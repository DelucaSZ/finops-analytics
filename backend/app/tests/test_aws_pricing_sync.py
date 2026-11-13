"""Offline orchestration tests; PostgreSQL advisory-lock behavior is separately gated."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import AwsAccount, CloudAccount
from app.models.aws_pricing import AwsPricingImportBatch, AwsPricingSyncRun
from app.models.pricing import PricingCatalogItem
from app.services.aws_pricing_bulk import PriceListReference
from app.services.aws_pricing_import import AwsImportResult
from app.services.aws_pricing_sync import (
    _SQLITE_TEST_LOCK,
    AwsPricingSynchronizer,
    coverage_report,
    discover_regions,
)
from app.services.aws_regional_pricing import AwsRegionalPricingRepository

CONFIG = SimpleNamespace(
    aws_pricing_sync_services="AmazonVPC,AmazonRDS",
    aws_pricing_sync_extra_regions="",
    aws_pricing_sync_interval_hours=24,
    aws_pricing_sync_stale_hours=72,
    aws_pricing_sync_max_jobs_per_cycle=2,
    aws_pricing_sync_max_concurrent=1,
    aws_pricing_sync_max_downloads=1,
    aws_pricing_sync_max_retries=3,
    aws_pricing_sync_backoff_seconds=5,
    aws_pricing_sync_max_bytes=10_000_000,
    aws_pricing_sync_max_products=1_000,
    aws_pricing_sync_max_rates=1_000,
)
NOW = datetime(2026, 11, 13, tzinfo=UTC)


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    engine.dispose()


def account(db, account_id, regions, enabled=True):
    master = CloudAccount(
        provider="aws", native_account_id=account_id, name=account_id, enabled=enabled
    )
    db.add(
        AwsAccount(
            cloud_account=master,
            name=account_id,
            aws_account_id=account_id,
            role_arn="arn:aws:iam::123456789012:role/test",
            external_id="test",
            regions=regions,
        )
    )
    db.flush()


def result(service, region, version, batch_id, status="published"):
    return AwsImportResult(
        service_code=service,
        region_code=region,
        dry_run=False,
        status=status,
        source_type="AWS_PUBLIC_PRICE_LIST",
        source_version=version,
        checksum="abc" + version,
        batch_id=batch_id,
        products_seen=1,
        products_matched=1,
        rates_seen=1,
        rates_staged=1,
        rates_rejected=0,
        rates_unsupported=0,
        published_rates=1 if status == "published" else 0,
        coverage={
            "complete": True,
            "required": ["ipv4_hour"],
            "present": ["ipv4_hour"],
            "missing": [],
            "counts": {"ipv4_hour": 1},
        },
        diagnostics={"source_bytes": 1000},
        elapsed_seconds=0.01,
    )


def fake_importer_factory(calls):
    def importer(*, service_code, region_code, db, dry_run, reference=None, **kwargs):
        calls.append((service_code, region_code, reference.arn if reference else "fixture"))
        if dry_run:
            return result(service_code, region_code, "v1", None, status="validated")
        with db.begin():
            repository = AwsRegionalPricingRepository(db)
            batch = repository.get_or_create_batch(
                service_code=service_code,
                region_code=region_code,
                source_version=reference.arn,
                checksum="sha" + reference.arn,
                source_type="AWS_PUBLIC_PRICE_LIST",
                source_uri=reference.url,
            )
            batch.status = "published"
            batch.finished_at = NOW
            batch.published_at = NOW
            batch.diagnostics = {"official_arn": reference.arn}
            repository.set_sync_state(
                service_code=service_code,
                region_code=region_code,
                status="synced",
                batch=batch,
                coverage={"complete": True, "present": ["ipv4_hour"], "missing": []},
            )
        return result(service_code, region_code, reference.arn, batch.id)

    return importer


def sync(maker, calls, refs, **kwargs):
    return AwsPricingSynchronizer(
        session_factory=maker,
        config=CONFIG,
        discovery=lambda service, region: PriceListReference(
            service,
            region,
            refs[region],
            "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/test",
        ),
        importer=fake_importer_factory(calls),
        allow_sqlite_tests=True,
        **kwargs,
    )


def test_region_discovery_deduplicated_and_active_only(sessions):
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1", "us-east-1"])
        account(db, "222222222222", ["sa-east-1", "us-west-2"])
        account(db, "333333333333", ["eu-west-1"], enabled=False)
    with sessions() as db:
        assert discover_regions(db) == ["sa-east-1", "us-east-1", "us-west-2"]
        assert discover_regions(db, "eu-north-1,sa-east-1") == [
            "eu-north-1",
            "sa-east-1",
            "us-east-1",
            "us-west-2",
        ]
        with pytest.raises(ValueError):
            discover_regions(db, "invalid-url")


def test_publish_unchanged_and_new_official_reference(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1"])
    calls = []
    refs = {"sa-east-1": "arn-v1"}
    orchestrator = sync(sessions, calls, refs)
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "published"
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "unchanged"
    assert len(calls) == 1
    refs["sa-east-1"] = "arn-v2"
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "published"
    with sessions() as db:
        assert db.scalar(select(func.count(AwsPricingSyncRun.id))) == 3
        assert db.scalar(select(func.count(AwsPricingImportBatch.id))) == 2
        state = AwsRegionalPricingRepository(db).get_sync_state(
            service_code="AmazonVPC", region_code="sa-east-1"
        )
        assert state.last_successful_batch_id is not None
    assert len(calls) == 2


def test_failure_keeps_last_good_and_is_independent_by_region(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1", "us-east-1"])
    calls = []
    refs = {"sa-east-1": "arn-v1", "us-east-1": "arn-v1"}
    orchestrator = sync(sessions, calls, refs)
    orchestrator.run_unit("AmazonVPC", "sa-east-1")
    with sessions() as db:
        original = (
            AwsRegionalPricingRepository(db)
            .get_sync_state(service_code="AmazonVPC", region_code="sa-east-1")
            .last_successful_batch_id
        )

    def broken(service, region):
        if region == "sa-east-1":
            raise OSError("AWS endpoint failed")
        return PriceListReference(service, region, "arn-v2", "https://aws.example")

    orchestrator.discovery = broken
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "failed"
    assert orchestrator.run_unit("AmazonVPC", "us-east-1")["status"] == "published"
    with sessions() as db:
        state = AwsRegionalPricingRepository(db).get_sync_state(
            service_code="AmazonVPC", region_code="sa-east-1"
        )
        assert state.last_successful_batch_id == original
        assert state.next_due_at is not None
        failed = db.scalar(
            select(AwsPricingSyncRun)
            .where(AwsPricingSyncRun.region_code == "sa-east-1")
            .order_by(AwsPricingSyncRun.started_at.desc())
            .limit(1)
        )
        assert failed.error_code == "OSError"


def test_claim_busy_and_recover_interrupted_run(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1"])
        db.add(
            AwsPricingSyncRun(
                service_code="AmazonVPC",
                region_code="sa-east-1",
                trigger="automatic",
                status="running",
                started_at=NOW,
            )
        )
    orchestrator = sync(sessions, [], {"sa-east-1": "arn-v1"})
    _SQLITE_TEST_LOCK.acquire()
    try:
        assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "busy"
    finally:
        _SQLITE_TEST_LOCK.release()
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "published"
    with sessions() as db:
        statuses = list(db.scalars(select(AwsPricingSyncRun.status)))
        assert "interrupted" in statuses
        assert "published" in statuses


def test_disabled_cross_worker_lock_fails_closed(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    orchestrator = AwsPricingSynchronizer(
        session_factory=sessions, config=CONFIG, allow_sqlite_tests=False
    )
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        orchestrator.run_unit("AmazonVPC", "sa-east-1")


def test_due_and_stale_are_independent_of_financial_publication(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1"])
    orchestrator = sync(sessions, [], {"sa-east-1": "arn-v1"})
    assert orchestrator.due("AmazonVPC", "sa-east-1")
    orchestrator.run_unit("AmazonVPC", "sa-east-1")
    assert not orchestrator.due("AmazonVPC", "sa-east-1")
    assert orchestrator.status(service="AmazonVPC")[0]["catalog_status"] == "synced"
    with sessions.begin() as db:
        state = AwsRegionalPricingRepository(db).get_sync_state(
            service_code="AmazonVPC", region_code="sa-east-1"
        )
        state.last_attempt_at = NOW - timedelta(days=8)
    assert orchestrator.status(service="AmazonVPC")[0]["freshness"] == "stale"


def test_validated_live_coverage_does_not_count_expired_or_unsupported_rates(sessions):
    with sessions.begin() as db:
        repo = AwsRegionalPricingRepository(db)
        product = repo.put_product(
            service="ipv4",
            service_code="AmazonVPC",
            region_code="sa-east-1",
            product_sku="VPC-1",
            product_family="IP Address",
            description="ipv4",
            financial_attributes={
                "group": "PublicIPv4",
                "usagetype": "SAE1-PublicIPv4:InUseAddress",
            },
            product_attributes={"group": "PublicIPv4", "usagetype": "SAE1-PublicIPv4:InUseAddress"},
        )
        repo.put_rate(
            product=product,
            rate_code="VPC-1.RATE",
            term_code="TERM",
            billing_unit="IP_HOUR",
            aws_unit="Hrs",
            amount=Decimal("0.00500000"),
            effective_from=NOW,
            source="AWS_PUBLIC_PRICE_LIST",
            source_effective_at=NOW,
        )
    with sessions() as db:
        present = coverage_report(db, "AmazonVPC", "sa-east-1", at=NOW + timedelta(days=1))
        assert present["complete"] is True
        assert present["active_rates"] == 1
        expired = coverage_report(db, "AmazonVPC", "sa-east-1", at=NOW - timedelta(days=1))
        assert expired["complete"] is False
        assert expired["missing"] == ["ipv4_hour"]


def test_same_price_later_official_effective_date_is_not_a_new_financial_version(sessions):
    with sessions.begin() as db:
        repo = AwsRegionalPricingRepository(db)
        product = repo.put_product(
            service="ipv4",
            service_code="AmazonVPC",
            region_code="sa-east-1",
            product_sku="VPC-2",
            product_family="IP Address",
            description="ipv4",
            financial_attributes={
                "group": "PublicIPv4",
                "usagetype": "SAE1-PublicIPv4:InUseAddress",
            },
        )
        params = dict(
            product=product,
            rate_code="VPC-2.RATE",
            term_code="TERM",
            billing_unit="IP_HOUR",
            aws_unit="Hrs",
            amount=Decimal("0.00500000"),
            source="AWS_PUBLIC_PRICE_LIST",
        )
        first = repo.put_rate(**params, effective_from=NOW, source_effective_at=NOW)
        later = NOW + timedelta(days=10)
        second = repo.put_rate(**params, effective_from=later, source_effective_at=later)
        assert first.id == second.id
    with sessions() as db:
        assert db.scalar(select(func.count(PricingCatalogItem.id))) == 1


def test_forced_validation_can_reimport_identical_reference(sessions, monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    with sessions.begin() as db:
        account(db, "111111111111", ["sa-east-1"])
    calls = []
    orchestrator = sync(sessions, calls, {"sa-east-1": "arn-v1"})
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1")["status"] == "published"
    assert orchestrator.run_unit("AmazonVPC", "sa-east-1", force=True)["status"] == "published"
    assert len(calls) == 2
    with sessions() as db:
        assert db.scalar(select(func.count(AwsPricingImportBatch.id))) == 1


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="requires isolated PostgreSQL")
def test_pg_advisory_locks_are_cross_session(monkeypatch):
    from sqlalchemy import create_engine

    url = os.environ["TEST_POSTGRES_URL"]
    engine = create_engine(url)
    maker = sessionmaker(bind=engine)
    syncer = AwsPricingSynchronizer(session_factory=maker, config=CONFIG)
    with syncer._claim("AmazonVPC", "sa-east-1") as first:
        assert first is True
        with syncer._claim("AmazonVPC", "sa-east-1") as second:
            assert second is False
    engine.dispose()
