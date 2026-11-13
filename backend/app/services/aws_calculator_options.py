"""Authenticated read-only regional AWS calculator metadata.

Regions and searchable EC2/RDS combinations come only from local database state.
The public AWS Pricing API is used by the importer, never by calculator endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.aws_pricing import (
    AwsPricingProduct,
    AwsPricingRateDetail,
    AwsPricingSyncState,
)
from app.models.pricing import PricingCatalogItem
from app.services.aws_pricing_sync import discover_regions

_ENGINES = {"postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB"}


def _coverage_status(states: list[AwsPricingSyncState]) -> str:
    if not states or all(state.last_successful_batch_id is None for state in states):
        return "sync_required"
    for status in ("stale", "partial", "failed"):
        if any(state.coverage_status == status for state in states):
            return status
    return "synced"


def available_regions(db: Session) -> dict:
    """Account regions, local catalog, and per-service sync coverage."""
    regions = set(discover_regions(db, settings.aws_pricing_sync_extra_regions))
    regions.update(db.scalars(select(AwsPricingProduct.region_code).distinct()))
    states = list(
        db.scalars(
            select(AwsPricingSyncState).where(
                AwsPricingSyncState.service_code.in_(("AmazonEC2", "AmazonRDS"))
            )
        )
    )
    regions.update(state.region_code for state in states)
    statuses: dict[str, str] = {}
    by_service: dict[str, dict[str, str]] = {"ec2": {}, "rds": {}}
    for region in sorted(regions):
        matches = [state for state in states if state.region_code == region]
        statuses[region] = _coverage_status(matches)
        for name, code in (("ec2", "AmazonEC2"), ("rds", "AmazonRDS")):
            service_states = [state for state in matches if state.service_code == code]
            by_service[name][region] = _coverage_status(service_states)
    return {
        "items": sorted(regions),
        "source": "AWS_REGIONAL_CATALOG",
        "region_status": statuses,
        "service_status": by_service,
    }

def aws_options(
    db: Session,
    *,
    region: str,
    service: str,
    search: str,
    engine: str | None,
    offset: int,
    limit: int,
) -> dict:
    if not (1 <= limit <= 100 and 0 <= offset <= 1_000_000):
        raise ValueError("invalid pagination")
    if service not in {"ec2", "rds"}:
        raise ValueError("unsupported AWS calculator service")
    name = _ENGINES.get((engine or "").lower())
    if service == "rds" and not name:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "status": "unsupported_engine",
            "supported_engines": list(_ENGINES),
        }
    product = AwsPricingProduct
    instance = product.product_attributes["instanceType"].as_string()
    variant = (
        product.product_attributes["operatingSystem"].as_string()
        if service == "ec2"
        else product.product_attributes["deploymentOption"].as_string()
    )
    q = [
        product.service == service,
        product.service_code == ("AmazonEC2" if service == "ec2" else "AmazonRDS"),
        product.region_code == region,
        product.product_family == ("Compute Instance" if service == "ec2" else "Database Instance"),
        product.status == "active",
        func.lower(instance).contains(search.lower(), autoescape=True),
    ]
    if service == "ec2":
        q.extend(
            (
                product.product_attributes["tenancy"].as_string() == "Shared",
                or_(
                    product.product_attributes["preInstalledSw"].as_string().is_(None),
                    product.product_attributes["preInstalledSw"].as_string().in_(("NA", "None")),
                ),
                or_(
                    product.product_attributes["capacitystatus"].as_string().is_(None),
                    product.product_attributes["capacitystatus"].as_string() == "Used",
                ),
                product.product_attributes["operation"].as_string().startswith("RunInstances"),
                variant.in_(("Linux", "Windows")),
            )
        )
    else:
        model = product.product_attributes["deploymentModel"].as_string()
        license_model = product.product_attributes["licenseModel"].as_string()
        edition = product.product_attributes["databaseEdition"].as_string()
        q.extend(
            (
                product.product_attributes["databaseEngine"].as_string() == name,
                variant.in_(("Single-AZ", "Multi-AZ")),
                or_(model.is_(None), ~model.in_(("Custom", "Multi-AZ DB cluster"))),
                or_(
                    license_model.is_(None),
                    func.lower(license_model).in_(("no license required", "license included")),
                ),
                or_(
                    edition.is_(None),
                    ~func.lower(edition).in_(
                        ("enterprise", "standard edition 2", "web", "express")
                    ),
                ),
            )
        )

    now = datetime.now(UTC)
    price_exists = (
        select(PricingCatalogItem.id)
        .join(
            AwsPricingRateDetail,
            AwsPricingRateDetail.pricing_item_id == PricingCatalogItem.id,
        )
        .where(
            AwsPricingRateDetail.product_id == product.id,
            AwsPricingRateDetail.purchase_option == "on_demand",
            AwsPricingRateDetail.pricing_status == "active",
            AwsPricingRateDetail.begin_range == "0",
            AwsPricingRateDetail.end_range == "Inf",
            PricingCatalogItem.provider == "aws",
            PricingCatalogItem.service == service,
            PricingCatalogItem.region_code == region,
            PricingCatalogItem.currency == "USD",
            PricingCatalogItem.unit == "INSTANCE_HOUR",
            PricingCatalogItem.enabled.is_(True),
            PricingCatalogItem.effective_from <= now,
            or_(
                PricingCatalogItem.effective_until.is_(None),
                PricingCatalogItem.effective_until > now,
            ),
        )
        .correlate(product)
        .exists()
    )
    # Group and paginate at SQL level; never load a region's SKU catalog into Python.
    statement = (
        select(
            instance.label("instance_type"),
            variant.label("variant"),
            func.max(case((price_exists, 1), else_=0)).label("has_price"),
        )
        .where(*q)
        .group_by(instance, variant)
        .order_by(instance, variant)
    )
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    results = db.execute(statement.offset(offset).limit(limit)).all()
    items = []
    for instance_type, raw_variant, has_price in results:
        variant_value = (
            raw_variant.lower()
            if service == "ec2"
            else "single_az"
            if raw_variant == "Single-AZ"
            else "multi_az"
        )
        entry = (
            {"instance_type": instance_type, "operating_system": variant_value}
            if service == "ec2"
            else {"instance_class": instance_type, "deployment": variant_value}
        )
        entry["pricing_status"] = "priced" if has_price else "price_not_effective"
        items.append(entry)
    return {
        "service": service,
        "region": region,
        "source": "AWS_REGIONAL_CATALOG",
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "status": "ok" if total else "no_results",
        "supported_engines": list(_ENGINES) if service == "rds" else [],
    }
