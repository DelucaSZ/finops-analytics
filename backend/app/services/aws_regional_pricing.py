"""Persistent AWS regional price repository. No network calls or consumer cutover.

The importer (28.3) must call these methods inside a caller-owned transaction.
Validation is fail-closed; no money, region, or missing rate is ever inferred.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.aws_pricing import (
    AwsPricingImportBatch,
    AwsPricingProduct,
    AwsPricingRateDetail,
    AwsPricingSyncState,
)
from app.models.pricing import PricingCatalogItem
from app.models.pricing_audit import PricingAuditEvent

AwsPriceStatus = Literal[
    "priced",
    "sku_missing",
    "price_not_effective",
    "pricing_configuration_error",
    "sync_required",
]

_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
# Extensible validation registry. The importer must explicitly map AWS attributes
# that influence financial identity; unknown keys do not silently become selectors.
_FINANCIAL_FIELDS = frozenset(
    {
        "instanceType",
        "operatingSystem",
        "tenancy",
        "capacitystatus",
        "preInstalledSw",
        "operation",
        "purchaseOption",
        "productFamily",
        "databaseEngine",
        "databaseEdition",
        "deploymentOption",
        "deploymentModel",
        "licenseModel",
        "storageType",
        "volumeApiName",
        "usagetype",
        "usageType",
        "volumeType",
        "iops",
        "throughput",
        "capacity",
        "snapshotType",
        "locationType",
        "group",
        "groupDescription",
        "loadBalancerType",
        "servicecode",
        "fromLocation",
        "toLocation",
        "transferType",
        "physicalProcessor",
        "processorArchitecture",
    }
)
_REQUIRED = {
    "ec2": frozenset({"instanceType", "operatingSystem", "tenancy", "operation"}),
    "rds": frozenset({"instanceType", "databaseEngine", "deploymentOption"}),
    "ebs": frozenset({"usagetype"}),
}
_ALLOWED_SERVICES = frozenset(
    {
        "ec2",
        "rds",
        "ebs",
        "snapshot",
        "ipv4",
        "alb",
        "nlb",
        "clb",
    }
)


class AwsPricingValidationError(ValueError):
    """Invalid AWS catalog identity or monetary input."""


class AwsPricingConflictError(RuntimeError):
    """A conflicting product or rate version cannot be published."""


@dataclass(frozen=True, slots=True)
class AwsRegionalPriceResolution:
    status: AwsPriceStatus
    service: str
    service_code: str
    region_code: str
    reference_at: datetime
    catalog_item_id: str | None = None
    product_sku: str | None = None
    rate_code: str | None = None
    billing_unit: str | None = None
    unit_price: Decimal | None = None
    currency: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    source: str | None = None
    version: str | None = None
    import_batch_id: str | None = None
    synced_at: datetime | None = None
    matched_attributes: Mapping[str, str] | None = None
    warning_code: str | None = None


def _required(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise AwsPricingValidationError(f"{name} must be a non-empty string of at most {maximum}")
    return value.strip()


def _region(region_code: str) -> str:
    result = _required(region_code, "region_code", 40)
    if not _REGION.fullmatch(result):
        raise AwsPricingValidationError("invalid AWS region code")
    return result


def _date(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AwsPricingValidationError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _stored_date(value: datetime) -> datetime:
    """SQLite loses timezone metadata; stored UTC timestamps stay UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _attributes(service: str, attributes: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(attributes, Mapping) or not attributes:
        raise AwsPricingValidationError("financial_attributes must be a non-empty mapping")
    result = {}
    for key, value in attributes.items():
        if not isinstance(key, str) or not _FIELD.fullmatch(key):
            raise AwsPricingValidationError("invalid AWS financial attribute name")
        if key not in _FINANCIAL_FIELDS:
            raise AwsPricingValidationError(f"unsupported AWS financial attribute: {key}")
        result[key] = _required(value, key, 256)
    required = _REQUIRED.get(service, frozenset())
    # RDS storage/performance SKUs have no instanceType; they are not DB instance SKUs.
    if service == "rds" and result.get("productFamily") != "Database Instance":
        required = frozenset({"usagetype"})
    if not required.issubset(result):
        raise AwsPricingValidationError(f"incomplete AWS {service} financial attributes")
    return dict(sorted(result.items()))


def _fingerprint(attributes: Mapping[str, str]) -> str:
    data = json.dumps(attributes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise AwsPricingValidationError("unit price must be a finite nonnegative Decimal")
    # The shared OCI catalog is NUMERIC(20,8). Reject, rather than round,
    # official AWS dimensions that exceed this precision until a safe scale migration.
    if value != value.quantize(Decimal("0.00000001")):
        raise AwsPricingValidationError("unit price exceeds catalog precision of 8 decimals")
    if value >= Decimal("1000000000000"):
        raise AwsPricingValidationError("unit price exceeds catalog numeric precision")
    return value


def _snapshot(item: PricingCatalogItem) -> dict[str, str | bool | None]:
    return {
        "id": item.id,
        "region_code": item.region_code,
        "price": format(Decimal(item.price), "f"),
        "currency": item.currency,
        "source": item.source,
        "effective_from": item.effective_from.isoformat(),
        "effective_until": item.effective_until.isoformat() if item.effective_until else None,
        "enabled": item.enabled,
    }


class AwsRegionalPricingRepository:
    """Transactional writes and paged reads for AWS regional catalog metadata.

    Commit/rollback belongs to the caller. Advisory locks plus database exclusion
    constraints guarantee non-overlapping published AWS terms in PostgreSQL.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _lock(self, key: str) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "aven:aws-price:" + key},
            )

    def get_or_create_batch(
        self,
        *,
        service_code: str,
        region_code: str,
        source_version: str,
        checksum: str,
        source_type: str,
        source_uri: str | None = None,
    ) -> AwsPricingImportBatch:
        code = _required(service_code, "service_code", 80)
        region = _region(region_code)
        version = _required(source_version, "source_version", 160)
        digest = _required(checksum, "checksum", 128)
        source = _required(source_type, "source_type", 64)
        self._lock(f"batch:{code}:{region}:{version}:{digest}")
        batch = self.db.scalar(
            select(AwsPricingImportBatch).where(
                AwsPricingImportBatch.service_code == code,
                AwsPricingImportBatch.region_code == region,
                AwsPricingImportBatch.source_version == version,
                AwsPricingImportBatch.checksum == digest,
            )
        )
        if batch:
            return batch
        batch = AwsPricingImportBatch(
            service_code=code,
            region_code=region,
            source_version=version,
            checksum=digest,
            source_type=source,
            source_uri=source_uri,
            status="running",
            started_at=utcnow(),
            products_seen=0,
            rates_seen=0,
            rates_rejected=0,
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def put_product(
        self,
        *,
        service: str,
        service_code: str,
        region_code: str,
        product_sku: str,
        product_family: str,
        description: str,
        financial_attributes: Mapping[str, str],
        product_attributes: Mapping[str, str] | None = None,
    ) -> AwsPricingProduct:
        normalized_service = _required(service, "service", 64).lower()
        if normalized_service not in _ALLOWED_SERVICES:
            raise AwsPricingValidationError("unsupported normalized AWS service")
        code = _required(service_code, "service_code", 80)
        region = _region(region_code)
        sku = _required(product_sku, "product_sku", 160)
        family = _required(product_family, "product_family", 120)
        desc = _required(description, "description", 500)
        identity = _attributes(normalized_service, financial_attributes)
        raw = dict(product_attributes or identity)
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in raw.items()):
            raise AwsPricingValidationError("product_attributes must contain string pairs")
        digest = _fingerprint(identity)
        self._lock(f"product:{code}:{region}:{sku}")
        existing = self.db.scalar(
            select(AwsPricingProduct).where(
                AwsPricingProduct.service_code == code,
                AwsPricingProduct.region_code == region,
                AwsPricingProduct.product_sku == sku,
            )
        )
        if existing:
            if (
                existing.service != normalized_service
                or existing.attribute_hash != digest
                or existing.financial_attributes != identity
                or existing.product_family != family
            ):
                raise AwsPricingConflictError("product identity changed for the same AWS SKU")
            return existing
        product = AwsPricingProduct(
            service=normalized_service,
            service_code=code,
            region_code=region,
            product_sku=sku,
            product_family=family,
            description=desc,
            product_attributes=raw,
            financial_attributes=identity,
            attribute_hash=digest,
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        return product

    def put_rate(
        self,
        *,
        product: AwsPricingProduct,
        rate_code: str,
        term_code: str,
        billing_unit: str,
        aws_unit: str,
        amount: Decimal,
        effective_from: datetime,
        source: str,
        source_effective_at: datetime,
        purchase_option: str = "on_demand",
        begin_range: str = "0",
        end_range: str = "Inf",
        rate_description: str = "",
        pricing_status: str = "active",
        import_batch: AwsPricingImportBatch | None = None,
    ) -> PricingCatalogItem:
        code = _required(rate_code, "rate_code", 180)
        term = _required(term_code, "term_code", 180)
        unit = _required(billing_unit, "billing_unit", 32).upper()
        aws_billing_unit = _required(aws_unit, "aws_unit", 64)
        option = _required(purchase_option, "purchase_option", 32).lower()
        if option not in {"on_demand", "reserved", "savings_plan"}:
            raise AwsPricingValidationError("unsupported purchase_option")
        if pricing_status not in {"active", "unsupported", "quarantined", "withdrawn"}:
            raise AwsPricingValidationError("invalid pricing_status")
        start = _date(effective_from, "effective_from")
        source_at = _date(source_effective_at, "source_effective_at")
        source_name = _required(source, "source", 80).upper()
        price = _money(amount)
        begin = _required(begin_range, "begin_range", 80)
        end = _required(end_range, "end_range", 80)
        if (begin != "0" or end != "Inf") and pricing_status == "active":
            raise AwsPricingValidationError("tiered AWS rates cannot be active linear rates")
        if product.id is None or product.status != "active":
            raise AwsPricingValidationError("product must be a persisted, active AWS product")
        if import_batch is not None and (
            import_batch.region_code != product.region_code
            or import_batch.service_code != product.service_code
        ):
            raise AwsPricingValidationError("import batch region/service mismatch")
        # Catalog SKU includes AWS product SKU and rate dimension code, not a friendly name.
        sku = f"{product.product_sku}:{code}"
        if len(sku) > 160:
            raise AwsPricingValidationError("AWS composite SKU exceeds shared catalog limit")
        is_active = pricing_status == "active"
        digest = _fingerprint(
            {
                "amount": format(price, "f"),
                "code": code,
                "term": term,
                "unit": unit,
                "aws_unit": aws_billing_unit,
                "option": option,
                "range": f"{begin}:{end}",
                "source": source_name,
            }
        )
        key = f"{product.service}:{product.region_code}:{sku}:{unit}"
        self._lock(key)
        rows = list(
            self.db.scalars(
                select(PricingCatalogItem)
                .where(
                    PricingCatalogItem.provider == "aws",
                    PricingCatalogItem.service == product.service,
                    PricingCatalogItem.region_code == product.region_code,
                    PricingCatalogItem.sku == sku,
                    PricingCatalogItem.unit == unit,
                )
                .order_by(PricingCatalogItem.effective_from.desc())
                .with_for_update()
            )
        )
        for item in rows:
            if _stored_date(item.effective_from) != start:
                continue
            detail = self.db.scalar(
                select(AwsPricingRateDetail).where(AwsPricingRateDetail.pricing_item_id == item.id)
            )
            if (
                detail is not None
                and detail.product_id == product.id
                and detail.source_hash == digest
                and item.price == price
                and item.currency == "USD"
                and detail.pricing_status == pricing_status
                and item.enabled == is_active
            ):
                return item
            raise AwsPricingConflictError("same rate identity and start has conflicting data")
        if rows and rows[0].enabled and is_active:
            # Do not manufacture a financial version when only the official
            # source publication changes but the actual rate stays constant.
            current = rows[0]
            current_detail = self.db.scalar(
                select(AwsPricingRateDetail).where(
                    AwsPricingRateDetail.pricing_item_id == current.id
                )
            )
            if (
                current_detail is not None
                and current_detail.product_id == product.id
                and current_detail.source_hash == digest
                and current_detail.pricing_status == pricing_status
                and current.price == price
                and current.currency == "USD"
                and (current.effective_until is None or start < _stored_date(current.effective_until))
            ):
                return current
        if rows and start <= _stored_date(rows[0].effective_from):
            raise AwsPricingConflictError(
                "backdated publication requires an explicit reconciliation"
            )
        if rows and rows[0].enabled:
            previous = rows[0]
            if previous.effective_until is not None and start >= _date(
                previous.effective_until, "stored effective_until"
            ):
                previous = None
            if previous is not None:
                before = _snapshot(previous)
                previous.effective_until = start
                self.db.flush()
                self._audit(previous, "VALIDITY_CHANGED", before, _snapshot(previous))
        item = PricingCatalogItem(
            provider="aws",
            service=product.service,
            region_code=product.region_code,
            sku=sku,
            description=(rate_description.strip() or product.description)[:255],
            unit=unit,
            price=price,
            currency="USD",
            effective_from=start,
            effective_until=None,
            enabled=is_active,
            source=source_name,
        )
        self.db.add(item)
        self.db.flush()
        detail = AwsPricingRateDetail(
            pricing_item_id=item.id,
            product_id=product.id,
            rate_code=code,
            term_code=term,
            purchase_option=option,
            billing_unit_aws=aws_billing_unit,
            begin_range=begin,
            end_range=end,
            rate_description=rate_description.strip() or product.description,
            pricing_status=pricing_status,
            import_batch_id=import_batch.id if import_batch else None,
            source_effective_at=source_at,
            synced_at=utcnow(),
            source_hash=digest,
        )
        self.db.add(detail)
        self._audit(item, "IMPORTED", None, _snapshot(item), import_batch)
        self.db.flush()
        return item

    def _audit(
        self,
        item: PricingCatalogItem,
        action: str,
        before: dict | None,
        after: dict | None,
        batch: AwsPricingImportBatch | None = None,
    ) -> None:
        self.db.add(
            PricingAuditEvent(
                pricing_item_id=item.id,
                provider="aws",
                service=item.service,
                region_code=item.region_code,
                sku=item.sku,
                unit=item.unit,
                import_batch_id=batch.id if batch else None,
                action=action,
                actor_type="SYSTEM",
                reason="AWS regional catalog version publication",
                before_data=before,
                after_data=after,
            )
        )

    def list_products(
        self,
        *,
        service: str,
        region_code: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AwsPricingProduct]:
        region = _region(region_code)
        if not (1 <= limit <= 1000 and offset >= 0):
            raise AwsPricingValidationError("invalid pagination")
        return list(
            self.db.scalars(
                select(AwsPricingProduct)
                .where(
                    AwsPricingProduct.service == service,
                    AwsPricingProduct.region_code == region,
                )
                .order_by(AwsPricingProduct.product_sku, AwsPricingProduct.id)
                .offset(offset)
                .limit(limit)
            )
        )

    def rate_history(
        self,
        *,
        service: str,
        region_code: str,
        product_sku: str,
        rate_code: str,
        billing_unit: str,
    ) -> list[PricingCatalogItem]:
        region = _region(region_code)
        return list(
            self.db.scalars(
                select(PricingCatalogItem)
                .join(
                    AwsPricingRateDetail,
                    AwsPricingRateDetail.pricing_item_id == PricingCatalogItem.id,
                )
                .join(
                    AwsPricingProduct,
                    AwsPricingRateDetail.product_id == AwsPricingProduct.id,
                )
                .where(
                    PricingCatalogItem.provider == "aws",
                    PricingCatalogItem.service == service,
                    PricingCatalogItem.region_code == region,
                    AwsPricingProduct.product_sku == product_sku,
                    AwsPricingRateDetail.rate_code == rate_code,
                    PricingCatalogItem.unit == billing_unit,
                )
                .order_by(PricingCatalogItem.effective_from.desc())
            )
        )

    def get_sync_state(
        self,
        *,
        service_code: str,
        region_code: str,
    ) -> AwsPricingSyncState | None:
        return self.db.scalar(
            select(AwsPricingSyncState).where(
                AwsPricingSyncState.service_code == service_code,
                AwsPricingSyncState.region_code == _region(region_code),
            )
        )

    def set_sync_state(
        self,
        *,
        service_code: str,
        region_code: str,
        status: str,
        batch: AwsPricingImportBatch | None = None,
        coverage: dict | None = None,
    ) -> AwsPricingSyncState:
        if status not in {"never_synced", "synced", "partial", "stale", "failed"}:
            raise AwsPricingValidationError("invalid sync status")
        if status == "synced" and (batch is None or batch.status != "published"):
            raise AwsPricingValidationError("synced requires a published import batch")
        code = _required(service_code, "service_code", 80)
        region = _region(region_code)
        if batch is not None and (batch.service_code != code or batch.region_code != region):
            raise AwsPricingValidationError("sync batch service/region mismatch")
        self._lock(f"sync:{code}:{region}")
        state = self.get_sync_state(service_code=code, region_code=region)
        if state is None:
            state = AwsPricingSyncState(
                service_code=code,
                region_code=region,
                coverage_status="never_synced",
                schema_version=1,
            )
            self.db.add(state)
        state.coverage_status = status
        state.last_attempt_at = utcnow()
        if status == "synced" and batch is not None and batch.status == "published":
            state.last_successful_batch_id = batch.id
            state.last_success_at = utcnow()
        if coverage is not None:
            state.coverage = coverage
        self.db.flush()
        return state


class AwsRegionalPricingResolver:
    """Strict exact-configuration, time-qualified, local PostgreSQL lookup."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_aws_price(
        self,
        *,
        service: str,
        service_code: str,
        region_code: str,
        configuration: Mapping[str, str],
        billing_unit: str,
        reference_at: datetime,
        purchase_option: str = "on_demand",
    ) -> AwsRegionalPriceResolution:
        service = _required(service, "service", 64).lower()
        if service not in _ALLOWED_SERVICES:
            raise AwsPricingValidationError("unsupported normalized AWS service")
        code = _required(service_code, "service_code", 80)
        region = _region(region_code)
        unit = _required(billing_unit, "billing_unit", 32).upper()
        at = _date(reference_at, "reference_at")
        attributes = _attributes(service, configuration)
        base = dict(
            service=service,
            service_code=code,
            region_code=region,
            reference_at=at,
        )

        def missing(status: AwsPriceStatus, reason: str) -> AwsRegionalPriceResolution:
            return AwsRegionalPriceResolution(status=status, warning_code=reason, **base)

        sync = AwsRegionalPricingRepository(self.db).get_sync_state(
            service_code=code, region_code=region
        )
        if (
            sync is None
            or sync.coverage_status == "never_synced"
            or (sync.coverage_status == "failed" and sync.last_successful_batch_id is None)
        ):
            return missing("sync_required", "aws_region_catalog_not_synchronized")
        products = list(
            self.db.scalars(
                select(AwsPricingProduct).where(
                    AwsPricingProduct.service == service,
                    AwsPricingProduct.service_code == code,
                    AwsPricingProduct.region_code == region,
                    AwsPricingProduct.attribute_hash == _fingerprint(attributes),
                    AwsPricingProduct.status == "active",
                )
            )
        )
        products = [p for p in products if p.financial_attributes == attributes]
        if not products:
            return missing(
                "sync_required" if sync.coverage_status in {"partial", "stale"} else "sku_missing",
                "aws_regional_product_absent",
            )
        product_ids = [p.id for p in products]
        rows = self.db.execute(
            select(PricingCatalogItem, AwsPricingRateDetail, AwsPricingProduct)
            .join(
                AwsPricingRateDetail,
                AwsPricingRateDetail.pricing_item_id == PricingCatalogItem.id,
            )
            .join(
                AwsPricingProduct,
                AwsPricingProduct.id == AwsPricingRateDetail.product_id,
            )
            .where(
                AwsPricingRateDetail.product_id.in_(product_ids),
                PricingCatalogItem.provider == "aws",
                PricingCatalogItem.service == service,
                PricingCatalogItem.region_code == region,
                PricingCatalogItem.unit == unit,
                AwsPricingRateDetail.purchase_option == purchase_option,
            )
        ).all()
        active = [
            (item, detail, product)
            for item, detail, product in rows
            if item.enabled
            and detail.pricing_status == "active"
            and detail.begin_range == "0"
            and detail.end_range == "Inf"
        ]
        effective = [
            (item, detail, product)
            for item, detail, product in active
            if _stored_date(item.effective_from) <= at
            and (item.effective_until is None or at < _stored_date(item.effective_until))
        ]
        if not effective:
            if active:
                return missing("price_not_effective", "aws_rate_not_effective_at_reference")
            if rows:
                return missing("pricing_configuration_error", "aws_rate_not_publishable")
            return missing(
                "sync_required" if sync.coverage_status in {"partial", "stale"} else "sku_missing",
                "aws_rate_dimension_missing",
            )
        if len(effective) != 1:
            return missing("pricing_configuration_error", "aws_rate_ambiguous")
        item, detail, product = effective[0]
        if item.currency != "USD" or detail.product_id != product.id:
            return missing("pricing_configuration_error", "aws_rate_integrity_error")
        return AwsRegionalPriceResolution(
            status="priced",
            catalog_item_id=item.id,
            product_sku=product.product_sku,
            rate_code=detail.rate_code,
            billing_unit=item.unit,
            unit_price=Decimal(item.price),
            currency=item.currency,
            effective_from=item.effective_from,
            effective_until=item.effective_until,
            source=item.source,
            version=item.id,
            import_batch_id=detail.import_batch_id,
            synced_at=detail.synced_at,
            matched_attributes=dict(product.financial_attributes),
            **base,
        )
