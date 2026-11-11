"""Task 27.2 numerical and HTTP contract regression tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.calculator import CalculatorEstimateRequest
from app.services.calculator_engine import (
    CalculatorMeteredComponent,
    duration_seconds,
    estimate_calculator_cost,
)
from app.services.calculator_foundation import CalculatorPriceLookup
from app.services.pricing_catalog import PricingIdentity, ResolvedPrice
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers

AT = datetime(2026, 11, 11, tzinfo=UTC)


def req(provider="aws", service="ec2", period=None, **other):
    data = {
        "provider": provider,
        "region": "sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        "resource_configuration": {"service": service},
        "period": period or {"mode": "monthly"},
        "pricing_reference_date": AT,
    }
    data.update(other)
    return CalculatorEstimateRequest.model_validate(data)


def component(
    provider="aws", unit="INSTANCE_HOUR", rate="2", count="1", month="720",
    increment=1, minimum=0, eligible=False, missing=None, key="compute",
):
    service = "ec2" if provider == "aws" else "compute"
    identity = PricingIdentity(provider, service, f"TEST.{key}", unit)
    price = (
        ResolvedPrice(
            id=f"id-{key}", provider=provider, service=service, sku=identity.sku,
            description=f"Test {key}", unit=unit, amount=Decimal(rate),
            currency="USD" if provider == "aws" else "BRL",
            effective_from=AT - timedelta(days=3), effective_until=None, source="TEST",
        )
        if missing is None else None
    )
    lookup = CalculatorPriceLookup(
        identity=identity, status=missing or "priced", price=price,
        reference_at=AT, warning_code=missing,
    )
    return CalculatorMeteredComponent(
        key=key, lookup=lookup, units_per_resource=Decimal(count),
        reference_month_hours=Decimal(month),
        increment_seconds=None if unit.endswith("_MONTH") else increment,
        minimum_billable_seconds=minimum, discount_eligible=eligible,
    )


@pytest.mark.parametrize(
    ("period", "expected_hours"),
    [
        ({"mode": "hours", "amount": "1"}, "1"),
        ({"mode": "days", "amount": "1"}, "24"),
        ({"mode": "weeks", "amount": "1"}, "168"),
        ({"mode": "weeks", "amount": "3"}, "504"),
        ({"mode": "weeks", "amount": "1.5"}, "252"),
        ({"mode": "hours", "amount": "0.5"}, "0.5"),
    ],
)
def test_precise_duration(period, expected_hours):
    assert duration_seconds(req(period=period)) / 3600 == Decimal(expected_hours)


def test_timezone_utc_elapsed_across_dst_and_partial_seconds():
    p = {
        "mode": "custom", "start_at": "2026-11-01T01:30:00-04:00",
        "end_at": "2026-11-01T01:30:30-05:00",
    }
    assert duration_seconds(req(period=p)) == Decimal("3630")
    precise = {
        "mode": "custom", "start_at": "2026-11-11T08:00:00+00:00",
        "end_at": "2026-11-11T08:00:00.500000+00:00",
    }
    assert duration_seconds(req(period=precise)) == Decimal("0.5")


@pytest.mark.parametrize("p", [
    {"mode": "weeks", "amount": "270"},
    {"mode": "custom", "start_at": "2026-01-01T00:00:00+00:00",
     "end_at": "2033-01-01T00:00:00+00:00"},
    {"mode": "custom", "start_at": "2026-01-01T00:00:00+00:00",
     "end_at": "2026-01-01T00:00:00+00:00"},
])
def test_invalid_duration_cannot_be_estimated(p):
    try:
        request = req(period=p)
    except ValidationError:
        return
    with pytest.raises(ValueError):
        estimate_calculator_cost(request, [component()])


def test_reference_month_and_quantity_and_hourly_usage():
    result = estimate_calculator_cost(
        req(quantity=2, period={"mode": "weeks", "amount": "3"}),
        [component(rate="0.5", count="4", month="720")],
    )
    assert result.period_duration_hours == Decimal(504)
    assert result.pricing_components[0].monthly_units == Decimal(5760)
    assert result.pricing_components[0].period_units == Decimal(4032)
    assert result.monthly_final_cost == Decimal("2880.00")
    assert result.period_final_cost == Decimal("2016.00")
    assert result.final_currency == "USD"


def test_oci_744_monthly_hours_and_no_financial_double_count():
    r = estimate_calculator_cost(
        req(provider="oci", service="compute", period={"mode": "days", "amount": "1"}),
        [component(provider="oci", unit="OCPU_HOUR", rate="0.08266", count="2", month="744")],
    )
    assert r.monthly_original_cost == Decimal("123.00")
    assert r.period_original_cost == Decimal("3.97")
    assert r.monthly_net_cost == r.monthly_final_cost == r.monthly_original_cost
    assert r.period_net_cost == r.period_final_cost == r.period_original_cost
    assert r.final_currency == "BRL"
    assert r.discount_percent is None
    assert r.tax_percent is None


def test_monthly_storage_prorates_independently_from_hourly_components():
    hourly = component(unit="OCPU_HOUR", rate="0.1", month="744", key="cpu")
    storage = component(unit="GB_MONTH", rate="0.2", count="100", month="744", key="disk")
    r = estimate_calculator_cost(
        req(period={"mode": "hours", "amount": "372"}), [hourly, storage]
    )
    assert r.pricing_components[0].period_units == Decimal("372")
    assert r.pricing_components[1].period_units == Decimal("50")
    assert r.monthly_final_cost == Decimal("94.40")
    assert r.period_final_cost == Decimal("47.20")


def test_second_and_minute_billing_and_minimum():
    second = component(unit="INSTANCE_SECOND", rate="0.01", increment=1,
                       minimum=60, key="seconds")
    minute = component(unit="INSTANCE_MINUTE", rate="0.5", increment=60,
                       key="minutes")
    r = estimate_calculator_cost(
        req(period={"mode": "hours", "amount": "0.000277777777777778"}),
        [second, minute],
    )
    assert r.pricing_components[0].period_units == Decimal("60")
    assert r.pricing_components[1].period_units == Decimal("1")
    assert r.period_final_cost == Decimal("1.10")


def test_hour_increment_is_explicit_not_assumed_per_second():
    hourly = component(rate="6", increment=3600)
    r = estimate_calculator_cost(req(period={"mode": "hours", "amount": "1.1"}), [hourly])
    assert r.period_final_cost == Decimal("12.00")
    assert r.pricing_components[0].period_units == Decimal(2)
    with pytest.raises(ValueError, match="time_metering_policy_required"):
        estimate_calculator_cost(req(), [component(increment=None)])


def test_aws_discount_fx_tax_order_and_period_separation():
    r = estimate_calculator_cost(
        req(period={"mode": "weeks", "amount": "1"}, aws_financial={
            "discount_percent": "10", "conversion_enabled": True,
            "usd_brl_rate": "5.00",
        }),
        [
            component(rate="1", month="720", eligible=True, key="eligible"),
            component(rate="0.2", month="720", eligible=False, key="ineligible"),
        ],
    )
    assert r.monthly_original_cost == Decimal("864.00")
    assert r.monthly_discount_amount == Decimal("72.00")
    assert r.monthly_net_cost == Decimal("792.00")
    assert r.monthly_converted_cost == Decimal("3960.00")
    assert r.monthly_tax_amount == Decimal("514.80")
    assert r.monthly_final_cost == Decimal("4474.80")
    assert r.period_original_cost == Decimal("201.60")
    assert r.period_discount_amount == Decimal("16.80")
    assert r.period_final_cost == Decimal("1044.12")
    assert r.final_currency == "BRL"


@pytest.mark.parametrize("discount,tax,expected", [
    ("0", "13", "565.00"),
    ("10", "0", "450.00"),
    ("100", "13", "0.00"),
])
def test_aws_discount_and_tax_edge_cases(discount, tax, expected):
    r = estimate_calculator_cost(
        req(aws_financial={"discount_percent": discount, "tax_percent": tax,
                           "conversion_enabled": True, "usd_brl_rate": "5"}),
        [component(rate="100", month="1", eligible=True)],
    )
    assert r.monthly_final_cost == Decimal(expected)


def test_discount_100_percent_does_not_discount_ineligible_component():
    r = estimate_calculator_cost(
        req(aws_financial={"discount_percent": "100"}),
        [component(rate="10", eligible=True, key="eligible"),
         component(rate="2", eligible=False, key="ineligible")],
    )
    assert r.monthly_final_cost == Decimal("1440.00")


def test_aggregated_rounding_not_component_rounding():
    r = estimate_calculator_cost(req(), [
        component(rate="0.004", month="1", key="a"),
        component(rate="0.004", month="1", key="b"),
    ])
    assert [p.monthly_original_cost for p in r.pricing_components] == [
        Decimal("0.00"), Decimal("0.00")
    ]
    assert r.monthly_final_cost == Decimal("0.01")


def test_free_price_is_allowed_but_missing_price_is_not_free():
    free = estimate_calculator_cost(req(), [component(rate="0")])
    assert free.pricing_status == "priced"
    assert free.monthly_final_cost == Decimal("0.00")
    missing = estimate_calculator_cost(
        req(), [component(missing="sku_missing")]
    )
    assert missing.pricing_status == "sku_missing"
    assert missing.monthly_final_cost is None
    assert missing.period_final_cost is None
    assert missing.missing_pricing_components == ["compute"]


def test_partial_price_is_only_an_explicit_known_subtotal():
    r = estimate_calculator_cost(req(), [
        component(rate="1", month="1", key="known"),
        component(missing="price_not_effective", key="unknown"),
    ])
    assert r.pricing_status == "partially_priced"
    assert r.monthly_known_subtotal == Decimal("1.00")
    assert r.period_known_subtotal == Decimal("1.00")
    assert r.monthly_final_cost is None
    assert r.monthly_original_cost is None
    assert r.missing_pricing_components == ["unknown"]
    assert "price_not_effective" in r.warnings


def test_invalid_mixed_currency_and_oci_discount_are_rejected():
    changed = component(provider="oci")
    with pytest.raises(ValueError, match="component_provider_mismatch"):
        estimate_calculator_cost(req(), [changed])
    with pytest.raises(ValueError, match="oci_discount_is_forbidden"):
        estimate_calculator_cost(
            req(provider="oci", service="compute"),
            [component(provider="oci", eligible=True)],
        )


def test_invalid_duplicate_sku_keys_and_snapshot_times():
    c = component()
    with pytest.raises(ValueError, match="duplicate_or_empty_component_key"):
        estimate_calculator_cost(req(), [c, c])
    with pytest.raises(ValueError, match="component_pricing_snapshot_mismatch"):
        estimate_calculator_cost(req(pricing_reference_date=AT + timedelta(days=1)), [c])


def test_monthly_units_do_not_accept_second_rounding():
    c = component(unit="GB_MONTH")
    c = CalculatorMeteredComponent(
        key=c.key, lookup=c.lookup, units_per_resource=c.units_per_resource,
        reference_month_hours=c.reference_month_hours, increment_seconds=60,
    )
    with pytest.raises(ValueError, match="monthly_units_do_not_use_second_rounding"):
        estimate_calculator_cost(req(), [c])


def test_empty_production_adapter_explicitly_unavailable():
    r = estimate_calculator_cost(req(), ())
    assert r.pricing_status == "unsupported_configuration"
    assert r.monthly_final_cost is None
    assert r.period_final_cost is None
    assert "service_adapter_not_available" in r.warnings


def test_api_is_authenticated_and_never_quotes_unverified_prices(auth_env):
    http, _, tokens, _ = auth_env
    payload = req().model_dump(mode="json")
    assert http.post("/api/v1/calculator/estimate", json=payload).status_code == 401
    assert http.post(
        "/api/v1/calculator/estimate", json=payload, headers=headers(tokens)
    ).status_code == 200
    response = http.post(
        "/api/v1/calculator/estimate", json=payload, headers=headers(tokens)
    )
    data = response.json()
    assert data["pricing_status"] == "unsupported_configuration"
    assert data["monthly_final_cost"] is None
    assert data["period_final_cost"] is None
    assert data["pricing_currency"] == "USD"
    assert data["warnings"] == ["service_adapter_not_available"]
    assert http.post(
        "/api/v1/calculator/estimate", json={**payload, "quantity": 0},
        headers=headers(tokens),
    ).status_code == 422