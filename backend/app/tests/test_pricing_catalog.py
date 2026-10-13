from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.pricing import PricingCatalogItem
from app.services.oci_pricing import OciPricingService
from app.services.pricing_catalog import (
    PricingAmbiguityError,
    PricingCurrencyMismatchError,
    PricingNotFoundError,
    PricingResolver,
)

REFERENCE = datetime(2026, 10, 13, 12, tzinfo=UTC)


@pytest.fixture
def pricing_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _item(
    *,
    provider: str = "oci",
    service: str = "compute",
    sku: str = "VM.Standard.E4.Flex.OCPU",
    unit: str = "OCPU_HOUR",
    price: str = "0.0689",
    currency: str = "BRL",
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    enabled: bool = True,
) -> PricingCatalogItem:
    return PricingCatalogItem(
        provider=provider,
        service=service,
        sku=sku,
        description=f"Pricing item {sku}",
        unit=unit,
        price=Decimal(price),
        currency=currency,
        effective_from=effective_from or REFERENCE - timedelta(days=1),
        effective_until=effective_until,
        enabled=enabled,
        source="TEST_CATALOG",
    )


def _resolve(db: Session, *, at: datetime = REFERENCE):
    return PricingResolver(db).resolve_price(
        provider="oci",
        service="compute",
        sku="VM.Standard.E4.Flex.OCPU",
        unit="OCPU_HOUR",
        at=at,
        expected_currency="BRL",
    )


def test_current_enabled_effective_price_is_returned(pricing_db):
    pricing_db.add(_item())
    pricing_db.commit()

    price = _resolve(pricing_db)

    assert price.amount == Decimal("0.06890000")
    assert price.currency == "BRL"
    assert price.provider == "oci"
    assert price.service == "compute"
    assert price.unit == "OCPU_HOUR"


def test_future_price_is_not_returned_before_effective_from(pricing_db):
    pricing_db.add(_item(effective_from=REFERENCE + timedelta(seconds=1)))
    pricing_db.commit()

    with pytest.raises(PricingNotFoundError, match="pricing not found"):
        _resolve(pricing_db)


def test_expired_price_is_not_returned_at_or_after_effective_until(pricing_db):
    pricing_db.add(
        _item(
            effective_from=REFERENCE - timedelta(days=2),
            effective_until=REFERENCE,
        )
    )
    pricing_db.commit()

    with pytest.raises(PricingNotFoundError, match="pricing not found"):
        _resolve(pricing_db)


def test_disabled_price_is_not_returned(pricing_db):
    pricing_db.add(_item(enabled=False))
    pricing_db.commit()

    with pytest.raises(PricingNotFoundError, match="pricing not found"):
        _resolve(pricing_db)


def test_overlapping_effective_prices_raise_configuration_error(pricing_db):
    pricing_db.add_all(
        [
            _item(effective_from=REFERENCE - timedelta(days=10), price="0.0689"),
            _item(effective_from=REFERENCE - timedelta(days=1), price="0.0700"),
        ]
    )
    pricing_db.commit()

    with pytest.raises(PricingAmbiguityError, match="multiple effective prices"):
        _resolve(pricing_db)


def test_missing_price_never_becomes_zero(pricing_db):
    with pytest.raises(PricingNotFoundError, match="pricing not found"):
        _resolve(pricing_db)


def test_currency_mismatch_is_rejected_explicitly(pricing_db):
    pricing_db.add(_item(currency="USD"))
    pricing_db.commit()

    with pytest.raises(PricingCurrencyMismatchError, match="expected BRL, found USD"):
        _resolve(pricing_db)


def test_brl_oci_and_usd_aws_can_coexist_without_becoming_equivalent(pricing_db):
    pricing_db.add_all(
        [
            _item(currency="BRL"),
            _item(
                provider="aws",
                service="ec2",
                sku="TEST_AWS_INSTANCE_HOUR",
                unit="INSTANCE_HOUR",
                price="0.10",
                currency="USD",
            ),
        ]
    )
    pricing_db.commit()
    resolver = PricingResolver(pricing_db, reference_at=REFERENCE)

    oci = resolver.resolve_price(
        provider="oci",
        service="compute",
        sku="VM.Standard.E4.Flex.OCPU",
        unit="OCPU_HOUR",
        expected_currency="BRL",
    )
    aws = resolver.resolve_price(
        provider="aws",
        service="ec2",
        sku="TEST_AWS_INSTANCE_HOUR",
        unit="INSTANCE_HOUR",
        expected_currency="USD",
    )

    assert oci.currency == "BRL"
    assert aws.currency == "USD"
    with pytest.raises(PricingCurrencyMismatchError):
        resolver.resolve_price(
            provider="oci",
            service="compute",
            sku="VM.Standard.E4.Flex.OCPU",
            unit="OCPU_HOUR",
            expected_currency="USD",
        )


def test_oci_compute_and_block_volume_use_database_catalog_values(pricing_db):
    pricing_db.add_all(
        [
            _item(sku="VM.Standard.E4.Flex.OCPU", unit="OCPU_HOUR", price="0.0689"),
            _item(
                sku="VM.Standard.E4.Flex.Memory",
                unit="GB_RAM_HOUR",
                price="0.0041",
            ),
            _item(
                service="block_volume",
                sku="BLOCK_VOLUME_GB_MONTH",
                unit="GB_MONTH",
                price="0.0531",
            ),
            _item(
                service="block_volume",
                sku="BLOCK_VOLUME_VPU_GB_MONTH",
                unit="VPU_GB_MONTH",
                price="0.0036",
            ),
        ]
    )
    pricing_db.commit()
    snapshot = PricingResolver(pricing_db, reference_at=REFERENCE).snapshot(
        provider="oci",
        expected_currency="BRL",
    )
    pricing = OciPricingService(snapshot)

    compute = pricing.price_compute_resource(
        shape="VM.Standard.E4.Flex",
        ocpus=4,
        memory_gb=64,
        at=REFERENCE,
    )
    storage = pricing.block_volume_monthly_cost(
        size_gb=500,
        vpus_per_gb=10,
        at=REFERENCE,
    )

    assert compute.base_monthly_cost == Decimal("400.27")
    assert compute.currency == "BRL"
    assert storage == Decimal("44.55")


def test_oci_calculation_changes_when_database_price_changes_without_static_fallback(pricing_db):
    row = _item(
        service="block_volume",
        sku="BLOCK_VOLUME_GB_MONTH",
        unit="GB_MONTH",
        price="0.0531",
    )
    vpu = _item(
        service="block_volume",
        sku="BLOCK_VOLUME_VPU_GB_MONTH",
        unit="VPU_GB_MONTH",
        price="0.0036",
    )
    pricing_db.add_all([row, vpu])
    pricing_db.commit()

    before = OciPricingService(
        PricingResolver(pricing_db, reference_at=REFERENCE).snapshot(
            provider="oci", expected_currency="BRL"
        )
    ).block_volume_monthly_cost(size_gb=100, vpus_per_gb=0, at=REFERENCE)

    row.price = Decimal("0.0600")
    pricing_db.commit()
    pricing_db.expire_all()
    after = OciPricingService(
        PricingResolver(pricing_db, reference_at=REFERENCE).snapshot(
            provider="oci", expected_currency="BRL"
        )
    ).block_volume_monthly_cost(size_gb=100, vpus_per_gb=0, at=REFERENCE)

    assert before == Decimal("5.31")
    assert after == Decimal("6.00")


def test_preloaded_snapshot_avoids_select_per_resource(pricing_db):
    pricing_db.add_all(
        [
            _item(
                service="block_volume",
                sku="BLOCK_VOLUME_GB_MONTH",
                unit="GB_MONTH",
                price="0.0531",
            ),
            _item(
                service="block_volume",
                sku="BLOCK_VOLUME_VPU_GB_MONTH",
                unit="VPU_GB_MONTH",
                price="0.0036",
            ),
        ]
    )
    pricing_db.commit()
    selects = 0

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal selects
        if statement.lstrip().upper().startswith("SELECT") and "pricing_catalog_items" in statement:
            selects += 1

    event.listen(pricing_db.get_bind(), "before_cursor_execute", count_selects)
    try:
        snapshot = PricingResolver(pricing_db, reference_at=REFERENCE).snapshot(
            provider="oci",
            expected_currency="BRL",
        )
        pricing = OciPricingService(snapshot)
        for size in range(1, 101):
            pricing.block_volume_monthly_cost(
                size_gb=size,
                vpus_per_gb=10,
                at=REFERENCE,
            )
    finally:
        event.remove(pricing_db.get_bind(), "before_cursor_execute", count_selects)

    assert selects == 1
