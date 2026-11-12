"""AWS EC2/RDS cost adapters: select verified SKU components, never compute money.

The provider-neutral Task 27.2 engine owns duration, quantity, discount, FX and tax.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.calculator import (
    AwsEc2Configuration,
    AwsRdsConfiguration,
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
)
from app.services.aws_calculator_pricing import AwsPublicPriceResolver, missing_aws_lookup
from app.services.calculator_engine import (
    CalculatorMeteredComponent,
    estimate_calculator_cost,
)

# An explicit estimation convention, not a promise of calendar-month usage.
AWS_INSTANCE_REFERENCE_HOURS = Decimal("730")
AWS_STORAGE_REFERENCE_HOURS = Decimal("720")
_OSS_ENGINES = {
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
}
_EXCLUSIONS = (
    "excludes_data_transfer",
    "excludes_public_ipv4",
    "excludes_snapshots",
    "excludes_backups",
    "excludes_monitoring",
    "excludes_optional_io_requests",
    "aws_public_on_demand_not_contract_net_price",
    "aws_price_list_current_snapshot_not_historical",
)


def _component(key, lookup, units, *, month, minimum=0, eligible=True):
    return CalculatorMeteredComponent(
        key=key,
        lookup=lookup,
        units_per_resource=Decimal(units),
        reference_month_hours=month,
        increment_seconds=1 if lookup.identity.unit.endswith("_HOUR") else None,
        minimum_billable_seconds=minimum,
        discount_eligible=eligible,
    )


def _missing(request, at, key, unit, warning, *, month=AWS_INSTANCE_REFERENCE_HOURS):
    return _component(
        key,
        missing_aws_lookup(
            request.resource_configuration.service,
            request.region,
            key,
            unit,
            at,
            (
                "missing_configuration"
                if warning.startswith("required_")
                else "unsupported_configuration"
            ),
            warning,
        ),
        1,
        month=month,
    )


def _quote(resolver, request, at, key, family, filters, matches, unit, aws_unit):
    return resolver.resolve(
        service=request.resource_configuration.service,
        region=request.region,
        family=family,
        filters=filters,
        matches=matches,
        unit=unit,
        aws_unit=aws_unit,
        at=at,
        key=key,
    )


def _ec2(request, at, resolver):
    cfg: AwsEc2Configuration = request.resource_configuration
    components = []
    warnings = []
    if not cfg.instance_type or not cfg.operating_system:
        components.append(
            _missing(
                request,
                at,
                "compute",
                "INSTANCE_HOUR",
                "required_instance_type_and_operating_system",
            )
        )
        return components, warnings
    if (
        cfg.operating_system.lower() not in {"linux", "windows"}
        or cfg.purchase_option not in (None, "on_demand")
        or cfg.tenancy not in (None, "shared")
    ):
        components.append(
            _missing(
                request, at, "compute", "INSTANCE_HOUR", "ec2_only_linux_windows_shared_on_demand"
            )
        )
        return components, warnings
    os_name = {"linux": "Linux", "windows": "Windows"}[cfg.operating_system.lower()]
    lookup = _quote(
        resolver,
        request,
        at,
        "compute",
        "Compute Instance",
        {
            "instanceType": cfg.instance_type,
            "operatingSystem": os_name,
            "tenancy": "Shared",
            "preInstalledSw": "NA",
            "capacitystatus": "Used",
        },
        lambda a: (
            a.get("instanceType") == cfg.instance_type
            and a.get("operatingSystem") == os_name
            and a.get("tenancy") == "Shared"
            and a.get("preInstalledSw") == "NA"
            and a.get("capacitystatus") == "Used"
            and a.get("operation", "").startswith("RunInstances")
        ),
        "INSTANCE_HOUR",
        "Hrs",
    )
    components.append(
        _component(
            "compute",
            lookup,
            1,
            month=AWS_INSTANCE_REFERENCE_HOURS,
            minimum=60,
            eligible=os_name == "Linux",
        )
    )
    # The Windows OS charge is already included in the Compute Instance SKU.
    if cfg.root_volume_gb is None or cfg.root_volume_gb == 0:
        warnings.append("ebs_storage_not_configured")
        if cfg.ebs_iops is not None or cfg.ebs_throughput_mbps is not None:
            components.append(
                _missing(
                    request,
                    at,
                    "ebs_storage",
                    "GB_MONTH",
                    "ebs_performance_requires_storage",
                    month=AWS_STORAGE_REFERENCE_HOURS,
                )
            )
        return components, warnings
    if cfg.ebs_volume_type == "gp2" and (
        cfg.ebs_iops is not None or cfg.ebs_throughput_mbps is not None
    ):
        components.append(
            _missing(
                request,
                at,
                "ebs_performance",
                "IOPS_MONTH",
                "gp2_custom_performance_not_supported",
                month=AWS_STORAGE_REFERENCE_HOURS,
            )
        )
        return components, warnings

    def ebs_price(key, family, unit, aws_unit):
        return _quote(
            resolver,
            request,
            at,
            key,
            family,
            {
                "volumeApiName": cfg.ebs_volume_type,
                "contains:usagetype": {
                    "ebs_storage": f"EBS:VolumeUsage.{cfg.ebs_volume_type}",
                    "ebs_iops": "EBS:VolumeP-IOPS.gp3",
                    "ebs_throughput": "EBS:VolumeP-Throughput.gp3",
                }[key],
            },
            lambda a: (
                a.get("volumeApiName") == cfg.ebs_volume_type
                and a.get("usagetype", "").endswith(
                    {
                        "ebs_storage": f"EBS:VolumeUsage.{cfg.ebs_volume_type}",
                        "ebs_iops": "EBS:VolumeP-IOPS.gp3",
                        "ebs_throughput": "EBS:VolumeP-Throughput.gp3",
                    }[key]
                )
            ),
            unit,
            aws_unit,
        )

    # EBS storage and provisioned performance are billed per second with 60s minimum.
    components.append(
        _component(
            "ebs_storage",
            ebs_price("ebs_storage", "Storage", "GB_MONTH", "GB-Mo"),
            cfg.root_volume_gb * cfg.ebs_volume_count,
            month=AWS_STORAGE_REFERENCE_HOURS,
            minimum=60,
            eligible=False,
        )
    )
    iops = cfg.ebs_iops if cfg.ebs_iops is not None else 3000
    throughput = cfg.ebs_throughput_mbps if cfg.ebs_throughput_mbps is not None else 125
    if cfg.ebs_volume_type == "gp3" and iops > 3000:
        components.append(
            _component(
                "ebs_iops",
                ebs_price("ebs_iops", "System Operation", "IOPS_MONTH", "IOPS-Mo"),
                Decimal(iops - 3000) * cfg.ebs_volume_count,
                month=AWS_STORAGE_REFERENCE_HOURS,
                minimum=60,
                eligible=False,
            )
        )
    if cfg.ebs_volume_type == "gp3" and throughput > 125:
        components.append(
            _component(
                "ebs_throughput",
                ebs_price("ebs_throughput", "Provisioned Throughput", "MBPS_MONTH", "MBps-Mo"),
                Decimal(throughput - 125) * cfg.ebs_volume_count,
                month=AWS_STORAGE_REFERENCE_HOURS,
                minimum=60,
            )
        )
    return components, warnings


def _rds(request, at, resolver):
    cfg: AwsRdsConfiguration = request.resource_configuration
    components = []
    warnings = []
    if not cfg.instance_class or not cfg.engine or not cfg.deployment:
        return [
            _missing(
                request, at, "instance", "INSTANCE_HOUR", "required_rds_engine_class_deployment"
            )
        ], warnings
    engine = _OSS_ENGINES.get(cfg.engine.lower())
    deployment = {"single_az": "Single-AZ", "multi_az": "Multi-AZ"}.get(cfg.deployment.lower())
    if not engine or not deployment or cfg.license_model not in (None, "no_license_required"):
        return [
            _missing(
                request,
                at,
                "instance",
                "INSTANCE_HOUR",
                "rds_engine_deployment_or_license_not_supported",
            )
        ], warnings
    if cfg.database_edition not in (None, ""):
        return [
            _missing(
                request,
                at,
                "instance",
                "INSTANCE_HOUR",
                "rds_database_edition_not_supported_for_oss",
            )
        ], warnings
    lookup = _quote(
        resolver,
        request,
        at,
        "instance",
        "Database Instance",
        {
            "instanceType": cfg.instance_class,
            "databaseEngine": engine,
            "deploymentOption": deployment,
        },
        lambda a: (
            a.get("instanceType") == cfg.instance_class
            and a.get("databaseEngine") == engine
            and a.get("deploymentOption") == deployment
            and a.get("deploymentModel") not in ("Custom", "Multi-AZ DB cluster")
            and a.get("licenseModel", "No license required").lower()
            in ("no license required", "license included")
            and a.get("databaseEdition", "Standard").lower()
            not in ("enterprise", "standard edition 2", "web", "express")
        ),
        "INSTANCE_HOUR",
        "Hrs",
    )
    # The AWS instance rate includes any licensing for this selected engine.
    components.append(
        _component("instance", lookup, 1, month=AWS_INSTANCE_REFERENCE_HOURS, minimum=600)
    )
    if cfg.storage_type is None and cfg.allocated_storage_gb is None:
        if cfg.provisioned_iops is not None or cfg.provisioned_throughput_mbps is not None:
            components.append(
                _missing(
                    request,
                    at,
                    "storage",
                    "GB_MONTH",
                    "storage_required_for_performance",
                    month=AWS_STORAGE_REFERENCE_HOURS,
                )
            )
        else:
            warnings.append("rds_storage_not_configured")
        return components, warnings
    if (
        cfg.storage_type not in ("gp2", "gp3")
        or cfg.allocated_storage_gb is None
        or cfg.allocated_storage_gb < 20
    ):
        components.append(
            _missing(
                request,
                at,
                "storage",
                "GB_MONTH",
                "rds_storage_type_and_size_required",
                month=AWS_STORAGE_REFERENCE_HOURS,
            )
        )
        return components, warnings
    # For gp3 extra IOPS/throughput, the baseline varies by engine, capacity
    # and deployment. Never omit or infer paid performance components.
    baseline_iops = 12000 if cfg.storage_type == "gp3" and cfg.allocated_storage_gb >= 400 else 3000
    baseline_mbps = 500 if cfg.storage_type == "gp3" and cfg.allocated_storage_gb >= 400 else 125
    if (
        (cfg.provisioned_iops is not None and cfg.provisioned_iops > baseline_iops)
        or (
            cfg.provisioned_throughput_mbps is not None
            and cfg.provisioned_throughput_mbps > baseline_mbps
        )
        or (
            cfg.storage_type == "gp2"
            and (cfg.provisioned_iops is not None or cfg.provisioned_throughput_mbps is not None)
        )
    ):
        components.append(
            _missing(
                request,
                at,
                "performance",
                "IOPS_MONTH",
                "rds_extra_performance_pricing_not_yet_supported",
                month=AWS_STORAGE_REFERENCE_HOURS,
            )
        )
        return components, warnings
    # Avoid nonsensical gp3 provisioned performance values below the baseline.
    if (cfg.provisioned_iops is not None and cfg.provisioned_iops < baseline_iops) or (
        cfg.provisioned_throughput_mbps is not None
        and cfg.provisioned_throughput_mbps < baseline_mbps
    ):
        components.append(
            _missing(
                request,
                at,
                "performance",
                "IOPS_MONTH",
                "rds_gp3_performance_below_baseline",
                month=AWS_STORAGE_REFERENCE_HOURS,
            )
        )
        return components, warnings

    suffix = ("Multi-AZ-" if deployment == "Multi-AZ" else "") + (
        "GP3-Storage" if cfg.storage_type == "gp3" else "GP2-Storage"
    )
    storage = _quote(
        resolver,
        request,
        at,
        "storage",
        "Database Storage",
        {"contains:usagetype": f"RDS:{suffix}"},
        # RDS storage SKUs can be engine-neutral; constrain by exact usage.
        lambda a: (
            a.get("usagetype", "").endswith(f"RDS:{suffix}")
            and a.get("databaseEngine") in (None, engine, "Any")
            and a.get("deploymentOption") in (None, deployment)
        ),
        "GB_MONTH",
        "GB-Mo",
    )
    components.append(
        _component(
            "storage",
            storage,
            cfg.allocated_storage_gb,
            month=AWS_STORAGE_REFERENCE_HOURS,
            minimum=600,
            eligible=False,
        )
    )
    return components, warnings


def estimate_aws_calculator(
    request: CalculatorEstimateRequest,
    *,
    resolver: AwsPublicPriceResolver | None = None,
    reference_at: datetime | None = None,
) -> CalculatorEstimateResponse:
    if request.provider != "aws":
        raise ValueError("only_aws")
    at = (request.pricing_reference_date or reference_at or datetime.now(UTC)).astimezone(UTC)
    provider = resolver or AwsPublicPriceResolver()
    if request.resource_configuration.service == "ec2":
        components, extra = _ec2(request, at, provider)
    else:
        components, extra = _rds(request, at, provider)
    result = estimate_calculator_cost(request, components, reference_at=at)
    return result.model_copy(
        update={"warnings": list(dict.fromkeys([*result.warnings, *extra, *_EXCLUSIONS]))}
    )
