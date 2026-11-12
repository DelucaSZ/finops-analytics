"""Read-only OCI Compute and Base Database calculator adapters (Task 27.4).

Only the existing effective-dated PricingResolver supplies monetary amounts.
Regional DB shape/edition/license compatibility is approved separately from rates
by explicit binding metadata; absent bindings or prices never become zero.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oci_db_calculator import OciDbCalculatorBinding
from app.schemas.calculator import (
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    CalculatorPricingStatus,
    OciComputeConfiguration,
    OciDbSystemConfiguration,
    OciVolumeConfiguration,
)
from app.services.calculator_engine import CalculatorMeteredComponent, estimate_calculator_cost
from app.services.calculator_foundation import (
    CalculatorCatalogAdapter,
    oci_compute_catalog_identities,
)
from app.services.oci_pricing import (
    OCI_BLOCK_STORAGE_SKU,
    OCI_BLOCK_VPU_SKU,
    OCI_MONTHLY_HOURS,
    OCI_SERVICE_BLOCK_VOLUME,
    OCI_SHAPE_PRICE_FAMILY,
    OCI_UNIT_GB_MONTH,
    OCI_UNIT_VPU_GB_MONTH,
)
from app.services.pricing_catalog import PricingIdentity

# Conservative standard-memory shape limits. Extended-memory VM SKUs are not in
# the approved catalog and must not be silently treated as the standard product.
STANDARD_SHAPE_LIMITS: dict[str, tuple[int, int]] = {
    "VM.Standard.E3.Flex": (64, 1024),
    "VM.Standard.E4.Flex": (64, 1024),
    "VM.Standard.E5.Flex": (94, 1024),
}
DB_SHAPE = "VM.BaseDB.x86"
OCI_EXCLUSIONS = (
    "excludes_network_egress",
    "excludes_load_balancers",
    "excludes_public_ip_charges",
    "excludes_backups",
    "excludes_object_and_file_storage",
    "excludes_additional_services",
    "oci_region_availability_not_verified",
    "oci_catalog_brl_final_no_additional_adjustments",
)


def _meter(key: str, lookup, units: Decimal, *, minimum: int = 0):
    return CalculatorMeteredComponent(
        key=key,
        lookup=lookup,
        units_per_resource=units,
        reference_month_hours=OCI_MONTHLY_HOURS,
        increment_seconds=1 if lookup.identity.unit.endswith("_HOUR") else None,
        minimum_billable_seconds=minimum,
        discount_eligible=False,
    )


def _finish(
    request: CalculatorEstimateRequest,
    at: datetime,
    components: list[CalculatorMeteredComponent],
    *,
    missing: list[str] | None = None,
    missing_status: CalculatorPricingStatus = "missing_configuration",
    warnings: list[str] | None = None,
) -> CalculatorEstimateResponse:
    return estimate_calculator_cost(
        request,
        components,
        reference_at=at,
        additional_missing_components=missing or (),
        missing_status=missing_status,
        extra_warnings=(*OCI_EXCLUSIONS, *(warnings or ())),
    )


def _invalid(request, at, reason: str, status: CalculatorPricingStatus):
    return _finish(
        request, at, [], missing=["configuration"], missing_status=status, warnings=[reason]
    )


def _volume_components(
    catalog: CalculatorCatalogAdapter,
    *,
    at: datetime,
    volume: OciVolumeConfiguration,
    prefix: str,
) -> tuple[list[CalculatorMeteredComponent], list[str]]:
    """Use distinct block storage and performance dimensions; VPU=0 incurs no VPU fee."""

    capacity = catalog.resolve(
        PricingIdentity("oci", OCI_SERVICE_BLOCK_VOLUME, OCI_BLOCK_STORAGE_SKU, OCI_UNIT_GB_MONTH),
        at=at,
    )
    units = volume.size_gb * Decimal(volume.count)
    components = [_meter(prefix + "_capacity", capacity, units)]
    if volume.vpus_per_gb is None:
        return components, [prefix + "_vpu_configuration"]
    if volume.vpus_per_gb % Decimal(10) != 0:
        return components, [prefix + "_unsupported_vpu_tier"]
    if volume.vpus_per_gb > 0:
        performance = catalog.resolve(
            PricingIdentity(
                "oci", OCI_SERVICE_BLOCK_VOLUME, OCI_BLOCK_VPU_SKU, OCI_UNIT_VPU_GB_MONTH
            ),
            at=at,
        )
        components.append(
            _meter(
                prefix + "_performance",
                performance,
                units * volume.vpus_per_gb,
            )
        )
    return components, []


def _compute(
    request: CalculatorEstimateRequest,
    at: datetime,
    catalog: CalculatorCatalogAdapter,
) -> CalculatorEstimateResponse:
    cfg = request.resource_configuration
    assert isinstance(cfg, OciComputeConfiguration)
    if not cfg.shape or cfg.ocpus is None or cfg.memory_gb is None:
        return _invalid(request, at, "required_shape_ocpus_memory", "missing_configuration")
    if cfg.shape not in OCI_SHAPE_PRICE_FAMILY:
        return _invalid(
            request, at, "oci_shape_not_in_pricing_allowlist", "unsupported_configuration"
        )
    max_ocpus, max_ram = STANDARD_SHAPE_LIMITS[cfg.shape]
    if (
        cfg.ocpus != cfg.ocpus.to_integral_value()
        or not Decimal(1) <= cfg.ocpus <= Decimal(max_ocpus)
        or cfg.memory_gb != cfg.memory_gb.to_integral_value()
        or cfg.memory_gb < cfg.ocpus
        or cfg.memory_gb > min(Decimal(max_ram), cfg.ocpus * Decimal(64))
    ):
        return _invalid(request, at, "invalid_oci_flex_ocpu_memory_pair", "invalid_combination")

    identities = oci_compute_catalog_identities(
        cfg.shape, windows=cfg.operating_system == "windows"
    )
    lookups = catalog.resolve_many(identities, at=at)
    components = [
        _meter("compute_ocpu", lookups[0], cfg.ocpus, minimum=60),
        _meter("compute_memory", lookups[1], cfg.memory_gb, minimum=60),
    ]
    missing: list[str] = []
    warnings: list[str] = []

    if cfg.operating_system == "windows":
        components.append(_meter("windows_license", lookups[2], cfg.ocpus))
    elif cfg.operating_system == "unknown":
        missing.append("operating_system_license_classification")
        warnings.append("unknown_operating_system_may_require_license")

    if cfg.boot_volume is not None:
        boot = cfg.boot_volume
        if boot.count != 1:
            return _invalid(request, at, "one_boot_volume_per_vm", "invalid_combination")
    elif cfg.boot_volume_gb is not None and cfg.boot_volume_gb > 0:
        boot = OciVolumeConfiguration(size_gb=cfg.boot_volume_gb, vpus_per_gb=cfg.vpus_per_gb)
    else:
        boot = None

    if boot is None:
        missing.append("boot_volume_configuration")
        warnings.append("boot_volume_not_configured")
    else:
        lines, absent = _volume_components(catalog, at=at, volume=boot, prefix="boot_volume")
        components.extend(lines)
        missing.extend(absent)

    for index, volume in enumerate(cfg.block_volumes):
        prefix = f"block_volume_{index + 1}"
        lines, absent = _volume_components(catalog, at=at, volume=volume, prefix=prefix)
        components.extend(lines)
        missing.extend(absent)

    if any("unsupported_vpu_tier" in key for key in missing):
        return _invalid(
            request, at, "oci_vpu_must_be_0_to_120_in_steps_of_10", "invalid_combination"
        )
    return _finish(request, at, components, missing=missing, warnings=warnings)


def _bindings(db: Session, request: CalculatorEstimateRequest, cfg: OciDbSystemConfiguration):
    rows = db.scalars(
        select(OciDbCalculatorBinding).where(
            OciDbCalculatorBinding.enabled.is_(True),
            OciDbCalculatorBinding.region == request.region,
            OciDbCalculatorBinding.deployment_model == cfg.deployment_model,
            OciDbCalculatorBinding.shape == cfg.shape,
            OciDbCalculatorBinding.edition == cfg.edition,
            OciDbCalculatorBinding.license_model == cfg.license_model,
            OciDbCalculatorBinding.cpu_unit == cfg.cpu_unit,
        )
    ).all()
    return {row.component: row for row in rows}


def _db_system(
    request: CalculatorEstimateRequest,
    at: datetime,
    catalog: CalculatorCatalogAdapter,
    db: Session,
) -> CalculatorEstimateResponse:
    cfg = request.resource_configuration
    assert isinstance(cfg, OciDbSystemConfiguration)
    if (
        not cfg.shape
        or not cfg.edition
        or not cfg.license_model
        or not cfg.cpu_unit
        or cfg.cpu_count is None
        or cfg.storage_gb is None
    ):
        return _invalid(
            request,
            at,
            "required_db_shape_edition_license_capacity_storage",
            "missing_configuration",
        )
    # New provisioning is restricted to the currently documented ECPU x86 BaseDB
    # configuration. Legacy OCPU variants are not silently converted to ECPU.
    if cfg.cpu_unit != "ECPU" or cfg.shape != DB_SHAPE:
        return _invalid(
            request,
            at,
            "legacy_ocpu_or_db_shape_not_available_for_new_provisioning",
            "unsupported_configuration",
        )
    if (
        cfg.cpu_count != cfg.cpu_count.to_integral_value()
        or cfg.cpu_count < 4
        or cfg.cpu_count > 256
        or cfg.cpu_count % 4 != 0
    ):
        return _invalid(
            request,
            at,
            "base_database_requires_4_to_256_ecpu_in_steps_of_4",
            "invalid_combination",
        )

    bindings = _bindings(db, request, cfg)
    capacity = bindings.get("capacity")
    licensing = bindings.get("license")
    storage = bindings.get("storage")
    if (
        (capacity and (capacity.unit != "ECPU_HOUR" or not capacity.source_reference.strip()))
        or (licensing and (licensing.unit != "ECPU_HOUR" or not licensing.source_reference.strip()))
        or (storage and (storage.unit != "GB_MONTH" or not storage.source_reference.strip()))
    ):
        return _invalid(
            request,
            at,
            "unverified_db_catalog_binding_or_incorrect_billing_unit",
            "pricing_configuration_error",
        )
    if cfg.license_model == "byol" and licensing:
        return _invalid(
            request, at, "byol_must_not_bill_extra_software_license", "invalid_combination"
        )
    if (
        cfg.license_model == "license_included"
        and capacity
        and capacity.includes_license
        and licensing
    ):
        return _invalid(
            request, at, "database_license_would_be_double_billed", "invalid_combination"
        )

    components: list[CalculatorMeteredComponent] = []
    missing: list[str] = []
    warnings = ["oci_base_database_quote_requires_verified_product_bindings"]
    if cfg.license_model == "byol":
        warnings.append("byol_requires_owned_eligible_oracle_licenses")
    if not capacity:
        missing.append("db_system_capacity_sku_mapping")
    else:
        lookup = catalog.resolve(
            PricingIdentity("oci", "db_system", capacity.sku, capacity.unit), at=at
        )
        components.append(_meter("db_system_capacity", lookup, cfg.cpu_count, minimum=60))

    if cfg.license_model == "license_included" and not (
        capacity is not None and capacity.includes_license
    ):
        if not licensing:
            missing.append("db_system_license_sku_mapping")
        else:
            lookup = catalog.resolve(
                PricingIdentity("oci", "db_system", licensing.sku, licensing.unit), at=at
            )
            components.append(_meter("db_system_license", lookup, cfg.cpu_count, minimum=60))

    if not storage:
        missing.append("db_system_storage_sku_mapping")
    else:
        lookup = catalog.resolve(
            PricingIdentity("oci", "db_system", storage.sku, storage.unit), at=at
        )
        components.append(_meter("db_system_storage", lookup, cfg.storage_gb, minimum=60))

    return _finish(
        request, at, components, missing=missing, missing_status="sku_missing", warnings=warnings
    )


def estimate_oci_calculator(
    request: CalculatorEstimateRequest,
    db: Session,
) -> CalculatorEstimateResponse:
    """Estimate OCI from a single catalog reference instant, without cloud API calls."""

    if request.provider != "oci":
        raise ValueError("OCI calculator cannot estimate another provider")
    at = (request.pricing_reference_date or datetime.now(UTC)).astimezone(UTC)
    catalog = CalculatorCatalogAdapter(db)
    if request.resource_configuration.service == "compute":
        return _compute(request, at, catalog)
    return _db_system(request, at, catalog, db)


def oci_calculator_options(
    db: Session, *, service: str, region: str, at: datetime | None = None
) -> dict:
    """Authenticated metadata with no invented regional service offerings."""

    reference = (at or datetime.now(UTC)).astimezone(UTC)
    catalog = CalculatorCatalogAdapter(db)
    if service == "compute":
        items = []
        for shape, (ocpu_limit, memory_limit) in STANDARD_SHAPE_LIMITS.items():
            pricing = catalog.resolve_many(oci_compute_catalog_identities(shape), at=reference)
            items.append(
                {
                    "shape": shape,
                    "max_ocpus": ocpu_limit,
                    "max_memory_gb": memory_limit,
                    "max_memory_per_ocpu_gb": 64,
                    "pricing_status": (
                        "priced" if all(row.available for row in pricing) else "sku_missing"
                    ),
                    "region_availability_verified": False,
                }
            )
        return {
            "service": service,
            "region": region,
            "currency": "BRL",
            "monthly_hours": str(OCI_MONTHLY_HOURS),
            "items": items,
            "operating_systems": ["linux", "windows"],
            "vpu_tiers": list(range(0, 121, 10)),
        }

    if service != "db_system":
        raise ValueError("unsupported OCI calculator service")
    rows = db.scalars(
        select(OciDbCalculatorBinding).where(
            OciDbCalculatorBinding.region == region,
            OciDbCalculatorBinding.enabled.is_(True),
        )
    ).all()
    groups: dict[tuple[str, str, str, str, str], dict] = {}
    for row in rows:
        k = (row.deployment_model, row.shape, row.edition, row.license_model, row.cpu_unit)
        group = groups.setdefault(
            k,
            {
                "deployment_model": row.deployment_model,
                "shape": row.shape,
                "edition": row.edition,
                "license_model": row.license_model,
                "cpu_unit": row.cpu_unit,
                "components": {},
            },
        )
        lookup = catalog.resolve(
            PricingIdentity("oci", "db_system", row.sku, row.unit), at=reference
        )
        group["components"][row.component] = {
            "sku": row.sku,
            "unit": row.unit,
            "status": lookup.status,
            "includes_license": row.includes_license,
            "source_reference": row.source_reference,
        }
    items = []
    for group in groups.values():
        parts = group["components"]
        necessary = {"capacity", "storage"}
        if group["license_model"] == "license_included" and not parts.get("capacity", {}).get(
            "includes_license"
        ):
            necessary.add("license")
        compatible = (
            group["shape"] == DB_SHAPE
            and group["cpu_unit"] == "ECPU"
            and (group["license_model"] != "byol" or "license" not in parts)
            and not (
                group["license_model"] == "license_included"
                and parts.get("capacity", {}).get("includes_license")
                and "license" in parts
            )
        )
        group["complete_price_available"] = compatible and all(
            k in parts and parts[k]["status"] == "priced" for k in necessary
        )
        items.append(group)
    return {
        "service": service,
        "region": region,
        "currency": "BRL",
        "monthly_hours": str(OCI_MONTHLY_HOURS),
        "items": items,
        "setup_required": not bool(items),
        "new_provisioning_shape": DB_SHAPE,
        "capacity_unit": "ECPU",
    }
