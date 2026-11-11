"""Calculator pricing adapters and financial policy primitives (Task 27.1).

No provisioning, account lookup, rates API, or complete temporal cost engine here.
Existing billing and OCI opportunity pricing services are left unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pricing import PricingCatalogItem
from app.schemas.calculator import AwsFinancialTerms, CalculatorPricingStatus
from app.services.oci_pricing import (
    OCI_BLOCK_STORAGE_SKU,
    OCI_BLOCK_VPU_SKU,
    OCI_COMPUTE_PRICE_KEYS,
    OCI_SERVICE_BLOCK_VOLUME,
    OCI_SERVICE_COMPUTE,
    OCI_UNIT_GB_MONTH,
    OCI_UNIT_GB_RAM_HOUR,
    OCI_UNIT_OCPU_HOUR,
    OCI_UNIT_VPU_GB_MONTH,
    OCI_WINDOWS_LICENSE_SKU,
    resolve_compute_price_family,
)
from app.services.pricing_catalog import (
    PricingAmbiguityError,
    PricingCurrencyMismatchError,
    PricingIdentity,
    PricingNotFoundError,
    PricingResolver,
    ResolvedPrice,
)

_CENT = Decimal("0.01")
_EXPECTED_CURRENCY = {"aws": "USD", "oci": "BRL"}


@dataclass(frozen=True, slots=True)
class CalculatorPriceLookup:
    identity: PricingIdentity
    status: CalculatorPricingStatus
    price: ResolvedPrice | None
    reference_at: datetime
    warning_code: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "priced" and self.price is not None


class CalculatorCatalogAdapter:
    """Read-only version-aware access to the existing provider-neutral catalog.

    A missing identity differs from a known identity with no applicable price.
    In both cases the financial value remains None, not a fabricated zero.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve(
        self,
        identity: PricingIdentity,
        *,
        at: datetime | None = None,
    ) -> CalculatorPriceLookup:
        provider = identity.provider.strip().lower()
        if provider not in _EXPECTED_CURRENCY:
            raise ValueError("unknown provider")
        reference = at or datetime.now(UTC)
        if reference.utcoffset() is None:
            raise ValueError("reference timestamp must be timezone-aware")
        reference = reference.astimezone(UTC)
        normalized = PricingIdentity(
            provider=provider,
            service=identity.service.strip().lower(),
            sku=identity.sku.strip(),
            unit=identity.unit.strip().upper(),
        )
        resolver = PricingResolver(self._db, reference_at=reference)
        try:
            price = resolver.resolve_price(
                provider=normalized.provider,
                service=normalized.service,
                sku=normalized.sku,
                unit=normalized.unit,
                expected_currency=_EXPECTED_CURRENCY[provider],
            )
        except PricingNotFoundError:
            exists = self._db.scalar(
                select(PricingCatalogItem.id)
                .where(
                    PricingCatalogItem.provider == normalized.provider,
                    PricingCatalogItem.service == normalized.service,
                    PricingCatalogItem.sku == normalized.sku,
                    PricingCatalogItem.unit == normalized.unit,
                )
                .limit(1)
            )
            status: CalculatorPricingStatus = (
                "price_not_effective" if exists is not None else "sku_missing"
            )
            return CalculatorPriceLookup(
                identity=normalized,
                status=status,
                price=None,
                reference_at=reference,
                warning_code=status,
            )
        except (PricingCurrencyMismatchError, PricingAmbiguityError):
            return CalculatorPriceLookup(
                identity=normalized,
                status="pricing_configuration_error",
                price=None,
                reference_at=reference,
                warning_code="invalid_catalog_configuration",
            )
        return CalculatorPriceLookup(
            identity=normalized,
            status="priced",
            price=price,
            reference_at=reference,
        )

    def resolve_many(
        self,
        identities: tuple[PricingIdentity, ...],
        *,
        at: datetime | None = None,
    ) -> tuple[CalculatorPriceLookup, ...]:
        # Consistent reference date across every component of one estimate.
        reference = at or datetime.now(UTC)
        return tuple(self.resolve(identity, at=reference) for identity in identities)


def oci_compute_catalog_identities(
    shape: str,
    *,
    windows: bool = False,
    include_block_volume: bool = False,
) -> tuple[PricingIdentity, ...]:
    """Reuse exact OCI allowlisted shape keys, with no invented SKUs or unit prices."""

    family = resolve_compute_price_family(shape)
    keys = OCI_COMPUTE_PRICE_KEYS[family]
    identities = [
        PricingIdentity("oci", OCI_SERVICE_COMPUTE, keys.ocpu_sku, OCI_UNIT_OCPU_HOUR),
        PricingIdentity("oci", OCI_SERVICE_COMPUTE, keys.memory_sku, OCI_UNIT_GB_RAM_HOUR),
    ]
    if windows:
        identities.append(
            PricingIdentity("oci", OCI_SERVICE_COMPUTE, OCI_WINDOWS_LICENSE_SKU, OCI_UNIT_OCPU_HOUR)
        )
    if include_block_volume:
        identities.extend(
            [
                PricingIdentity(
                    "oci", OCI_SERVICE_BLOCK_VOLUME, OCI_BLOCK_STORAGE_SKU, OCI_UNIT_GB_MONTH
                ),
                PricingIdentity(
                    "oci", OCI_SERVICE_BLOCK_VOLUME, OCI_BLOCK_VPU_SKU, OCI_UNIT_VPU_GB_MONTH
                ),
            ]
        )
    return tuple(identities)


@dataclass(frozen=True, slots=True)
class AwsFinancialBreakdown:
    original_usd: Decimal
    discount_amount_usd: Decimal
    net_usd: Decimal
    converted_brl: Decimal | None
    tax_amount_brl: Decimal | None
    final_amount: Decimal
    final_currency: Literal["USD", "BRL"]


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def apply_aws_financial_terms(
    *,
    eligible_original_usd: Decimal,
    noneligible_original_usd: Decimal,
    terms: AwsFinancialTerms,
) -> AwsFinancialBreakdown:
    """Apply discount -> manual USD/BRL -> tax, without altering catalog prices.

    Financial computation here is only the pure contractual adjustment step.
    Quantity, duration, metering and price composition are Task 27.2 concerns.
    Intermediate calculations retain Decimal precision; output uses half-up cents.
    """

    if any(
        not isinstance(value, Decimal) or not value.is_finite() or value < 0
        for value in (eligible_original_usd, noneligible_original_usd)
    ):
        raise ValueError("USD component totals must be non-negative finite Decimals")
    original = eligible_original_usd + noneligible_original_usd
    discount = eligible_original_usd * terms.discount_percent / Decimal("100")
    net = original - discount

    if not terms.conversion_enabled:
        return AwsFinancialBreakdown(
            original_usd=_money(original),
            discount_amount_usd=_money(discount),
            net_usd=_money(net),
            converted_brl=None,
            tax_amount_brl=None,
            final_amount=_money(net),
            final_currency="USD",
        )

    assert terms.usd_brl_rate is not None  # Validated by AwsFinancialTerms.
    converted = net * terms.usd_brl_rate
    tax = converted * terms.tax_percent / Decimal("100")
    return AwsFinancialBreakdown(
        original_usd=_money(original),
        discount_amount_usd=_money(discount),
        net_usd=_money(net),
        converted_brl=_money(converted),
        tax_amount_brl=_money(tax),
        final_amount=_money(converted + tax),
        final_currency="BRL",
    )
