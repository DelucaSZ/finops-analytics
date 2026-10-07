from decimal import Decimal

import pytest

from app.services.oci_pricing import (
    OCI_BLOCK_STORAGE_GB_MONTH,
    OCI_BLOCK_VPU_GB_MONTH,
    OCI_COMPUTE_PRICES,
    OCI_MONTHLY_HOURS,
    OCI_PRICING_CURRENCY,
    OCI_PRICING_METADATA,
    OCI_PRICING_SOURCE,
    OCI_PRICING_VERSION,
    OCI_WINDOWS_OCPU_HOUR,
    InvalidOciPricingInputError,
    OciPricingService,
    UnsupportedOciComputeFamilyError,
    quantize_money,
)


@pytest.fixture
def pricing() -> OciPricingService:
    return OciPricingService()


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("E3", Decimal("114.43")),
        ("E4", Decimal("151.33")),
        ("E5", Decimal("188.60")),
    ],
)
def test_compute_monthly_cost_by_family(pricing, family, expected):
    assert (
        pricing.compute_monthly_cost(
            family=family,
            ocpus=Decimal("2"),
            memory_gb=Decimal("16"),
        )
        == expected
    )


def test_windows_license_is_explicit_and_not_included_by_default(pricing):
    base = pricing.compute_monthly_cost(
        family="E3",
        ocpus=Decimal("2"),
        memory_gb=Decimal("16"),
    )
    windows = pricing.compute_monthly_cost(
        family="E3",
        ocpus=Decimal("2"),
        memory_gb=Decimal("16"),
        include_windows_license=True,
    )

    assert base == Decimal("114.43")
    assert windows == Decimal("800.28")
    assert windows > base


def test_block_volume_without_vpu(pricing):
    assert pricing.block_volume_monthly_cost(
        size_gb=Decimal("100"),
        vpus_per_gb=Decimal("0"),
    ) == Decimal("5.31")


def test_block_volume_reference_example_with_vpu(pricing):
    assert pricing.block_volume_monthly_cost(
        size_gb=Decimal("500"),
        vpus_per_gb=Decimal("10"),
    ) == Decimal("44.55")


def test_unknown_compute_family_never_returns_zero(pricing):
    with pytest.raises(UnsupportedOciComputeFamilyError, match="unsupported OCI Compute family"):
        pricing.compute_monthly_cost(
            family="E6",
            ocpus=Decimal("1"),
            memory_gb=Decimal("8"),
        )


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"family": "E3", "ocpus": Decimal("-1"), "memory_gb": Decimal("8")}, "ocpus"),
        ({"family": "E3", "ocpus": Decimal("1"), "memory_gb": Decimal("-8")}, "memory_gb"),
    ],
)
def test_compute_rejects_negative_inputs(pricing, kwargs, field):
    with pytest.raises(InvalidOciPricingInputError, match=field):
        pricing.compute_monthly_cost(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"size_gb": Decimal("-1"), "vpus_per_gb": Decimal("0")}, "size_gb"),
        ({"size_gb": Decimal("100"), "vpus_per_gb": Decimal("-1")}, "vpus_per_gb"),
    ],
)
def test_block_volume_rejects_negative_inputs(pricing, kwargs, field):
    with pytest.raises(InvalidOciPricingInputError, match=field):
        pricing.block_volume_monthly_cost(**kwargs)


@pytest.mark.parametrize("value", [None, "", "not-a-number", "NaN", "Infinity"])
def test_missing_or_invalid_decimal_inputs_are_rejected(pricing, value):
    with pytest.raises(InvalidOciPricingInputError):
        pricing.block_volume_monthly_cost(size_gb=value, vpus_per_gb=Decimal("0"))


def test_float_inputs_are_rejected_to_prevent_binary_float_money_regressions(pricing):
    with pytest.raises(InvalidOciPricingInputError, match="Decimal"):
        pricing.compute_monthly_cost(family="E3", ocpus=1.0, memory_gb=Decimal("8"))
    with pytest.raises(InvalidOciPricingInputError, match="Decimal"):
        pricing.block_volume_monthly_cost(size_gb=Decimal("100"), vpus_per_gb=10.0)


def test_zero_values_are_legitimate(pricing):
    assert pricing.compute_monthly_cost(family="E3", ocpus=0, memory_gb=0) == Decimal("0.00")
    assert pricing.block_volume_monthly_cost(size_gb=0, vpus_per_gb=0) == Decimal("0.00")


def test_catalog_metadata_and_rates_are_explicit_decimals():
    assert OCI_PRICING_METADATA.source == OCI_PRICING_SOURCE == "deepops_oci_price_table"
    assert OCI_PRICING_METADATA.version == OCI_PRICING_VERSION == "2026-10"
    assert OCI_PRICING_METADATA.currency == OCI_PRICING_CURRENCY == "BRL"
    assert OCI_PRICING_METADATA.monthly_hours == OCI_MONTHLY_HOURS == Decimal("744")
    assert Decimal("0.46092") == OCI_WINDOWS_OCPU_HOUR
    assert Decimal("0.0531") == OCI_BLOCK_STORAGE_GB_MONTH
    assert Decimal("0.0036") == OCI_BLOCK_VPU_GB_MONTH
    assert all(
        isinstance(value, Decimal)
        for price in OCI_COMPUTE_PRICES.values()
        for value in (price.ocpu_hour, price.memory_gb_hour)
    )


def test_money_rounding_uses_cents_and_half_up():
    assert quantize_money(Decimal("1.005")) == Decimal("1.01")
