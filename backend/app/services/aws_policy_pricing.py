"""Read-only, fail-closed financial enrichment of AWS policy findings.

Collectors discover operational facts. This adapter resolves immutable, regional
On-Demand public-price identities from the same local catalog as the calculator.
It does not call the AWS Pricing API or mutate the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aws_pricing import AwsPricingProduct
from app.services.aws_calculator_regional import AwsLocalCalculatorResolver
from app.services.aws_regional_pricing import (
    AwsRegionalPricingRepository,
    AwsRegionalPricingResolver,
)
from app.services.collector_types import CollectedFinding

_CENT = Decimal("0.01")
_INSTANCE_HOURS = Decimal("730")
_AWS_FINANCIAL_RULES = frozenset({
    "ebs_unattached", "ec2_stopped_with_ebs", "eip_unassociated",
    "snapshot_retention", "ec2_nonprod_outside_hours",
    "load_balancer_no_traffic", "rds_nonprod_idle",
})


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _number(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None
    return result if result.is_finite() and result >= 0 else None


@dataclass(frozen=True)
class _Rate:
    status: str
    warning: str | None = None
    unit_price: Decimal | None = None
    unit: str | None = None
    catalog_item_id: str | None = None
    product_sku: str | None = None
    rate_code: str | None = None
    source: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    import_batch_id: str | None = None

    def component(self, name: str, quantity: Decimal) -> dict[str, Any]:
        valid = self.status == "priced" and self.unit_price is not None
        return {
            "name": name,
            "status": self.status,
            "reason": self.warning,
            "quantity": format(quantity, "f"),
            "unit": self.unit,
            "unit_price_usd": format(self.unit_price, "f") if valid else None,
            "estimated_cost_usd": format(_money(quantity * self.unit_price), "f") if valid else None,
            "catalog_item_id": self.catalog_item_id,
            "product_sku": self.product_sku,
            "rate_code": self.rate_code,
            "source": self.source,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "import_batch_id": self.import_batch_id,
        }


class AwsPolicyPricingAdapter:
    """One-scoped-execution cache; never shared across accounts, sessions or runs."""

    def __init__(self, db: Session, *, reference_at: datetime | None = None) -> None:
        self.db = db
        self.reference_at = reference_at or datetime.now(UTC)
        if self.reference_at.utcoffset() is None:
            raise ValueError("AWS pricing reference must be timezone-aware")
        self.calculator = AwsLocalCalculatorResolver(db)
        self.regional = AwsRegionalPricingResolver(db)
        self.repository = AwsRegionalPricingRepository(db)
        self._cache: dict[tuple[Any, ...], _Rate] = {}

    @staticmethod
    def _from_calculator(result: Any) -> _Rate:
        price = result.price
        return _Rate(
            status=result.status,
            warning=result.warning_code,
            unit_price=price.amount if price is not None and result.available else None,
            unit=price.unit if price is not None and result.available else None,
            catalog_item_id=price.id if price is not None and result.available else None,
            product_sku=result.product_sku,
            rate_code=result.rate_code,
            source=price.source if price is not None and result.available else None,
            effective_from=price.effective_from.isoformat() if price is not None and result.available else None,
            effective_until=price.effective_until.isoformat() if price is not None and price.effective_until else None,
            import_batch_id=result.import_batch_id,
        )

    def _calculator_rate(
        self, *, service: str, region: str, family: str, filters: dict[str, str],
        key: str, unit: str, matcher,
    ) -> _Rate:
        cache_key = ("calculator", service, region, family, key, unit, tuple(sorted(filters.items())))
        if cache_key not in self._cache:
            result = self.calculator.resolve(
                service=service, region=region, family=family, filters=filters,
                matches=matcher, unit=unit, aws_unit="", at=self.reference_at, key=key,
            )
            self._cache[cache_key] = self._from_calculator(result)
        return self._cache[cache_key]

    def _catalog_rate(
        self, *, service: str, region: str, unit: str, usage_token: str,
        service_codes: tuple[str, ...], family_token: str | None = None,
    ) -> _Rate:
        key = ("catalog", service, region, unit, usage_token, service_codes, family_token)
        if key in self._cache:
            return self._cache[key]
        statement = select(AwsPricingProduct).where(
            AwsPricingProduct.service == service,
            AwsPricingProduct.service_code.in_(service_codes),
            AwsPricingProduct.region_code == region,
            AwsPricingProduct.status == "active",
        )
        if usage_token:
            statement = statement.where(
                AwsPricingProduct.financial_attributes["usagetype"]
                .as_string().contains(usage_token, autoescape=True)
            )
        if family_token:
            statement = statement.where(
                AwsPricingProduct.product_family.ilike("%" + family_token + "%")
            )
        rows = list(self.db.scalars(statement.limit(51)))
        if len(rows) > 50:
            rate = _Rate("pricing_configuration_error", "aws_catalog_product_match_limit")
        elif len(rows) != 1:
            if len(rows) > 1:
                rate = _Rate("pricing_configuration_error", "aws_policy_ambiguous_product")
            else:
                states = [
                    self.repository.get_sync_state(service_code=code, region_code=region)
                    for code in service_codes
                ]
                missing_sync = not any(
                    state is not None and state.last_successful_batch_id is not None
                    for state in states
                )
                rate = _Rate(
                    "sync_required" if missing_sync else "sku_missing",
                    "aws_region_catalog_not_synchronized" if missing_sync else "aws_policy_product_absent",
                )
        else:
            product = rows[0]
            resolution = self.regional.resolve_aws_price(
                service=product.service,
                service_code=product.service_code,
                region_code=region,
                configuration=product.financial_attributes,
                billing_unit=unit,
                reference_at=self.reference_at,
                purchase_option="on_demand",
            )
            rate = _Rate(
                status=resolution.status,
                warning=resolution.warning_code,
                unit_price=resolution.unit_price,
                unit=resolution.billing_unit,
                catalog_item_id=resolution.catalog_item_id,
                product_sku=resolution.product_sku,
                rate_code=resolution.rate_code,
                source=resolution.source,
                effective_from=resolution.effective_from.isoformat() if resolution.effective_from else None,
                effective_until=resolution.effective_until.isoformat() if resolution.effective_until else None,
                import_batch_id=resolution.import_batch_id,
            )
        self._cache[key] = rate
        return rate

    def _ebs(self, region: str, volume: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        volume_type = str(volume.get("type") or volume.get("volume_type") or "")
        size = _number(volume.get("size_gib"))
        if volume_type not in {"gp2", "gp3", "io1", "io2", "st1", "sc1"} or size is None:
            return [], ["unsupported_ebs_type_or_size"]
        components: list[dict[str, Any]] = []
        missing: list[str] = []

        def add(name: str, token: str, family: str, unit: str, quantity: Decimal):
            rate = self._calculator_rate(
                service="ec2", region=region, family=family,
                filters={"contains:usagetype": token},
                key=name, unit=unit,
                matcher=lambda a: (
                    a.get("volumeApiName") in (None, volume_type)
                    and str(a.get("usagetype", "")).endswith(token)
                ),
            )
            components.append(rate.component(name, quantity))
            if rate.status != "priced":
                missing.append(name + ":" + rate.status)

        add("ebs_storage", "EBS:VolumeUsage." + volume_type, "Storage", "GB_MONTH", size)
        iops = _number(volume.get("iops"))
        throughput = _number(volume.get("throughput"))
        if volume_type in {"io1", "io2"}:
            if iops is None:
                missing.append("ebs_iops:missing_provisioned_iops")
            else:
                add("ebs_iops", "EBS:VolumeP-IOPS." + volume_type,
                    "System Operation", "IOPS_MONTH", iops)
        if volume_type == "gp3":
            if iops is None:
                missing.append("ebs_iops:missing_provisioned_iops")
            elif iops > 3000:
                add("ebs_iops", "EBS:VolumeP-IOPS.gp3", "System Operation",
                    "IOPS_MONTH", iops - 3000)
            if throughput is None:
                missing.append("ebs_throughput:missing_provisioned_throughput")
            elif throughput > 125:
                add("ebs_throughput", "EBS:VolumeP-Throughput.gp3", "Provisioned Throughput",
                    "MBPS_MONTH", throughput - 125)
        return components, missing

    def _ec2(self, region: str, details: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        instance_type = str(details.get("instance_type") or "")
        platform = str(details.get("platform_details") or "").lower()
        if "windows" in platform:
            operating_system = "Windows"
        elif "linux" in platform or "unix" in platform:
            operating_system = "Linux"
        else:
            return [], ["ec2_operating_system_unknown"]
        if str(details.get("tenancy") or "").lower() not in {"default", "shared"}:
            return [], ["ec2_shared_tenancy_not_confirmed"]
        if not instance_type:
            return [], ["ec2_instance_type_unknown"]
        rate = self._calculator_rate(
            service="ec2", region=region, family="Compute Instance",
            filters={"instanceType": instance_type, "operatingSystem": operating_system, "tenancy": "Shared"},
            key="ec2_compute", unit="INSTANCE_HOUR",
            matcher=lambda a: (
                a.get("instanceType") == instance_type
                and a.get("operatingSystem") == operating_system
                and a.get("tenancy") == "Shared"
                and a.get("preInstalledSw", "NA") in ("NA", "None")
                and a.get("capacitystatus", "Used") == "Used"
                and str(a.get("operation", "")).startswith("RunInstances")
            ),
        )
        return [rate.component("ec2_compute", _INSTANCE_HOURS)], [] if rate.status == "priced" else [rate.status]

    def _rds(self, region: str, details: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        engine = {"postgres": "PostgreSQL", "postgresql": "PostgreSQL",
                  "mysql": "MySQL", "mariadb": "MariaDB"}.get(str(details.get("engine") or "").lower())
        instance_type = str(details.get("instance_class") or "")
        multi = details.get("multi_az")
        if not engine or not instance_type or not isinstance(multi, bool):
            return [], ["rds_financial_identity_incomplete"]
        expected_license = (
            "postgresql-license" if engine == "PostgreSQL"
            else "general-public-license"
        )
        license_model = str(details.get("license_model") or "").lower()
        if license_model not in {expected_license, "no-license-required"}:
            return [], ["rds_license_model_unsupported_or_missing"]
        deployment = "Multi-AZ" if multi else "Single-AZ"
        rate = self._calculator_rate(
            service="rds", region=region, family="Database Instance",
            filters={"instanceType": instance_type, "databaseEngine": engine,
                     "deploymentOption": deployment},
            key="rds_instance", unit="INSTANCE_HOUR",
            matcher=lambda a: (
                a.get("instanceType") == instance_type
                and a.get("databaseEngine") == engine
                and a.get("deploymentOption") == deployment
                and a.get("deploymentModel") not in ("Custom", "Multi-AZ DB cluster")
                and str(a.get("licenseModel", "No license required")).lower()
                in ("no license required", "license included")
                and str(a.get("databaseEdition", "Standard")).lower()
                not in ("enterprise", "standard edition 2", "web", "express")
            ),
        )
        return [rate.component("rds_instance", _INSTANCE_HOURS)], [] if rate.status == "priced" else [rate.status]

    @staticmethod
    def _status(components: list[dict[str, Any]], missing: list[str]) -> str:
        priced = any(part.get("status") == "priced" for part in components)
        if missing or any(part.get("status") != "priced" for part in components):
            if priced:
                return "partially_priced"
            statuses = {part.get("status") for part in components}
            if "pricing_configuration_error" in statuses:
                return "pricing_configuration_error"
            if "sync_required" in statuses:
                return "sync_required"
            return "price_unavailable"
        return "priced" if components else "price_unavailable"

    @staticmethod
    def _total(components: list[dict[str, Any]]) -> Decimal:
        return sum(
            (Decimal(part["estimated_cost_usd"]) for part in components
             if part.get("estimated_cost_usd") is not None), Decimal("0")
        )

    @staticmethod
    def _schedule_hours(config: dict[str, Any]) -> Decimal | None:
        try:
            days = {int(day) for day in config.get("business_days", [])}
            if not days.issubset(set(range(1, 8))):
                return None
            start_h, start_m = map(int, str(config["business_hours_start"]).split(":"))
            end_h, end_m = map(int, str(config["business_hours_end"]).split(":"))
            start = start_h * 60 + start_m
            end = end_h * 60 + end_m
            if not (0 <= start < end <= 1440):
                return None
            monthly_hours = (Decimal(10080 - len(days) * (end - start)) / Decimal(10080)) * _INSTANCE_HOURS
            return monthly_hours
        except (KeyError, TypeError, ValueError):
            return None

    def _price_one(
        self, finding: CollectedFinding, config: dict[str, Any]
    ) -> bool:
        details = finding.evidence.get("details", {})
        region = finding.region or ""
        components: list[dict[str, Any]] = []
        missing: list[str] = []
        notes: list[str] = []
        savings: Decimal | None = None
        current: Decimal | None = None
        key = finding.rule_key

        if key == "ebs_unattached":
            components, missing = self._ebs(region, details)
        elif key == "ec2_stopped_with_ebs":
            for volume in details.get("volumes", []):
                parts, absent = self._ebs(region, volume)
                components.extend(parts)
                missing.extend(absent)
            if not details.get("volumes"):
                missing.append("ebs_volumes_not_described")
            notes.append("Stopping EC2 does not eliminate attached EBS charges; deletion requires separate validation.")
        elif key == "eip_unassociated":
            rate = self._catalog_rate(service="ipv4", region=region, unit="IP_HOUR",
                                      usage_token="IdleAddress", service_codes=("AmazonVPC", "AmazonEC2"))
            components = [rate.component("public_ipv4_idle", _INSTANCE_HOURS)]
        elif key == "snapshot_retention":
            tier = str(details.get("storage_tier") or "standard").lower()
            if tier != "standard":
                missing.append("snapshot_storage_tier_not_supported")
            else:
                rate = self._catalog_rate(service="snapshot", region=region, unit="GB_MONTH",
                                          usage_token="SnapshotUsage", service_codes=("AmazonEC2",))
                size = _number(details.get("volume_size_gib"))
                if size is None:
                    missing.append("snapshot_logical_size_unknown")
                else:
                    components = [rate.component("snapshot_logical_upper_bound", size)]
            notes.append("Incremental snapshots: source volume size is an upper bound, not measured billable storage.")
        elif key == "ec2_nonprod_outside_hours":
            components, missing = self._ec2(region, details)
        elif key == "load_balancer_no_traffic":
            lb_type = str(details.get("load_balancer_type") or "")
            service = {"application": "alb", "network": "nlb", "classic": "clb"}.get(lb_type)
            if service is None:
                missing.append("load_balancer_type_unsupported")
            else:
                rate = self._catalog_rate(service=service, region=region, unit="LB_HOUR",
                                          usage_token="LoadBalancerUsage", service_codes=("AWSELB",))
                components = [rate.component("load_balancer_base", _INSTANCE_HOURS)]
            missing.append("load_balancer_variable_usage_not_estimated")
            notes.append("Base rate only; LCU/NLCU/other variable charges are excluded.")
            if not details.get("datapoint_count"):
                notes.append("CloudWatch has no datapoints: zero traffic is not established.")
        elif key == "rds_nonprod_idle":
            components, missing = self._rds(region, details)
            notes.append("Only instance compute is potentially avoidable; storage and other RDS costs remain.")
        else:
            return True

        status = self._status(components, missing)
        total = self._total(components)
        full = status == "priced"
        if key in {"ebs_unattached", "ec2_stopped_with_ebs", "eip_unassociated"} and full:
            current = _money(total)
            savings = current
        elif key == "snapshot_retention" and full:
            current = _money(total)
            # Logical upper bounds cannot be recognized as actual savings.
            savings = None
        elif key == "ec2_nonprod_outside_hours" and full:
            current = _money(total)
            scheduled = self._schedule_hours(config)
            if scheduled is None:
                status = "partially_priced"
                missing.append("invalid_business_schedule")
            else:
                unit_price = _number(components[0].get("unit_price_usd"))
                if unit_price is not None:
                    savings = _money(unit_price * scheduled)
                    notes.append("Off-hours estimate assumes recurring running time; actual uptime not verified.")
        elif key == "rds_nonprod_idle" and full:
            # Current total is unknown because storage and additional usage are excluded.
            savings = _money(total)
            status = "partially_priced"
            missing.append("rds_storage_and_additional_costs_excluded")

        finding.current_monthly_cost = current
        finding.estimated_monthly_savings = savings
        if savings is None:
            finding.severity = "low"
            finding.confidence = "low"
        elif savings >= 100:
            finding.severity = "high"
        elif savings >= 20:
            finding.severity = "medium"
        else:
            finding.severity = "low"
        threshold = _number(config.get("minimum_monthly_savings_usd", 0))
        if threshold is not None and savings is not None and savings < threshold:
            return False
        finding.evidence["pricing"] = {
            "provider": "aws",
            "region": region,
            "currency": "USD",
            "source": "AWS_REGIONAL_CATALOG",
            "reference_at": self.reference_at.isoformat(),
            "status": status,
            "known_subtotal_usd": format(_money(total), "f") if components else None,
            "current_monthly_cost_usd": format(current, "f") if current is not None else None,
            "estimated_monthly_savings_usd": format(savings, "f") if savings is not None else None,
            "components": components,
            "missing_components": missing,
            "notes": notes,
        }
        if current is not None:
            finding.evidence.setdefault("metrics", []).append({
                "key": "aws_regional_priced_monthly_cost",
                "label": "Regional public rate estimated monthly cost",
                "value": float(current),
                "unit": "USD_MONTH",
                "kind": "estimate",
            })
        if savings is not None:
            finding.evidence.setdefault("metrics", []).append({
                "key": "aws_regional_priced_monthly_savings",
                "label": "Regional public rate estimated monthly savings",
                "value": float(savings),
                "unit": "USD_MONTH",
                "kind": "estimate",
            })
        finding.evidence.setdefault("notes", []).extend(notes)
        return True

    def enrich_findings(self, findings: list[CollectedFinding], policies: list[dict[str, Any]]) -> None:
        by_rule = {policy["rule_key"]: policy.get("config", {}) for policy in policies}
        # All resource discovery is complete before any pricing DB query is made.
        findings[:] = [
            finding for finding in findings
            if finding.rule_key not in _AWS_FINANCIAL_RULES
            or self._price_one(finding, by_rule.get(finding.rule_key, {}))
        ]
