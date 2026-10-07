"""Centralized, versioned OCI pricing for deterministic DeepOps estimates.

Prices in this module come from the approved DeepOps OCI commercial price table.
They are denominated in BRL, use 744 hours per month for Compute, and represent
cost before taxes. The spreadsheet tax factor is intentionally not applied.

The catalog is versioned in code so analyzers can depend on this service rather
than embedding rates or formulas. A future contract/API-backed implementation
can replace the catalog without changing analyzer-facing pricing semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import MappingProxyType
from typing import Final

OCI_PRICING_SOURCE: Final = "deepops_oci_price_table"
OCI_PRICING_VERSION: Final = "2026-10"
OCI_PRICING_CURRENCY: Final = "BRL"
OCI_MONTHLY_HOURS: Final = Decimal("744")
OCI_MONEY_QUANTUM: Final = Decimal("0.01")
OCI_WINDOWS_OCPU_HOUR: Final = Decimal("0.46092")
OCI_BLOCK_STORAGE_GB_MONTH: Final = Decimal("0.0531")
OCI_BLOCK_VPU_GB_MONTH: Final = Decimal("0.0036")


class OciPricingError(ValueError):
    """Base error for unsupported or invalid OCI pricing input."""


class UnsupportedOciComputeFamilyError(OciPricingError):
    """Raised when no approved price exists for a requested Compute family."""


class InvalidOciPricingInputError(OciPricingError):
    """Raised when a pricing input is missing, non-decimal, or negative."""


@dataclass(frozen=True)
class OciComputePrice:
    ocpu_hour: Decimal
    memory_gb_hour: Decimal


@dataclass(frozen=True)
class OciPricingMetadata:
    source: str
    version: str
    currency: str
    monthly_hours: Decimal


OCI_COMPUTE_PRICES: Final[Mapping[str, OciComputePrice]] = MappingProxyType(
    {
        "E3": OciComputePrice(
            ocpu_hour=Decimal("0.0521"),
            memory_gb_hour=Decimal("0.0031"),
        ),
        "E4": OciComputePrice(
            ocpu_hour=Decimal("0.0689"),
            memory_gb_hour=Decimal("0.0041"),
        ),
        "E5": OciComputePrice(
            ocpu_hour=Decimal("0.08266"),
            memory_gb_hour=Decimal("0.005511"),
        ),
    }
)

OCI_PRICING_METADATA: Final = OciPricingMetadata(
    source=OCI_PRICING_SOURCE,
    version=OCI_PRICING_VERSION,
    currency=OCI_PRICING_CURRENCY,
    monthly_hours=OCI_MONTHLY_HOURS,
)


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary result to BRL cents using ROUND_HALF_UP."""

    return value.quantize(OCI_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _decimal_input(name: str, value: Decimal | int | str | None) -> Decimal:
    if value is None or isinstance(value, (bool, float)):
        raise InvalidOciPricingInputError(
            f"{name} must be provided as Decimal, int, or decimal string"
        )
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidOciPricingInputError(f"{name} must be a valid decimal value") from exc
    if not parsed.is_finite():
        raise InvalidOciPricingInputError(f"{name} must be a finite decimal value")
    if parsed < 0:
        raise InvalidOciPricingInputError(f"{name} cannot be negative")
    return parsed


def _compute_family(family: str | None) -> tuple[str, OciComputePrice]:
    if family is None or not isinstance(family, str) or not family.strip():
        raise InvalidOciPricingInputError("family must be provided")
    normalized = family.strip().upper()
    try:
        return normalized, OCI_COMPUTE_PRICES[normalized]
    except KeyError as exc:
        raise UnsupportedOciComputeFamilyError(
            f"unsupported OCI Compute family: {family!r}"
        ) from exc


class OciPricingService:
    """Pure OCI cost calculations over simple domain values, without OCI SDK coupling."""

    @property
    def metadata(self) -> OciPricingMetadata:
        return OCI_PRICING_METADATA

    def compute_monthly_cost(
        self,
        *,
        family: str | None,
        ocpus: Decimal | int | str | None,
        memory_gb: Decimal | int | str | None,
        include_windows_license: bool = False,
    ) -> Decimal:
        _, prices = _compute_family(family)
        ocpu_count = _decimal_input("ocpus", ocpus)
        memory = _decimal_input("memory_gb", memory_gb)
        if not isinstance(include_windows_license, bool):
            raise InvalidOciPricingInputError("include_windows_license must be a boolean")

        monthly = (
            ocpu_count * prices.ocpu_hour * OCI_MONTHLY_HOURS
            + memory * prices.memory_gb_hour * OCI_MONTHLY_HOURS
        )
        if include_windows_license:
            monthly += ocpu_count * OCI_WINDOWS_OCPU_HOUR * OCI_MONTHLY_HOURS
        return quantize_money(monthly)

    def block_volume_monthly_cost(
        self,
        *,
        size_gb: Decimal | int | str | None,
        vpus_per_gb: Decimal | int | str | None,
    ) -> Decimal:
        size = _decimal_input("size_gb", size_gb)
        vpus = _decimal_input("vpus_per_gb", vpus_per_gb)
        monthly = size * OCI_BLOCK_STORAGE_GB_MONTH + size * vpus * OCI_BLOCK_VPU_GB_MONTH
        return quantize_money(monthly)
