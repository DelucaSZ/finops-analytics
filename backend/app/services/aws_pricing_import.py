"""Task 28.3: controlled AWS official price ingestion into the 28.2 catalog.

Parsing and validation happen off-database. A bounded service/region publication is
atomic; a failed or partial attempt never removes or overwrites last-good prices.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.aws_pricing import AwsPricingProduct, AwsPricingRateDetail
from app.models.pricing import PricingCatalogItem
from app.services.aws_pricing_bulk import (
    AwsBulkImportError,
    PriceListReference,
    StageStats,
    discover_price_list,
    download_official_offer,
    iter_staged_rates,
    stage_offer,
)
from app.services.aws_regional_pricing import (
    AwsPricingConflictError,
    AwsRegionalPricingRepository,
)

logger = logging.getLogger(__name__)
_SOURCE = "AWS_PUBLIC_PRICE_LIST"
_FIXTURE = "TEST_FIXTURE"


@dataclass(frozen=True, slots=True)
class AwsImportResult:
    service_code: str
    region_code: str
    dry_run: bool
    status: str
    source_type: str
    source_version: str
    checksum: str
    batch_id: str | None
    products_seen: int
    products_matched: int
    rates_seen: int
    rates_staged: int
    rates_rejected: int
    rates_unsupported: int
    published_rates: int
    coverage: dict[str, Any]
    diagnostics: dict[str, Any]
    elapsed_seconds: float


def _result(
    service: str,
    region: str,
    dry_run: bool,
    status: str,
    source_type: str,
    stats: StageStats,
    *,
    batch_id: str | None = None,
    published_rates: int = 0,
    elapsed_seconds: float = 0,
    diagnostics: dict[str, Any] | None = None,
) -> AwsImportResult:
    return AwsImportResult(
        service_code=service,
        region_code=region,
        dry_run=dry_run,
        status=status,
        source_type=source_type,
        source_version=stats.source_version,
        checksum=stats.checksum,
        batch_id=batch_id,
        products_seen=stats.products_seen,
        products_matched=stats.products_matched,
        rates_seen=stats.rates_seen,
        rates_staged=stats.rates_staged,
        rates_rejected=stats.rates_rejected,
        rates_unsupported=stats.rates_unsupported,
        published_rates=published_rates,
        coverage=stats.coverage,
        diagnostics=diagnostics or {},
        elapsed_seconds=round(elapsed_seconds, 3),
    )


def _file_digest(path: Path, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(block)
            if total > max_bytes:
                raise AwsBulkImportError("fixture exceeds max_bytes")
            digest.update(block)
    if not total:
        raise AwsBulkImportError("empty fixture")
    return digest.hexdigest(), total


def _can_publish_partial(db: Session, service: str, region: str) -> bool:
    """Never replace an existing regional price set with an incomplete import."""
    return (
        db.scalar(
            select(PricingCatalogItem.id)
            .where(
                PricingCatalogItem.provider == "aws",
                PricingCatalogItem.region_code == region,
                PricingCatalogItem.service.in_(
                    {
                        "AmazonEC2": ("ec2", "ebs", "snapshot", "ipv4"),
                        "AmazonRDS": ("rds",),
                        "AWSELB": ("alb", "nlb", "clb"),
                        "AmazonVPC": ("ipv4",),
                    }[service]
                ),
            )
            .limit(1)
        )
        is None
    )


def _check_dry_run_conflicts(db: Session, staging: Path, limit: int = 100000) -> int:
    """Read-only exact SKU/rate/epoch comparison with pre-existing rows."""
    errors = 0
    for count, rate in enumerate(iter_staged_rates(staging), start=1):
        if count > limit:
            raise AwsBulkImportError("dry-run conflict-check limit exceeded")
        product = db.scalar(
            select(AwsPricingProduct).where(
                AwsPricingProduct.service_code == rate.product.service_code,
                AwsPricingProduct.region_code == rate.product.region,
                AwsPricingProduct.product_sku == rate.product.sku,
            )
        )
        if product is not None and (
            product.service != rate.product.service
            or product.financial_attributes != rate.product.financial_attributes
            or product.product_family != rate.product.family
        ):
            errors += 1
            continue
        sku = rate.product.sku + ":" + rate.rate_code
        row = db.execute(
            select(PricingCatalogItem, AwsPricingRateDetail)
            .join(
                AwsPricingRateDetail,
                AwsPricingRateDetail.pricing_item_id == PricingCatalogItem.id,
            )
            .where(
                PricingCatalogItem.provider == "aws",
                PricingCatalogItem.service == rate.product.service,
                PricingCatalogItem.region_code == rate.product.region,
                PricingCatalogItem.sku == sku,
                PricingCatalogItem.unit == rate.unit,
            )
            .order_by(PricingCatalogItem.effective_from.desc())
            .limit(1)
        ).first()
        if row:
            item, detail = row
            epoch = datetime.fromisoformat(rate.effective_at)
            original = item.effective_from
            if original.tzinfo is None:
                original = original.replace(tzinfo=UTC)
            if (
                original == epoch
                and (item.price != rate.amount or detail.rate_code != rate.rate_code)
            ) or epoch < original:
                errors += 1
    return errors


def _record_failure(
    db: Session,
    service: str,
    region: str,
    stats: StageStats,
    source_type: str,
    source_uri: str,
    reason: str,
) -> None:
    """Persist diagnostic status in its own transaction after a rollback."""
    try:
        with db.begin():
            repository = AwsRegionalPricingRepository(db)
            batch = repository.get_or_create_batch(
                service_code=service,
                region_code=region,
                source_version=stats.source_version,
                checksum=stats.checksum,
                source_type=source_type,
                source_uri=source_uri[:1000],
            )
            if batch.status == "published":
                return
            batch.status = "failed"
            batch.finished_at = utcnow()
            batch.products_seen = stats.products_seen
            batch.rates_seen = stats.rates_seen
            batch.rates_rejected = stats.rates_rejected
            batch.diagnostics = {"reason": reason[:300], "rejects": stats.rejects}
            state = repository.get_sync_state(service_code=service, region_code=region)
            if state is None or state.last_successful_batch_id is None:
                repository.set_sync_state(
                    service_code=service,
                    region_code=region,
                    status="failed",
                    coverage=stats.coverage,
                )
            else:
                state.last_attempt_at = utcnow()
                state.error_summary = reason[:500]
    except Exception as exc:
        db.rollback()
        logger.error("aws_price_import_failure_audit_unavailable reason=%s", type(exc).__name__)


def import_aws_prices(
    *,
    service_code: str,
    region_code: str,
    db: Session | None = None,
    dry_run: bool = True,
    allow_partial: bool = False,
    effective_at: datetime | None = None,
    fixture_path: Path | None = None,
    max_bytes: int = 2_000_000_000,
    max_products: int = 1_000_000,
    max_rates: int = 1_000_000,
    endpoint_region: str = "us-east-1",
    reference: PriceListReference | None = None,
    client=None,
) -> AwsImportResult:
    """Import one official service+region. Caller supplies an idle SQLAlchemy session.

    Offline fixture mode is explicitly distinguished from real AWS downloads.
    No endpoint, UI, scheduler or customer account credentials are involved.
    """
    start = time.monotonic()
    if reference is not None and (
        fixture_path is not None
        or reference.service_code != service_code
        or reference.region_code != region_code
    ):
        raise AwsBulkImportError("official price-list reference does not match service/region")
    if not dry_run and db is None:
        raise AwsBulkImportError("database session required for publication")
    if allow_partial and dry_run:
        # Dry-run may report incomplete coverage without pretending publication.
        allow_partial = False
    with tempfile.TemporaryDirectory(prefix="aven-aws-prices-") as tmp:
        directory = Path(tmp)
        source = directory / "official-offer.json"
        staging = directory / "staged.sqlite"
        source_type = _FIXTURE if fixture_path else _SOURCE
        download_started = time.monotonic()
        if fixture_path is not None:
            checksum, size = _file_digest(fixture_path, max_bytes)
            source = fixture_path
            source_uri = "offline-fixture"
        else:
            if reference is None:
                reference = discover_price_list(
                    service_code,
                    region_code,
                    effective_at=effective_at,
                    endpoint_region=endpoint_region,
                    client=client,
                )
            checksum, size = download_official_offer(reference, source, max_bytes=max_bytes)
            source_uri = reference.url
        download_seconds = time.monotonic() - download_started
        parse_started = time.monotonic()
        stats = stage_offer(
            source,
            staging,
            service_code=service_code,
            region=region_code,
            max_products=max_products,
            max_rates=max_rates,
        )
        parse_seconds = time.monotonic() - parse_started
        stats.checksum = checksum
        stats.source_bytes = size
        complete = stats.coverage["complete"] and stats.rates_rejected == 0
        diagnostics = {
            "source_bytes": size,
            "download_seconds": round(download_seconds, 3),
            "parse_seconds": round(parse_seconds, 3),
            "format": stats.format_version,
            "publication_date": stats.publication_date,
            "rejects": stats.rejects,
            "examples": stats.examples,
            "coverage_complete": complete,
            "official_arn": reference.arn if reference else None,
        }
        if db is not None and dry_run:
            conflicts = _check_dry_run_conflicts(db, staging, limit=max_rates)
            diagnostics["conflicts"] = conflicts
        elif dry_run:
            diagnostics["conflicts_checked"] = False
        if dry_run:
            return _result(
                service_code,
                region_code,
                True,
                "validated" if complete and not diagnostics.get("conflicts") else "partial",
                source_type,
                stats,
                diagnostics=diagnostics,
                elapsed_seconds=time.monotonic() - start,
            )
        assert db is not None
        batch_id = None
        published = 0
        try:
            persistence_started = time.monotonic()
            with db.begin():
                repository = AwsRegionalPricingRepository(db)
                # Lock the whole service+region before checking coverage or status.
                repository._lock(f"publication:{service_code}:{region_code}")
                batch = repository.get_or_create_batch(
                    service_code=service_code,
                    region_code=region_code,
                    source_version=stats.source_version,
                    checksum=stats.checksum,
                    source_type=source_type,
                    source_uri=source_uri[:1000],
                )
                batch_id = batch.id
                if batch.status == "published":
                    return _result(
                        service_code,
                        region_code,
                        False,
                        "already_published",
                        source_type,
                        stats,
                        batch_id=batch_id,
                        diagnostics=diagnostics,
                        elapsed_seconds=time.monotonic() - start,
                    )
                batch.products_seen = stats.products_seen
                batch.rates_seen = stats.rates_seen
                batch.rates_rejected = stats.rates_rejected
                batch.diagnostics = diagnostics
                batch.checkpoint = {"source_version": stats.source_version, "rows": 0}
                if not complete and not (
                    allow_partial and _can_publish_partial(db, service_code, region_code)
                ):
                    batch.status = "partial"
                    batch.finished_at = utcnow()
                    existing = repository.get_sync_state(
                        service_code=service_code, region_code=region_code
                    )
                    if existing is None or existing.last_successful_batch_id is None:
                        repository.set_sync_state(
                            service_code=service_code,
                            region_code=region_code,
                            status="partial",
                            coverage=stats.coverage,
                        )
                    return _result(
                        service_code,
                        region_code,
                        False,
                        "partial",
                        source_type,
                        stats,
                        batch_id=batch_id,
                        diagnostics=diagnostics,
                        elapsed_seconds=time.monotonic() - start,
                    )
                if not stats.rates_staged:
                    raise AwsBulkImportError("no validated On-Demand rates to publish")
                # Service+region is a bounded transaction, never all-AWS.
                for rate in iter_staged_rates(staging):
                    product = repository.put_product(
                        service=rate.product.service,
                        service_code=service_code,
                        region_code=region_code,
                        product_sku=rate.product.sku,
                        product_family=rate.product.family,
                        description=rate.product.description,
                        financial_attributes=rate.product.financial_attributes,
                        product_attributes=rate.product.attributes,
                    )
                    repository.put_rate(
                        product=product,
                        rate_code=rate.rate_code,
                        term_code=rate.term_code,
                        billing_unit=rate.unit,
                        aws_unit=rate.aws_unit,
                        amount=rate.amount,
                        effective_from=datetime.fromisoformat(rate.effective_at),
                        source=source_type,
                        source_effective_at=datetime.fromisoformat(rate.effective_at),
                        begin_range=rate.begin_range,
                        end_range=rate.end_range,
                        rate_description=rate.description,
                        pricing_status=rate.pricing_status,
                        import_batch=batch,
                    )
                    published += 1
                    if published % 500 == 0:
                        db.flush()
                        batch.checkpoint = {
                            "source_version": stats.source_version,
                            "rows": published,
                        }
                batch.status = "published"
                batch.finished_at = utcnow()
                batch.published_at = utcnow()
                batch.checkpoint = {"source_version": stats.source_version, "rows": published}
                diagnostics["persistence_seconds"] = round(
                    time.monotonic() - persistence_started, 3
                )
                batch.diagnostics = dict(diagnostics)
                repository.set_sync_state(
                    service_code=service_code,
                    region_code=region_code,
                    status="synced" if complete else "partial",
                    batch=batch,
                    coverage=stats.coverage,
                )
            logger.info(
                "aws_bulk_import_published service=%s region=%s version=%s rates=%s complete=%s",
                service_code,
                region_code,
                stats.source_version,
                published,
                complete,
            )
            return _result(
                service_code,
                region_code,
                False,
                "published" if complete else "published_partial",
                source_type,
                stats,
                batch_id=batch_id,
                published_rates=published,
                diagnostics=diagnostics,
                elapsed_seconds=time.monotonic() - start,
            )
        except Exception as exc:
            db.rollback()
            _record_failure(
                db,
                service_code,
                region_code,
                stats,
                source_type,
                source_uri,
                type(exc).__name__ + ": " + str(exc)[:150],
            )
            if isinstance(exc, (AwsBulkImportError, AwsPricingConflictError)):
                raise
            raise AwsBulkImportError("AWS pricing publication rolled back") from exc
