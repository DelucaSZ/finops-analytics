"""Task 28.2: isolated AWS regional persistence and fail-closed resolution tests."""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.migrations import migration_config
from app.models.aws_pricing import AwsPricingRateDetail
from app.models.pricing import PricingCatalogItem
from app.models.pricing_audit import PricingAuditEvent
from app.services.aws_regional_pricing import (
    AwsPricingConflictError,
    AwsPricingValidationError,
    AwsRegionalPricingRepository,
    AwsRegionalPricingResolver,
)

AT = datetime(2026, 11, 12, 12, tzinfo=UTC)
ATTRS = {
    "instanceType": "m6i.large",
    "operatingSystem": "Linux",
    "tenancy": "Shared",
    "operation": "RunInstances",
}


@pytest.fixture
def pricing_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _product(db: Session, region: str = "sa-east-1"):
    return AwsRegionalPricingRepository(db).put_product(
        service="ec2", service_code="AmazonEC2", region_code=region,
        product_sku="SKU-TEST-001", product_family="Compute Instance",
        description="Synthetic test fixture (not an AWS public price)",
        financial_attributes=ATTRS,
    )


def _publish(db: Session, region: str = "sa-east-1"):
    repo = AwsRegionalPricingRepository(db)
    batch = repo.get_or_create_batch(
        service_code="AmazonEC2", region_code=region, source_version="fixture-1",
        checksum="fixture-checksum", source_type="TEST_FIXTURE",
    )
    batch.status = "published"
    repo.set_sync_state(
        service_code="AmazonEC2", region_code=region, status="synced", batch=batch
    )
    return batch


def _rate(
    db: Session, region: str = "sa-east-1", *,
    amount: str = "0.12345678", effective_from: datetime | None = None,
    rate_code: str = "SKU-TEST-001.JRTCKXETXF.6YS6EN2CT7",
):
    product = _product(db, region)
    batch = _publish(db, region)
    item = AwsRegionalPricingRepository(db).put_rate(
        product=product, rate_code=rate_code, term_code="TESTTERM",
        billing_unit="INSTANCE_HOUR", aws_unit="Hrs",
        amount=Decimal(amount), effective_from=effective_from or AT - timedelta(days=5),
        source="AWS_PUBLIC_PRICE_LIST", source_effective_at=AT - timedelta(days=10),
        import_batch=batch, rate_description="synthetic test rate",
    )
    db.flush()
    return item


def _resolve(db: Session, region: str, at: datetime = AT):
    return AwsRegionalPricingResolver(db).resolve_aws_price(
        service="ec2", service_code="AmazonEC2", region_code=region,
        configuration=ATTRS, billing_unit="INSTANCE_HOUR", reference_at=at,
    )


def test_same_product_in_two_regions_resolves_distinct_prices(pricing_db):
    first = _rate(pricing_db, "sa-east-1", amount="0.12345678")
    second = _rate(pricing_db, "us-east-1", amount="0.01111111")
    pricing_db.commit()
    br = _resolve(pricing_db, "sa-east-1")
    us = _resolve(pricing_db, "us-east-1")
    assert br.status == us.status == "priced"
    assert br.catalog_item_id == first.id
    assert us.catalog_item_id == second.id
    assert br.unit_price == Decimal("0.12345678")
    assert us.unit_price == Decimal("0.01111111")
    assert br.currency == us.currency == "USD"
    assert br.region_code != us.region_code
    assert br.product_sku == us.product_sku == "SKU-TEST-001"


def test_missing_region_never_falls_back_and_missing_is_not_free(pricing_db):
    _rate(pricing_db, "sa-east-1")
    pricing_db.commit()
    missing = _resolve(pricing_db, "us-east-1")
    assert missing.status == "sync_required"
    assert missing.unit_price is None
    _publish(pricing_db, "us-east-1")
    pricing_db.commit()
    missing = _resolve(pricing_db, "us-east-1")
    assert missing.status == "sku_missing"
    assert missing.unit_price is None


def test_real_zero_rate_is_priced_and_not_turned_into_missing(pricing_db):
    _rate(pricing_db, amount="0.00000000")
    pricing_db.commit()
    result = _resolve(pricing_db, "sa-east-1")
    assert result.status == "priced"
    assert result.unit_price == Decimal("0")
    assert result.rate_code is not None
    assert result.import_batch_id is not None


def test_historical_version_and_current_version_without_overwrite(pricing_db):
    original = _rate(pricing_db, amount="0.12345678", effective_from=AT - timedelta(days=5))
    later = _rate(pricing_db, amount="0.22222222", effective_from=AT + timedelta(days=2))
    pricing_db.commit()
    assert original.id != later.id
    assert _resolve(pricing_db, "sa-east-1", AT).catalog_item_id == original.id
    assert _resolve(pricing_db, "sa-east-1", AT + timedelta(days=3)).catalog_item_id == (
        later.id
    )
    assert _resolve(pricing_db, "sa-east-1", AT - timedelta(days=10)).status == (
        "price_not_effective"
    )
    assert original.effective_until == AT + timedelta(days=2)
    history = AwsRegionalPricingRepository(pricing_db).rate_history(
        service="ec2", region_code="sa-east-1",
        product_sku="SKU-TEST-001",
        rate_code="SKU-TEST-001.JRTCKXETXF.6YS6EN2CT7",
        billing_unit="INSTANCE_HOUR",
    )
    assert [item.id for item in history] == [later.id, original.id]


def test_identical_rate_import_is_idempotent_and_provenance_is_audited(pricing_db):
    one = _rate(pricing_db)
    two = _rate(pricing_db)
    pricing_db.commit()
    assert one.id == two.id
    rows = list(pricing_db.scalars(select(PricingAuditEvent).where(
        PricingAuditEvent.pricing_item_id == one.id
    )))
    assert len(rows) == 1
    assert rows[0].action == "IMPORTED"
    assert rows[0].region_code == "sa-east-1"
    assert rows[0].import_batch_id is not None
    assert rows[0].after_data["price"] == "0.12345678"


def test_conflicting_idempotency_and_backdating_are_rejected(pricing_db):
    _rate(pricing_db)
    with pytest.raises(AwsPricingConflictError, match="conflicting"):
        _rate(pricing_db, amount="0.98765432")
    with pytest.raises(AwsPricingConflictError, match="backdated"):
        _rate(pricing_db, effective_from=AT - timedelta(days=6))


def test_invalid_decimals_and_attributes_are_rejected(pricing_db):
    product = _product(pricing_db)
    with pytest.raises(AwsPricingValidationError, match="precision"):
        AwsRegionalPricingRepository(pricing_db).put_rate(
            product=product, rate_code="test-rate", term_code="term",
            billing_unit="INSTANCE_HOUR", aws_unit="Hrs",
            amount=Decimal("0.000000001"), effective_from=AT,
            source="TEST", source_effective_at=AT,
        )
    for amount in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(AwsPricingValidationError, match="finite nonnegative"):
            AwsRegionalPricingRepository(pricing_db).put_rate(
                product=product, rate_code="test-rate", term_code="term",
                billing_unit="INSTANCE_HOUR", aws_unit="Hrs",
                amount=amount, effective_from=AT, source="TEST", source_effective_at=AT,
            )
    with pytest.raises(AwsPricingValidationError, match="incomplete"):
        AwsRegionalPricingRepository(pricing_db).put_product(
            service="ec2", service_code="AmazonEC2", region_code="sa-east-1",
            product_sku="bad-fixture", product_family="Compute Instance",
            description="fixture", financial_attributes={"instanceType": "m6i.large"},
        )
    with pytest.raises(AwsPricingValidationError, match="region"):
        _product(pricing_db, "non-existent-region")


def test_distinct_product_skus_with_same_attributes_fail_closed(pricing_db):
    _rate(pricing_db)
    product = AwsRegionalPricingRepository(pricing_db).put_product(
        service="ec2", service_code="AmazonEC2", region_code="sa-east-1",
        product_sku="SKU-TEST-ALTERNATE", product_family="Compute Instance",
        description="fixture alternate SKU", financial_attributes=ATTRS,
    )
    batch = _publish(pricing_db)
    AwsRegionalPricingRepository(pricing_db).put_rate(
        product=product, rate_code="other-rate", term_code="OTHER-TERM",
        billing_unit="INSTANCE_HOUR", aws_unit="Hrs", amount=Decimal("1.00000000"),
        effective_from=AT - timedelta(days=2), source="AWS_PUBLIC_PRICE_LIST",
        source_effective_at=AT - timedelta(days=5), import_batch=batch,
    )
    pricing_db.commit()
    assert _resolve(pricing_db, "sa-east-1").status == "pricing_configuration_error"


def test_unsupported_tier_cannot_be_published_as_linear(pricing_db):
    product = _product(pricing_db)
    with pytest.raises(AwsPricingValidationError, match="tiered"):
        AwsRegionalPricingRepository(pricing_db).put_rate(
            product=product, rate_code="rate-1", term_code="term",
            billing_unit="GB_MONTH", aws_unit="GB-Mo",
            amount=Decimal("0.1"), effective_from=AT,
            source="AWS_PUBLIC_PRICE_LIST", source_effective_at=AT,
            begin_range="100", end_range="Inf",
        )


def test_database_constraints_reject_invalid_aws_rows(pricing_db):
    pricing_db.add(PricingCatalogItem(
        provider="aws", region_code="sa-east-1", service="ec2",
        sku="BAD", description="bad currency fixture", unit="HOUR",
        price=Decimal("0.12"), currency="BRL", effective_from=AT,
        enabled=True, source="TEST",
    ))
    with pytest.raises(IntegrityError):
        pricing_db.flush()
    pricing_db.rollback()
    pricing_db.add(PricingCatalogItem(
        provider="aws", region_code=None, service="ec2",
        sku="BAD", description="missing region fixture", unit="HOUR",
        price=Decimal("0.12"), currency="USD", effective_from=AT,
        enabled=True, source="TEST",
    ))
    with pytest.raises(IntegrityError):
        pricing_db.flush()
    pricing_db.rollback()


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'aws-pricing-migration.db'}")
        yield engine
        engine.dispose()
        return
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set TEST_POSTGRES_URL for PostgreSQL migration/constraint tests")
    schema = "test_aws_price_" + uuid.uuid4().hex
    control = create_engine(url)
    with control.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_0040_migration_preserves_oci_and_supports_empty_downgrade(migration_engine):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0039_oci_db_calculator_bindings")
        catalog = Table("pricing_catalog_items", MetaData(), autoload_with=connection)
        original = [
            (r.id, r.sku, r.price, r.currency, r.effective_from, r.effective_until)
            for r in connection.execute(select(catalog)).all()
        ]
        assert len(original) >= 9

        command.upgrade(cfg, "0040_aws_regional_pricing")
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        assert {
            "aws_pricing_products", "aws_pricing_rate_details",
            "aws_pricing_import_batches", "aws_pricing_sync_state",
        }.issubset(tables)
        catalog = Table("pricing_catalog_items", MetaData(), autoload_with=connection)
        assert "region_code" in catalog.c
        assert set(inspector.get_indexes("pricing_catalog_items")[i]["name"]
                   for i in range(len(inspector.get_indexes("pricing_catalog_items")))) >= {
            "uq_pricing_catalog_items_aws_effective",
            "uq_pricing_catalog_items_oci_effective",
            "ix_pricing_catalog_items_aws_lookup",
        }
        after = [
            (r.id, r.sku, r.price, r.currency, r.effective_from, r.effective_until)
            for r in connection.execute(select(catalog)).all()
        ]
        assert sorted(original) == sorted(after)
        assert all(row.region_code is None for row in connection.execute(select(catalog)).all())
        if connection.dialect.name == "postgresql":
            constraint = connection.scalar(text(
                "SELECT 1 FROM pg_constraint WHERE conname = "
                "'ex_aws_pricing_effective_no_overlap'"
            ))
            assert constraint == 1

        command.downgrade(cfg, "0039_oci_db_calculator_bindings")
        catalog = Table("pricing_catalog_items", MetaData(), autoload_with=connection)
        assert "region_code" not in catalog.c
        restored = [
            (r.id, r.sku, r.price, r.currency, r.effective_from, r.effective_until)
            for r in connection.execute(select(catalog)).all()
        ]
        assert sorted(restored) == sorted(original)


def test_pg_constraint_prevents_overlapping_aws_rates(migration_engine):
    if migration_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only GiST exclusion constraint")
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0040_aws_regional_pricing")
    with Session(migration_engine) as db:
        item = _rate(db)
        db.commit()
        db.add(PricingCatalogItem(
            provider="aws", region_code="sa-east-1", service="ec2",
            sku=item.sku, description="overlap test", unit="INSTANCE_HOUR",
            price=Decimal("0.3"), currency="USD",
            effective_from=AT - timedelta(days=4),
            effective_until=AT + timedelta(days=2),
            enabled=True, source="TEST",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
