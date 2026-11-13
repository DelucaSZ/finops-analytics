"""Read-only bridge from the published AWS regional catalog to CalculatorPriceLookup.

The calculator never queries AWS APIs or makes a replacement public-price estimate.
Financial identity comes from the imported product's *complete* normalized attributes,
then the strict temporal resolver checks the published rate.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aws_pricing import AwsPricingProduct
from app.services.aws_calculator_pricing import missing_aws_lookup
from app.services.aws_regional_pricing import (
    AwsRegionalPricingRepository,
    AwsRegionalPricingResolver,
)
from app.services.calculator_foundation import CalculatorPriceLookup
from app.services.pricing_catalog import PricingIdentity, ResolvedPrice

_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
_MAX_CANDIDATES = 50


class AwsLocalCalculatorResolver:
    """A minimal, fail-closed adapter for the existing EC2/RDS metering policies."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.regional = AwsRegionalPricingResolver(db)
        self.repository = AwsRegionalPricingRepository(db)
        self.warnings: list[str] = []

    def _missing(
        self, service: str, region: str, key: str, unit: str, at: datetime,
        status: str, warning: str,
    ) -> CalculatorPriceLookup:
        return missing_aws_lookup(service, region, key, unit, at, status, warning)

    def resolve(
        self,
        *,
        service: str,
        region: str,
        family: str,
        filters: dict[str, str],
        matches,
        unit: str,
        aws_unit: str,
        at: datetime,
        key: str,
    ) -> CalculatorPriceLookup:
        if not _REGION.fullmatch(region):
            return self._missing(service, region, key, unit, at, "invalid_combination", "invalid_aws_region")
        if at.tzinfo is None:
            raise ValueError("pricing reference must be timezone-aware")
        at = at.astimezone(UTC)
        code = "AmazonEC2" if service == "ec2" else "AmazonRDS"
        target_service = "ebs" if service == "ec2" and family != "Compute Instance" else service

        sync = self.repository.get_sync_state(service_code=code, region_code=region)
        if sync is not None and sync.coverage_status in {"stale", "partial", "failed"}:
            # A last-good published tariff is not invalidated by a failed later sync.
            if sync.last_successful_batch_id is not None:
                self.warnings.append("aws_region_catalog_" + sync.coverage_status)

        statement = select(AwsPricingProduct).where(
            AwsPricingProduct.service == target_service,
            AwsPricingProduct.service_code == code,
            AwsPricingProduct.region_code == region,
            AwsPricingProduct.product_family == family,
            AwsPricingProduct.status == "active",
        )
        for field, value in filters.items():
            if field.startswith("contains:"):
                column = AwsPricingProduct.product_attributes[field.removeprefix("contains:")].as_string()
                statement = statement.where(column.contains(value, autoescape=True))
            else:
                # Strict product qualification is done in SQL, not by loading all SKUs.
                column = AwsPricingProduct.financial_attributes[field].as_string()
                statement = statement.where(column == value)
        if service == "ec2" and family == "Compute Instance":
            statement = statement.where(
                AwsPricingProduct.financial_attributes["operation"].as_string().startswith("RunInstances")
            )
        if service == "rds" and family == "Database Instance":
            statement = statement.where(
                AwsPricingProduct.financial_attributes["deploymentModel"].as_string().is_(None)
                | ~AwsPricingProduct.financial_attributes["deploymentModel"].as_string().in_(
                    ("Custom", "Multi-AZ DB cluster")
                )
            )
        rows = list(self.db.scalars(statement.limit(_MAX_CANDIDATES + 1)))
        if len(rows) > _MAX_CANDIDATES:
            return self._missing(
                target_service, region, key, unit, at,
                "pricing_configuration_error", "aws_catalog_product_match_limit",
            )
        candidates = [p for p in rows if matches(p.product_attributes)]
        if not candidates:
            needs_sync = (
                sync is None
                or sync.coverage_status == "never_synced"
                or (
                    sync.coverage_status in {"failed", "partial", "stale"}
                    and sync.last_successful_batch_id is None
                )
            )
            return self._missing(
                target_service, region, key, unit, at,
                "sync_required" if needs_sync else "sku_missing",
                "aws_region_catalog_not_synchronized" if needs_sync else f"aws_{service}_{key}_price_unavailable",
            )
        if len(candidates) != 1:
            return self._missing(
                target_service, region, key, unit, at,
                "pricing_configuration_error", f"aws_{service}_{key}_ambiguous_product",
            )

        product = candidates[0]
        # Never reconstruct a partial identity from instanceType alone.
        resolved = self.regional.resolve_aws_price(
            service=product.service,
            service_code=product.service_code,
            region_code=region,
            configuration=product.financial_attributes,
            billing_unit=unit,
            reference_at=at,
            purchase_option="on_demand",
        )
        if resolved.status != "priced":
            return self._missing(
                product.service, region, key, unit, at,
                resolved.status, resolved.warning_code or resolved.status,
            )
        if (
            resolved.unit_price is None or resolved.catalog_item_id is None
            or not resolved.product_sku or not resolved.rate_code
            or resolved.currency != "USD" or resolved.billing_unit != unit
            or resolved.effective_from is None or resolved.source is None
        ):
            return self._missing(
                product.service, region, key, unit, at,
                "pricing_configuration_error", "aws_rate_integrity_error",
            )
        identity = PricingIdentity(
            "aws", product.service, f"{resolved.product_sku}:{resolved.rate_code}", unit
        )
        price = ResolvedPrice(
            id=resolved.catalog_item_id,
            provider="aws",
            service=product.service,
            sku=identity.sku,
            description=product.description,
            unit=unit,
            amount=resolved.unit_price,
            currency="USD",
            effective_from=resolved.effective_from,
            effective_until=resolved.effective_until,
            source=resolved.source,
        )
        return CalculatorPriceLookup(
            identity=identity,
            status="priced",
            price=price,
            reference_at=at,
            region_code=region,
            product_sku=resolved.product_sku,
            rate_code=resolved.rate_code,
            import_batch_id=resolved.import_batch_id,
            synced_at=resolved.synced_at,
        )
