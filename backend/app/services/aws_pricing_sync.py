"""Task 28.4: bounded AWS regional catalog synchronization and operational observability.

The 28.3 importer remains the sole writer of financial catalog records. Scheduler
and operator calls use the same orchestration entry points; nothing runs by default.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.account import AwsAccount, CloudAccount
from app.models.aws_pricing import (
    AwsPricingImportBatch,
    AwsPricingProduct,
    AwsPricingRateDetail,
    AwsPricingSyncRun,
)
from app.models.pricing import PricingCatalogItem
from app.services.aws_pricing_bulk import PriceListReference, discover_price_list
from app.services.aws_pricing_import import AwsImportResult, import_aws_prices
from app.services.aws_pricing_normalization import (
    NormalizedProduct,
    NormalizedRate,
    coverage_component,
    coverage_summary,
    supported_source,
)
from app.services.aws_regional_pricing import AwsRegionalPricingRepository

logger = logging.getLogger(__name__)
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
_SQLITE_TEST_LOCK = threading.Lock()
_COMPONENT = {
    "INSTANCE_HOUR": "",
    "LB_HOUR": "hour",
    "IP_HOUR": "ipv4",
    "GB_MONTH": "capacity",
    "IOPS_MONTH": "iops",
    "MBPS_MONTH": "throughput",
    "LCU_HOUR": "lcu",
    "NLCU_HOUR": "nlcu",
}


def _utc(value: datetime | None = None) -> datetime:
    dt = value or datetime.now(UTC)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _key(name: str) -> int:
    # Same signed bigint on all workers, stable across Python hash randomization.
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)


def discover_regions(db: Session, extra_regions: str = "") -> list[str]:
    """Active AWS account regions + explicit extras; no global-region sweep."""
    rows = db.scalars(
        select(AwsAccount.regions)
        .join(CloudAccount, AwsAccount.cloud_account_id == CloudAccount.id)
        .where(CloudAccount.provider == "aws", CloudAccount.enabled.is_(True))
    )
    regions: set[str] = set()
    for values in rows:
        if isinstance(values, list):
            regions.update(x for x in values if isinstance(x, str) and _REGION.fullmatch(x))
    for region in extra_regions.split(","):
        code = region.strip()
        if code:
            if not _REGION.fullmatch(code):
                raise ValueError("invalid extra AWS pricing region")
            regions.add(code)
    return sorted(regions)


def _services(raw: str) -> list[str]:
    values = list(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))
    if not values or any(not supported_source(x) for x in values):
        raise ValueError("unsupported AWS pricing synchronization service configuration")
    return values


class AwsPricingSynchronizer:
    """Persistent cycle state, PostgreSQL cross-worker mutexes and last-good publication."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        config: Any = settings,
        discovery: Callable[..., PriceListReference] = discover_price_list,
        importer: Callable[..., AwsImportResult] = import_aws_prices,
        allow_sqlite_tests: bool = False,
    ) -> None:
        self.sessions = session_factory
        self.config = config
        self.discovery = discovery
        self.importer = importer
        self.allow_sqlite_tests = allow_sqlite_tests

    @contextmanager
    def _claim(self, service: str, region: str) -> Iterator[bool]:
        """Hold session-level advisory locks across source discovery AND publication.

        Transaction-scoped publication locks in the 28.3 importer remain active as
        a second independent guard. Test-only SQLite path is deliberately explicit.
        """
        engine = self.sessions.kw["bind"]
        if engine.dialect.name != "postgresql":
            if not self.allow_sqlite_tests:
                raise RuntimeError("AWS sync requires PostgreSQL advisory locks")
            acquired = _SQLITE_TEST_LOCK.acquire(blocking=False)
            try:
                yield acquired
            finally:
                if acquired:
                    _SQLITE_TEST_LOCK.release()
            return
        acquired: list[int] = []
        with engine.connect() as connection:

            def take(name: str) -> bool:
                key = _key("aven:aws-pricing-sync:" + name)
                if connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
                    acquired.append(key)
                    return True
                return False

            def slot(prefix: str, maximum: int) -> bool:
                return any(take(f"{prefix}:{index}") for index in range(maximum))

            try:
                # Global (cross-container) resource limits, including downloads.
                claimed = (
                    slot("worker", self.config.aws_pricing_sync_max_concurrent)
                    and slot("download", self.config.aws_pricing_sync_max_downloads)
                    and take(f"unit:{service}:{region}")
                )
                yield claimed
            finally:
                for key in reversed(acquired):
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()

    def units(
        self, *, service: str | None = None, region: str | None = None
    ) -> list[tuple[str, str]]:
        enabled = _services(self.config.aws_pricing_sync_services)
        if service and service not in enabled:
            raise ValueError("service disabled or unsupported for AWS price synchronization")
        if region and not _REGION.fullmatch(region):
            raise ValueError("invalid AWS pricing region")
        with self.sessions() as db:
            regions = discover_regions(db, self.config.aws_pricing_sync_extra_regions)
        if region:
            # Explicit administrative selections filter the requested region and
            # may also bootstrap a region not yet listed on an account.
            regions = [region]
        return [(svc, reg) for reg in regions for svc in (enabled if not service else [service])]

    def due(self, service: str, region: str, now: datetime | None = None) -> bool:
        current = _utc(now)
        with self.sessions() as db:
            state = AwsRegionalPricingRepository(db).get_sync_state(
                service_code=service, region_code=region
            )
            if state is None or state.next_due_at is None:
                return True
            return _utc(state.next_due_at) <= current

    def _start(self, service: str, region: str, trigger: str, now: datetime) -> str:
        with self.sessions.begin() as db:
            # A running row with a released advisory lock is an interrupted worker.
            abandoned = db.scalars(
                select(AwsPricingSyncRun).where(
                    AwsPricingSyncRun.service_code == service,
                    AwsPricingSyncRun.region_code == region,
                    AwsPricingSyncRun.status == "running",
                )
            )
            for previous in abandoned:
                previous.status = "interrupted"
                previous.finished_at = now
                previous.error_code = "worker_interrupted"
                previous.error_summary = "Worker stopped before recording completion"
            previous_run = db.scalar(
                select(AwsPricingSyncRun)
                .where(
                    AwsPricingSyncRun.service_code == service,
                    AwsPricingSyncRun.region_code == region,
                )
                .order_by(AwsPricingSyncRun.started_at.desc(), AwsPricingSyncRun.id.desc())
                .limit(1)
            )
            attempt = (
                min(previous_run.attempt + 1, self.config.aws_pricing_sync_max_retries)
                if previous_run is not None and previous_run.status in {"failed", "interrupted"}
                else 1
            )
            item = AwsPricingSyncRun(
                service_code=service,
                region_code=region,
                trigger=trigger,
                status="running",
                started_at=now,
                attempt=attempt,
            )
            db.add(item)
            db.flush()
            return item.id

    def _last_published(
        self, db: Session, service: str, region: str
    ) -> AwsPricingImportBatch | None:
        state = AwsRegionalPricingRepository(db).get_sync_state(
            service_code=service, region_code=region
        )
        if state is None or state.last_successful_batch_id is None:
            return None
        batch = db.get(AwsPricingImportBatch, state.last_successful_batch_id)
        return batch if batch is not None and batch.status == "published" else None

    def _finish(
        self,
        run_id: str,
        *,
        status: str,
        now: datetime,
        reference: PriceListReference | None = None,
        result: AwsImportResult | None = None,
        error_code: str | None = None,
        elapsed: float = 0,
    ) -> dict[str, Any]:
        with self.sessions.begin() as db:
            run = db.get(AwsPricingSyncRun, run_id)
            assert run is not None
            run.status = status
            run.finished_at = now
            run.source_reference = reference.arn[:500] if reference else None
            run.source_version = result.source_version if result else None
            run.batch_id = result.batch_id if result else None
            run.products_seen = result.products_seen if result else 0
            run.rates_seen = result.rates_seen if result else 0
            run.rates_rejected = result.rates_rejected if result else 0
            run.rates_published = result.published_rates if result else 0
            run.coverage = result.coverage if result else None
            run.error_code = error_code
            run.error_summary = (
                "Official AWS pricing synchronization failed; inspect backend logs"
                if error_code
                else None
            )
            run.metrics = {
                "elapsed_seconds": round(elapsed, 3),
                "source_bytes": result.diagnostics.get("source_bytes") if result else 0,
                "rates_staged": result.rates_staged if result else 0,
                "rates_unsupported": result.rates_unsupported if result else 0,
                "rates_rejected": run.rates_rejected,
                "download_seconds": result.diagnostics.get("download_seconds") if result else 0,
                "parse_seconds": result.diagnostics.get("parse_seconds") if result else 0,
                "persistence_seconds": (
                    result.diagnostics.get("persistence_seconds") if result else 0
                ),
            }
            cadence = timedelta(hours=self.config.aws_pricing_sync_interval_hours)
            if status == "failed":
                if run.attempt < self.config.aws_pricing_sync_max_retries:
                    exponent = min(run.attempt - 1, 12)
                    seconds = self.config.aws_pricing_sync_backoff_seconds * (2**exponent)
                    # Stable bounded per-unit jitter (no fast retry storm).
                    jitter = abs(_key(f"{run.service_code}:{run.region_code}:{run.attempt}")) % 31
                    run.next_retry_at = now + timedelta(seconds=seconds + jitter)
                else:
                    run.next_retry_at = now + cadence
                due = run.next_retry_at
            else:
                due = now + cadence
            repository = AwsRegionalPricingRepository(db)
            state = repository.get_sync_state(
                service_code=run.service_code, region_code=run.region_code
            )
            if state is None:
                state = repository.set_sync_state(
                    service_code=run.service_code,
                    region_code=run.region_code,
                    status="failed" if status == "failed" else "never_synced",
                )
            state.last_attempt_at = now
            state.next_due_at = due
            if error_code:
                state.error_summary = run.error_summary
            else:
                state.error_summary = None
            report = {
                "execution_id": run.id,
                "service_code": run.service_code,
                "region_code": run.region_code,
                "status": status,
                "source_version": run.source_version,
                "batch_id": run.batch_id,
                "next_due_at": due.isoformat(),
                "error_code": error_code,
            }
        logger.info(
            "event=aws_pricing_sync_completed execution_id=%s service=%s "
            "region=%s status=%s elapsed=%.3f error_code=%s",
            run_id,
            report["service_code"],
            report["region_code"],
            status,
            elapsed,
            error_code,
        )
        return report

    def run_unit(
        self,
        service: str,
        region: str,
        *,
        trigger: str = "manual",
        dry_run: bool = False,
        now: datetime | None = None,
        fixture_path=None,
        force: bool = False,
    ) -> dict[str, Any]:
        if not supported_source(service) or not _REGION.fullmatch(region):
            raise ValueError("invalid AWS pricing service or commercial region")
        if trigger not in {"manual", "automatic", "retry", "initial_import"}:
            raise ValueError("invalid AWS pricing trigger")
        if not dry_run and os.environ.get("AVEN_AWS_PRICING_IMPORT_ENABLED") != "1":
            raise PermissionError("publication requires AVEN_AWS_PRICING_IMPORT_ENABLED=1")
        if (
            fixture_path is not None
            and not dry_run
            and (
                not self.allow_sqlite_tests
                or os.environ.get("AVEN_ALLOW_OFFLINE_PRICE_FIXTURES") != "1"
            )
        ):
            raise PermissionError("offline fixture publication is restricted to explicit tests")
        current = _utc(now)
        started = time.monotonic()
        with self._claim(service, region) as acquired:
            if not acquired:
                return {"service_code": service, "region_code": region, "status": "busy"}
            if dry_run:
                with self.sessions() as db:
                    reference = None if fixture_path else self.discovery(service, region)
                    # Dry-run is a read-only report and cannot publish or queue a job.
                    result = self.importer(
                        service_code=service,
                        region_code=region,
                        db=db,
                        dry_run=True,
                        reference=reference,
                        fixture_path=fixture_path,
                        max_bytes=self.config.aws_pricing_sync_max_bytes,
                        max_products=self.config.aws_pricing_sync_max_products,
                        max_rates=self.config.aws_pricing_sync_max_rates,
                    )
                return {
                    "service_code": service,
                    "region_code": region,
                    "status": result.status,
                    "coverage": result.coverage,
                    "source_version": result.source_version,
                }
            run_id = self._start(service, region, trigger, current)
            reference = None
            result = None
            try:
                if fixture_path is None:
                    reference = self.discovery(service, region)
                    with self.sessions() as db:
                        latest = self._last_published(db, service, region)
                        # Publication identity is the immutable official ARN, not request time.
                        if (
                            not force
                            and latest is not None
                            and latest.source_type == "AWS_PUBLIC_PRICE_LIST"
                            and (latest.diagnostics or {}).get("official_arn") == reference.arn
                        ):
                            return self._finish(
                                run_id,
                                status="unchanged",
                                now=_utc(),
                                reference=reference,
                                elapsed=time.monotonic() - started,
                            )
                with self.sessions() as db:
                    result = self.importer(
                        service_code=service,
                        region_code=region,
                        db=db,
                        dry_run=False,
                        reference=reference,
                        fixture_path=fixture_path,
                        max_bytes=self.config.aws_pricing_sync_max_bytes,
                        max_products=self.config.aws_pricing_sync_max_products,
                        max_rates=self.config.aws_pricing_sync_max_rates,
                    )
                status = {
                    "published": "published",
                    "already_published": "unchanged",
                    "partial": "partial",
                    "published_partial": "partial",
                }.get(result.status, "failed")
                return self._finish(
                    run_id,
                    status=status,
                    now=_utc(),
                    result=result,
                    reference=reference,
                    error_code="unexpected_import_status" if status == "failed" else None,
                    elapsed=time.monotonic() - started,
                )
            except Exception as exc:
                logger.warning(
                    "event=aws_pricing_sync_failed execution_id=%s service=%s region=%s code=%s",
                    run_id,
                    service,
                    region,
                    type(exc).__name__,
                )
                return self._finish(
                    run_id,
                    status="failed",
                    now=_utc(),
                    reference=reference,
                    error_code=type(exc).__name__[:100],
                    elapsed=time.monotonic() - started,
                )

    def run_cycle(
        self,
        *,
        service: str | None = None,
        region: str | None = None,
        due_only: bool = True,
        dry_run: bool = False,
        retry_failed: bool = False,
    ) -> list[dict[str, Any]]:
        result = []
        for svc, reg in self.units(service=service, region=region):
            if len(result) >= self.config.aws_pricing_sync_max_jobs_per_cycle:
                break
            if due_only and not self.due(svc, reg):
                continue
            if retry_failed:
                with self.sessions() as db:
                    latest = db.scalar(
                        select(AwsPricingSyncRun.status)
                        .where(
                            AwsPricingSyncRun.service_code == svc,
                            AwsPricingSyncRun.region_code == reg,
                        )
                        .order_by(AwsPricingSyncRun.started_at.desc(), AwsPricingSyncRun.id.desc())
                        .limit(1)
                    )
                    if latest not in {"failed", "interrupted"}:
                        continue
            result.append(
                self.run_unit(
                    svc, reg, trigger="automatic" if due_only else "manual", dry_run=dry_run
                )
            )
        return result

    def status(
        self, *, service: str | None = None, region: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("invalid status pagination limit")
        with self.sessions() as db:
            units = self.units(service=service, region=region)
            records = []
            for svc, reg in units[:limit]:
                state = AwsRegionalPricingRepository(db).get_sync_state(
                    service_code=svc, region_code=reg
                )
                latest = db.scalar(
                    select(AwsPricingSyncRun)
                    .where(
                        AwsPricingSyncRun.service_code == svc, AwsPricingSyncRun.region_code == reg
                    )
                    .order_by(AwsPricingSyncRun.started_at.desc(), AwsPricingSyncRun.id.desc())
                    .limit(1)
                )
                updated = _utc(state.last_attempt_at) if state and state.last_attempt_at else None
                stale = (
                    updated is None
                    or updated + timedelta(hours=self.config.aws_pricing_sync_stale_hours) < _utc()
                )
                records.append(
                    {
                        "service_code": svc,
                        "region_code": reg,
                        "last_attempt_status": latest.status if latest else "not_synced",
                        "catalog_status": state.coverage_status if state else "never_synced",
                        "freshness": "stale" if stale else "current",
                        "last_attempt_at": updated.isoformat() if updated else None,
                        "last_success_at": _utc(state.last_success_at).isoformat()
                        if state and state.last_success_at
                        else None,
                        "next_due_at": _utc(state.next_due_at).isoformat()
                        if state and state.next_due_at
                        else None,
                        "published_batch_id": state.last_successful_batch_id if state else None,
                        "coverage": state.coverage if state else None,
                        "error_code": latest.error_code if latest else None,
                    }
                )
            return records


def coverage_report(
    db: Session, service: str, region: str, at: datetime | None = None
) -> dict[str, Any]:
    """Calculate coverage from CURRENT valid, linear published rates, not row totals.

    This complements immutable import-time coverage and detects expired dimension
    families. Count is paginated by database cursor, never materialized as a list.
    """
    now = _utc(at)
    statement = (
        select(AwsPricingProduct, AwsPricingRateDetail, PricingCatalogItem)
        .join(AwsPricingRateDetail, AwsPricingRateDetail.product_id == AwsPricingProduct.id)
        .join(PricingCatalogItem, PricingCatalogItem.id == AwsPricingRateDetail.pricing_item_id)
        .where(
            AwsPricingProduct.service_code == service,
            AwsPricingProduct.region_code == region,
            AwsPricingRateDetail.pricing_status == "active",
            PricingCatalogItem.enabled.is_(True),
            PricingCatalogItem.source == "AWS_PUBLIC_PRICE_LIST",
            PricingCatalogItem.effective_from <= now,
            (
                PricingCatalogItem.effective_until.is_(None)
                | (PricingCatalogItem.effective_until > now)
            ),
        )
        .execution_options(yield_per=500)
    )
    components: Counter[str] = Counter()
    rates = 0
    for product, detail, item in db.execute(statement):
        if item.currency != "USD" or item.price is None:
            continue
        component = _COMPONENT.get(item.unit)
        if component is None:
            continue
        normalized = NormalizedProduct(
            sku=product.product_sku,
            service=product.service,
            service_code=service,
            region=region,
            family=product.product_family,
            description=product.description,
            attributes=product.product_attributes,
            financial_attributes=product.financial_attributes,
        )
        rate = NormalizedRate(
            product=normalized,
            rate_code=detail.rate_code,
            term_code=detail.term_code,
            amount=item.price,
            effective_at=_utc(item.effective_from).isoformat(),
            aws_unit=detail.billing_unit_aws,
            unit=item.unit,
            begin_range=detail.begin_range,
            end_range=detail.end_range,
            description=detail.rate_description,
            pricing_status=detail.pricing_status,
            component=component,
        )
        components[coverage_component(rate)] += 1
        rates += 1
    summary = coverage_summary(service, dict(components))
    summary["active_rates"] = rates
    summary["products"] = (
        db.scalar(
            select(func.count(AwsPricingProduct.id)).where(
                AwsPricingProduct.service_code == service, AwsPricingProduct.region_code == region
            )
        )
        or 0
    )
    # RDS Multi-AZ is required by the calculator even when the 28.3 minimum
    # (historically Single-AZ) is met.
    if service == "AmazonRDS":
        required = {f"rds_{engine}_multiaz" for engine in ("postgresql", "mysql", "mariadb")}
        summary["missing"] = sorted(set(summary["missing"]) | (required - set(summary["present"])))
        summary["required"] = sorted(set(summary["required"]) | required)
        summary["complete"] = not summary["missing"]
    return summary
