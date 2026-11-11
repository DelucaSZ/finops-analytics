"""Task 27.1 contract tests: no fabricated SKU, FX, currency, or zero-cost fallbacks."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.pricing import PricingCatalogItem
from app.schemas.calculator import (
    AwsFinancialTerms,
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    CalculatorPeriod,
)
from app.services.calculator_foundation import (
    CalculatorCatalogAdapter,
    apply_aws_financial_terms,
    oci_compute_catalog_identities,
)
from app.services.oci_pricing import UnsupportedOciComputeShapeError
from app.services.pricing_catalog import PricingIdentity

AT = datetime(2026, 11, 11, 18, tzinfo=UTC)


def _request(**changes):
    request = {
        "provider": "aws",
        "region": "sa-east-1",
        "resource_configuration": {"service": "ec2", "instance_type": "t3.medium"},
    }
    request.update(changes)
    return CalculatorEstimateRequest.model_validate(request)


def test_aws_defaults_and_account_independence():
    request = _request()
    assert request.quantity == 1
    assert request.period.mode == "monthly"
    assert request.aws_financial is None
    assert "account_id" not in request.model_fields


def test_oci_accepts_db_system_without_inventing_a_price():
    request = _request(
        provider="oci",
        resource_configuration={
            "service": "db_system",
            "shape": "VM.BaseDB.x86",
            "cpu_unit": "ECPU",
            "license_model": "license_included",
        },
    )
    assert request.resource_configuration.cpu_unit == "ECPU"


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "oci"},
        {"provider": "oci", "aws_financial": {}},
        {"resource_configuration": {"service": "rds", "engine": "postgres"}},
        {"region": "   "},
        {"quantity": 0},
        {"quantity": 100001},
        {"pricing_reference_date": "2026-11-11T12:00:00"},
    ],
)
def test_invalid_request_combinations_rejected(changes):
    with pytest.raises(ValidationError):
        _request(**changes)


@pytest.mark.parametrize(
    "invalid",
    [
        {"discount_percent": "-0.01"},
        {"discount_percent": "100.01"},
        {"discount_percent": "NaN"},
        {"conversion_enabled": True},
        {"conversion_enabled": True, "usd_brl_rate": 0},
        {"usd_brl_rate": "5.2"},
        {"tax_percent": -1},
    ],
)
def test_invalid_aws_terms_rejected(invalid):
    with pytest.raises(ValidationError):
        AwsFinancialTerms.model_validate(invalid)


def test_aws_terms_default_tax_and_discount():
    terms = AwsFinancialTerms()
    assert terms.discount_percent == Decimal("0")
    assert terms.tax_percent == Decimal("13")
    assert terms.conversion_enabled is False


@pytest.mark.parametrize(
    "period",
    [
        {"mode": "hours", "amount": "0"},
        {"mode": "hours", "amount": "NaN"},
        {"mode": "weeks"},
        {"mode": "monthly", "amount": 4},
        {"mode": "custom", "start_at": "2026-11-11T10:00:00Z"},
        {
            "mode": "custom",
            "start_at": "2026-11-11T10:00:00",
            "end_at": "2026-11-11T11:00:00",
        },
        {
            "mode": "custom",
            "start_at": "2026-11-11T12:00:00Z",
            "end_at": "2026-11-11T11:00:00Z",
        },
    ],
)
def test_invalid_periods_rejected(period):
    with pytest.raises(ValidationError):
        CalculatorPeriod.model_validate(period)


def test_fractional_weeks_and_custom_datetimes():
    assert CalculatorPeriod(mode="weeks", amount="1.5").amount == Decimal("1.5")
    custom = CalculatorPeriod(
        mode="custom",
        start_at=AT,
        end_at=AT + timedelta(hours=4),
    )
    assert custom.end_at - custom.start_at == timedelta(hours=4)


def test_discount_only_applies_to_eligible_usd_components():
    result = apply_aws_financial_terms(
        eligible_original_usd=Decimal("100"),
        noneligible_original_usd=Decimal("20"),
        terms=AwsFinancialTerms(
            discount_percent=Decimal("10"),
            conversion_enabled=True,
            usd_brl_rate=Decimal("5"),
        ),
    )
    assert result.original_usd == Decimal("120.00")
    assert result.discount_amount_usd == Decimal("10.00")
    assert result.net_usd == Decimal("110.00")
    assert result.converted_brl == Decimal("550.00")
    assert result.tax_amount_brl == Decimal("71.50")
    assert result.final_amount == Decimal("621.50")
    assert result.final_currency == "BRL"


def test_100_percent_discount_does_not_discount_ineligible_items():
    result = apply_aws_financial_terms(
        eligible_original_usd=Decimal("90"),
        noneligible_original_usd=Decimal("20"),
        terms=AwsFinancialTerms(discount_percent=100),
    )
    assert result.final_amount == Decimal("20.00")
    assert result.final_currency == "USD"
    assert result.converted_brl is None
    assert result.tax_amount_brl is None


@pytest.mark.parametrize("bad", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_component_money_is_rejected(bad):
    with pytest.raises(ValueError):
        apply_aws_financial_terms(
            eligible_original_usd=bad,
            noneligible_original_usd=Decimal("0"),
            terms=AwsFinancialTerms(),
        )


def test_oci_compute_catalog_keys_reuse_existing_exact_allowlist():
    identities = oci_compute_catalog_identities(
        "VM.Standard.E5.Flex", windows=True, include_block_volume=True
    )
    assert [identity.sku for identity in identities] == [
        "VM.Standard.E5.Flex.OCPU",
        "VM.Standard.E5.Flex.Memory",
        "WINDOWS_LICENSE_OCPU",
        "BLOCK_VOLUME_GB_MONTH",
        "BLOCK_VOLUME_VPU_GB_MONTH",
    ]
    assert all(identity.provider == "oci" for identity in identities)
    with pytest.raises(UnsupportedOciComputeShapeError):
        oci_compute_catalog_identities("VM.BaseDB.x86")


@pytest.fixture
def price_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _price(*, currency="BRL", enabled=True, start=None, end=None):
    return PricingCatalogItem(
        provider="oci",
        service="compute",
        sku="VM.Standard.E5.Flex.OCPU",
        description="E5 OCPU",
        unit="OCPU_HOUR",
        price=Decimal("0.08266"),
        currency=currency,
        effective_from=start or AT - timedelta(days=1),
        effective_until=end,
        enabled=enabled,
        source="TEST",
    )


IDENTITY = PricingIdentity("oci", "compute", "VM.Standard.E5.Flex.OCPU", "OCPU_HOUR")


def test_catalog_missing_and_not_effective_are_not_zero(price_db):
    adapter = CalculatorCatalogAdapter(price_db)
    missing = adapter.resolve(IDENTITY, at=AT)
    assert missing.status == "sku_missing"
    assert missing.price is None

    price_db.add(_price(start=AT + timedelta(days=1)))
    price_db.commit()
    future = adapter.resolve(IDENTITY, at=AT)
    assert future.status == "price_not_effective"
    assert future.price is None


def test_catalog_current_price_retains_provenance(price_db):
    price_db.add(_price())
    price_db.commit()
    resolved = CalculatorCatalogAdapter(price_db).resolve(IDENTITY, at=AT)
    assert resolved.available
    assert resolved.price is not None
    assert resolved.price.amount == Decimal("0.08266000")
    assert resolved.price.currency == "BRL"
    assert resolved.price.source == "TEST"
    assert resolved.price.effective_from is not None


def test_catalog_wrong_currency_is_not_returned_as_valid(price_db):
    price_db.add(_price(currency="USD"))
    price_db.commit()
    resolved = CalculatorCatalogAdapter(price_db).resolve(IDENTITY, at=AT)
    assert resolved.status == "pricing_configuration_error"
    assert resolved.price is None


def test_catalog_disabled_price_is_explicit(price_db):
    price_db.add(_price(enabled=False))
    price_db.commit()
    resolved = CalculatorCatalogAdapter(price_db).resolve(IDENTITY, at=AT)
    assert resolved.status == "price_not_effective"
    assert resolved.price is None


def test_catalog_batch_keeps_same_reference_date(price_db):
    adapter = CalculatorCatalogAdapter(price_db)
    results = adapter.resolve_many((IDENTITY, IDENTITY), at=AT)
    assert all(result.reference_at == AT for result in results)


def test_priced_response_needs_totals_and_oci_cannot_be_taxed():
    base = {
        "provider": "oci",
        "service": "compute",
        "region": "sa-saopaulo-1",
        "resource_configuration": {"service": "compute", "shape": "VM.Standard.E5.Flex"},
        "quantity": 1,
        "period": {"mode": "monthly"},
        "pricing_currency": "BRL",
        "final_currency": "BRL",
        "pricing_status": "sku_missing",
        "missing_pricing_components": ["compute:unknown"],
    }
    missing = CalculatorEstimateResponse.model_validate(base)
    assert missing.monthly_final_cost is None
    with pytest.raises(ValidationError):
        CalculatorEstimateResponse.model_validate(
            {**base, "pricing_status": "priced", "missing_pricing_components": []}
        )
    with pytest.raises(ValidationError):
        CalculatorEstimateResponse.model_validate({**base, "tax_percent": "13"})
