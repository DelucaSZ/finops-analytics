from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.oci_pricing import OciPricingService
from app.services.pricing_catalog import PricingCurrencyMismatchError, ResolvedPrice

_EFFECTIVE_FROM = datetime(2026, 10, 1, tzinfo=UTC)
_TEST_PRICES = {
    ("compute", "VM.Standard.E3.Flex.OCPU", "OCPU_HOUR"): Decimal("0.0521"),
    ("compute", "VM.Standard.E3.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.0031"),
    ("compute", "VM.Standard.E4.Flex.OCPU", "OCPU_HOUR"): Decimal("0.0689"),
    ("compute", "VM.Standard.E4.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.0041"),
    ("compute", "VM.Standard.E5.Flex.OCPU", "OCPU_HOUR"): Decimal("0.08266"),
    ("compute", "VM.Standard.E5.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.005511"),
    ("compute", "WINDOWS_LICENSE_OCPU", "OCPU_HOUR"): Decimal("0.46092"),
    ("block_volume", "BLOCK_VOLUME_GB_MONTH", "GB_MONTH"): Decimal("0.0531"),
    ("block_volume", "BLOCK_VOLUME_VPU_GB_MONTH", "VPU_GB_MONTH"): Decimal("0.0036"),
}


class _TestPricingResolver:
    def resolve_price(
        self,
        *,
        provider: str,
        service: str,
        sku: str,
        unit: str,
        at=None,
        expected_currency: str | None = None,
    ) -> ResolvedPrice:
        if provider != "oci":
            raise KeyError(provider)
        amount = _TEST_PRICES[(service, sku, unit)]
        if expected_currency not in {None, "BRL"}:
            raise PricingCurrencyMismatchError(
                f"test catalog expected BRL, caller requested {expected_currency}"
            )
        return ResolvedPrice(
            id=f"test-{service}-{sku}-{unit}",
            provider="oci",
            service=service,
            sku=sku,
            description=f"Test catalog item {sku}",
            unit=unit,
            amount=amount,
            currency="BRL",
            effective_from=_EFFECTIVE_FROM,
            effective_until=None,
            source="IMPORTED_OCI_CALCULATOR",
        )


@pytest.fixture(autouse=True)
def isolated_oci_pricing_catalog(monkeypatch):
    resolver = _TestPricingResolver()
    original = OciPricingService._catalog

    def catalog(service: OciPricingService, *, at=None):
        if service._resolver is not None:
            return service._resolver
        return resolver

    monkeypatch.setattr(OciPricingService, "_catalog", catalog)
    yield resolver
    monkeypatch.setattr(OciPricingService, "_catalog", original)
