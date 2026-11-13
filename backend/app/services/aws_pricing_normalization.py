"""Conservative AWS Price List normalization for regional On-Demand import.

Never infer a service category or billable unit from an unrelated tariff.
Unknown offerings are counted, not silently converted into prices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.aws_regional_pricing import AwsPricingValidationError

_SOURCE_SERVICES = frozenset({"AmazonEC2", "AmazonRDS", "AWSELB", "AmazonVPC"})
_ALLOWED_FIELDS = frozenset(
    {
        "instanceType",
        "operatingSystem",
        "tenancy",
        "preInstalledSw",
        "capacitystatus",
        "operation",
        "databaseEngine",
        "databaseEdition",
        "deploymentOption",
        "deploymentModel",
        "licenseModel",
        "storageType",
        "volumeApiName",
        "usagetype",
        "volumeType",
        "snapshotType",
        "group",
        "groupDescription",
        "locationType",
        "loadBalancerType",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedProduct:
    sku: str
    service: str
    service_code: str
    region: str
    family: str
    description: str
    attributes: dict[str, str]
    financial_attributes: dict[str, str]


@dataclass(frozen=True, slots=True)
class NormalizedRate:
    product: NormalizedProduct
    rate_code: str
    term_code: str
    amount: Decimal
    effective_at: str
    aws_unit: str
    unit: str
    begin_range: str
    end_range: str
    description: str
    pricing_status: str
    component: str


def supported_source(service_code: str) -> bool:
    return service_code in _SOURCE_SERVICES


def _token(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _volume_type(attr: dict[str, str], usage: str) -> str | None:
    match = re.search(r"(?:^|[-:.])(gp2|gp3|io1|io2|st1|sc1)(?:$|[-:.])", usage, re.I)
    if match:
        return match.group(1).lower()
    source = (attr.get("volumeApiName") or attr.get("volumeType") or "").lower()
    for code in ("gp2", "gp3", "io1", "io2", "st1", "sc1"):
        if source == code or re.search(r"\b" + code + r"\b", source):
            return code
    return None


def _is_ebs(usage: str, family: str) -> bool:
    return (
        "EBS" in usage.upper()
        or "EBS" in family.upper()
        or "Storage" in family
        and any(x in usage for x in ("VolumeUsage", "VolumeP-IOPS", "VolumeThroughput"))
    )


def classify_product(
    service_code: str, region: str, sku: str, product: dict[str, Any]
) -> NormalizedProduct | None:
    """Return None for ambiguous/non-target offers. Never cross a regional boundary."""
    if not supported_source(service_code):
        return None
    attr_raw = product.get("attributes")
    if not isinstance(attr_raw, dict):
        return None
    attr = {str(k): v for k, v in attr_raw.items() if isinstance(v, str)}
    origin_region = attr.get("regionCode")
    if origin_region and origin_region != region:
        return None
    if attr.get("locationType") not in (None, "", "AWS Region"):
        return None
    family = _token(product.get("productFamily"))
    usage = attr.get("usagetype", "")
    group = (attr.get("group", "") + " " + attr.get("groupDescription", "")).lower()
    service = ""
    if service_code == "AmazonEC2":
        if family == "Compute Instance" and attr.get("instanceType"):
            if attr.get("operatingSystem") not in {"Linux", "Windows"}:
                return None
            if attr.get("tenancy") != "Shared":
                return None
            if attr.get("preInstalledSw", "NA") not in {"NA", "None"}:
                return None
            if attr.get("capacitystatus", "Used") != "Used":
                return None
            service = "ec2"
        elif re.search(r"Snap(?:shot)?Usage|Snapshot", usage + family, re.I):
            service = "snapshot"
        elif _is_ebs(usage, family) and _volume_type(attr, usage):
            service = "ebs"
        elif re.search(r"PublicIPv4|InUseAddress|IdleAddress", usage, re.I):
            service = "ipv4"
    elif service_code == "AmazonRDS":
        if (
            family == "Database Instance"
            and attr.get("instanceType")
            and attr.get("databaseEngine")
        ):
            if attr.get("databaseEngine") not in {"PostgreSQL", "MySQL", "MariaDB"}:
                return None
            if not attr.get("deploymentOption"):
                return None
            service = "rds"
        elif attr.get("usagetype") and re.search(r"Storage|IOPS|Throughput", family + usage, re.I):
            service = "rds"
    elif service_code == "AmazonVPC":
        if re.search(r"PublicIPv4|InUseAddress|IdleAddress", usage, re.I):
            service = "ipv4"
    elif service_code == "AWSELB":
        lookup = (usage + " " + family + " " + group).lower()
        if "network" in lookup or "nlb" in lookup or "nlcuusage" in lookup:
            service = "nlb"
        elif "application" in lookup or "alb" in lookup or "lcuusage" in lookup:
            service = "alb"
        elif "classic" in lookup or "clb" in lookup:
            service = "clb"
        # An unqualified LoadBalancerUsage is ambiguous: do not label it Classic.
    if not service or not isinstance(sku, str) or not sku.strip():
        return None
    attrs = {k: v for k, v in attr.items() if len(k) <= 100 and len(v) <= 500}
    financial = {k: v for k, v in attrs.items() if k in _ALLOWED_FIELDS and v}
    financial["productFamily"] = family
    if service == "ec2" and not all(
        financial.get(k) for k in ("instanceType", "operatingSystem", "tenancy", "operation")
    ):
        return None
    if service == "ebs" and not financial.get("usagetype"):
        return None
    if service == "rds":
        if attr.get("instanceType"):
            if not all(financial.get(k) for k in ("databaseEngine", "deploymentOption")):
                return None
        elif not financial.get("usagetype"):
            return None
    if not financial or not family:
        return None
    return NormalizedProduct(
        sku=sku.strip(),
        service=service,
        service_code=service_code,
        region=region,
        family=family,
        description=_token(product.get("productFamily")) or service,
        attributes=attrs,
        financial_attributes=financial,
    )


def _unit(aws_unit: str, service: str, usage: str) -> tuple[str, str] | None:
    """Explicit mappings; no monthly to hourly conversion or unit guessing."""
    key = aws_unit.strip().lower()
    if service in {"ec2", "rds"} and key in {"hrs", "hours"}:
        return ("INSTANCE_HOUR", "")
    if service in {"alb", "nlb", "clb"}:
        if key in {"hrs", "hours"}:
            return ("LB_HOUR", "hour")
        if key == "lcu-hrs" and service == "alb":
            return ("LCU_HOUR", "lcu")
        if key == "nlcu-hrs" and service == "nlb":
            return ("NLCU_HOUR", "nlcu")
    if service == "ipv4" and key in {"hrs", "hours"}:
        return ("IP_HOUR", "ipv4")
    if service in {"ebs", "snapshot", "rds"}:
        if key in {"gb-mo", "gb-month", "gb-months"}:
            return ("GB_MONTH", "capacity")
        if key in {"iops-mo", "iops-month"}:
            return ("IOPS_MONTH", "iops")
        if key in {"mbps-mo", "mbps-month"}:
            return ("MBPS_MONTH", "throughput")
    return None


def normalize_rate(
    product: NormalizedProduct, rate_code: str, term_code: str, term: dict, dimension: dict
) -> NormalizedRate:
    if not rate_code or not term_code or not isinstance(dimension, dict):
        raise AwsPricingValidationError("missing rate_code/term_code/dimension")
    currency = dimension.get("pricePerUnit")
    if not isinstance(currency, dict) or set(currency) != {"USD"}:
        raise AwsPricingValidationError("missing or non-USD pricing dimension")
    try:
        amount = Decimal(str(currency["USD"]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AwsPricingValidationError("invalid monetary value") from exc
    if not amount.is_finite() or amount < 0:
        raise AwsPricingValidationError("invalid nonnegative finite price")
    if amount.as_tuple().exponent < -8 and amount != amount.quantize(Decimal("0.00000001")):
        raise AwsPricingValidationError("rate exceeds NUMERIC(20,8) precision")
    if amount >= Decimal("1000000000000"):
        raise AwsPricingValidationError("rate exceeds NUMERIC(20,8) range")
    unit = _token(dimension.get("unit"))
    usage = product.attributes.get("usagetype", "")
    if (
        product.service == "rds"
        and unit.lower() in {"hrs", "hours"}
        and not product.attributes.get("instanceType")
    ):
        raise AwsPricingValidationError("non-instance RDS hourly offering")
    mapped = _unit(unit, product.service, usage)
    if not mapped:
        raise AwsPricingValidationError("unsupported billing unit " + unit[:40])
    billing_unit, component = mapped
    if product.service == "ebs":
        family = product.family.lower()
        if component == "capacity" and "snapshot" in family:
            raise AwsPricingValidationError("ambiguous EBS snapshot family")
    begin = str(dimension.get("beginRange", ""))
    end = str(dimension.get("endRange", ""))
    if not begin or not end:
        raise AwsPricingValidationError("missing tier ranges")
    effective = _token(term.get("effectiveDate"))
    if not effective:
        raise AwsPricingValidationError("missing effectiveDate")
    description = _token(dimension.get("description")) or product.description
    return NormalizedRate(
        product=product,
        rate_code=rate_code,
        term_code=term_code,
        amount=amount,
        effective_at=effective,
        aws_unit=unit,
        unit=billing_unit,
        begin_range=begin,
        end_range=end,
        description=description[:500],
        pricing_status="active" if (begin, end) == ("0", "Inf") else "unsupported",
        component=component,
    )


def coverage_component(rate: NormalizedRate) -> str:
    service = rate.product.service
    attr = rate.product.attributes
    usage = attr.get("usagetype", "")
    if service == "ec2":
        return "ec2_" + attr.get("operatingSystem", "").lower()
    if service == "ebs":
        volume = _volume_type(attr, usage) or "unknown"
        return "ebs_" + volume + "_" + rate.component
    if service == "rds":
        if rate.unit == "INSTANCE_HOUR":
            engine = attr.get("databaseEngine", "").lower()
            deployment = attr.get("deploymentOption", "").lower().replace("-", "")
            return "rds_" + engine + "_" + deployment
        if rate.unit == "GB_MONTH":
            volume = _volume_type(attr, usage) or "unknown"
            return "rds_" + volume + "_capacity"
        return "rds_" + rate.component
    if service == "snapshot":
        return "snapshot_storage"
    if service == "ipv4":
        return "ipv4_hour"
    if service in {"alb", "nlb", "clb"}:
        return service + "_" + rate.component
    return service


_REQUIRED_COVERAGE: dict[str, frozenset[str]] = {
    "AmazonEC2": frozenset(
        {
            "ec2_linux",
            "ec2_windows",
            "ebs_gp2_capacity",
            "ebs_gp3_capacity",
            "ebs_gp3_iops",
            "ebs_gp3_throughput",
            "ebs_io1_capacity",
            "ebs_io2_capacity",
            "ebs_st1_capacity",
            "ebs_sc1_capacity",
            "snapshot_storage",
        }
    ),
    "AmazonRDS": frozenset(
        {
            "rds_postgresql_singleaz",
            "rds_mysql_singleaz",
            "rds_mariadb_singleaz",
            "rds_gp2_capacity",
            "rds_gp3_capacity",
        }
    ),
    "AWSELB": frozenset({"alb_hour", "alb_lcu", "nlb_hour", "nlb_nlcu"}),
    "AmazonVPC": frozenset({"ipv4_hour"}),
}


def coverage_summary(service_code: str, observed: dict[str, int]) -> dict[str, Any]:
    mandatory = sorted(_REQUIRED_COVERAGE.get(service_code, ()))
    present = sorted(k for k, count in observed.items() if count > 0)
    return {
        "required": mandatory,
        "present": present,
        "missing": sorted(set(mandatory) - set(present)),
        "counts": dict(sorted(observed.items())),
        "complete": bool(mandatory) and set(mandatory).issubset(present),
    }
