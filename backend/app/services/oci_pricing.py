"""Centralized, versioned OCI pricing for deterministic DeepOps estimates.

Prices in this module come from the approved DeepOps OCI commercial price table.
They are denominated in BRL, use 744 hours per month for Compute, and represent
cost before taxes. The spreadsheet tax factor is intentionally not applied.

The catalog is versioned in code so analyzers can depend on this service rather
than embedding rates or formulas. A future contract/API-backed implementation
can replace the catalog without changing analyzer-facing pricing semantics.

Compute shape resolution is an explicit allowlist. Only commercially validated
OCI shapes belong in ``OCI_SHAPE_PRICE_FAMILY``; absence from the mapping means
unsupported. Do not infer pricing families from substrings, prefixes, regexes,
or case-normalized shape names. The current allowlist covers only E3/E4/E5 Flex.

Compute pricing uses ``OCPU * OCPU/hour * 744 + RAM GB * RAM GB/hour * 744``.
Windows licensing is never inferred or applied automatically by the resource
pricing API in this task; callers that explicitly need it must use the lower-
level family API with ``include_windows_license=True``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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

PRICING_STATUS_PRICED: Final = "priced"
PRICING_STATUS_UNSUPPORTED_SHAPE: Final = "unsupported_shape"
PRICING_STATUS_MISSING_INPUT: Final = "missing_pricing_input"
PRICING_STATUS_INVALID_INPUT: Final = "invalid_pricing_input"


class OciPricingError(ValueError):
    """Base error for unsupported or invalid OCI pricing input."""


class UnsupportedOciComputeFamilyError(OciPricingError):
    """Raised when no approved price exists for a requested Compute family."""


class UnsupportedOciComputeShapeError(OciPricingError):
    """Raised when no approved Compute pricing family exists for an OCI shape."""


class InvalidOciPricingInputError(OciPricingError):
    """Raised when a pricing input is missing or invalid."""


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


@dataclass(frozen=True)
class OciComputePricingResult:
    """Explainable OCI Compute pricing result for resource-level consumers."""

    status: str
    source: str
    version: str
    currency: str
    monthly_hours: Decimal
    shape: str | None = None
    family: str | None = None
    ocpus: Decimal | None = None
    memory_gb: Decimal | None = None
    ocpu_monthly_cost: Decimal | None = None
    memory_monthly_cost: Decimal | None = None
    base_monthly_cost: Decimal | None = None
    windows_license_included: bool = False
    reason: str | None = None

    @property
    def financial_value_populated(self) -> bool:
        return self.status == PRICING_STATUS_PRICED and self.base_monthly_cost is not None


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

OCI_SHAPE_PRICE_FAMILY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "VM.Standard.E3.Flex": "E3",
        "VM.Standard.E4.Flex": "E4",
        "VM.Standard.E5.Flex": "E5",
    }
)

OCI_PRICING_METADATA: Final = OciPricingMetadata(
    source=OCI_PRICING_SOURCE,
    version=OCI_PRICING_VERSION,
    currency=OCI_PRICING_CURRENCY,
    monthly_hours=OCI_MONTHLY_HOURS,
)


def resolve_compute_price_family(shape: str | None) -> str:
    """Resolve an exact OCI shape name to an approved Compute pricing family."""

    if shape is None or not isinstance(shape, str) or not shape.strip():
        raise InvalidOciPricingInputError("shape must be provided")
    try:
        return OCI_SHAPE_PRICE_FAMILY[shape]
    except KeyError as exc:
        raise UnsupportedOciComputeShapeError(f"unsupported OCI Compute shape: {shape!r}") from exc


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary result to BRL cents using ROUND_HALF_UP."""

    return value.quantize(OCI_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _decimal_input(
    name: str,
    value: Decimal | int | float | str | None,
    *,
    allow_float: bool = False,
) -> Decimal:
    if value is None or isinstance(value, bool) or (isinstance(value, float) and not allow_float):
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


def _positive_compute_input(name: str, value: Decimal | int | float | str | None) -> Decimal:
    parsed = _decimal_input(name, value, allow_float=True)
    if parsed <= 0:
        raise InvalidOciPricingInputError(f"{name} must be greater than zero for OCI Flex Compute")
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


def _empty_compute_result(
    *,
    status: str,
    shape: str | None,
    family: str | None = None,
    reason: str | None = None,
) -> OciComputePricingResult:
    return OciComputePricingResult(
        status=status,
        source=OCI_PRICING_SOURCE,
        version=OCI_PRICING_VERSION,
        currency=OCI_PRICING_CURRENCY,
        monthly_hours=OCI_MONTHLY_HOURS,
        shape=shape,
        family=family,
        windows_license_included=False,
        reason=reason,
    )


class OciPricingService:
    """Pure OCI cost calculations over simple domain values, without OCI SDK coupling."""

    @property
    def metadata(self) -> OciPricingMetadata:
        return OCI_PRICING_METADATA

    def compute_monthly_pricing(
        self,
        *,
        family: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        include_windows_license: bool = False,
        shape: str | None = None,
    ) -> OciComputePricingResult:
        """Calculate an explainable monthly Compute result from an approved family."""

        normalized_family, prices = _compute_family(family)
        ocpu_count = _positive_compute_input("ocpus", ocpus)
        memory = _positive_compute_input("memory_gb", memory_gb)
        if not isinstance(include_windows_license, bool):
            raise InvalidOciPricingInputError("include_windows_license must be a boolean")

        raw_ocpu_cost = ocpu_count * prices.ocpu_hour * OCI_MONTHLY_HOURS
        raw_memory_cost = memory * prices.memory_gb_hour * OCI_MONTHLY_HOURS
        raw_base_cost = raw_ocpu_cost + raw_memory_cost
        raw_total = raw_base_cost
        if include_windows_license:
            raw_total += ocpu_count * OCI_WINDOWS_OCPU_HOUR * OCI_MONTHLY_HOURS

        return OciComputePricingResult(
            status=PRICING_STATUS_PRICED,
            source=OCI_PRICING_SOURCE,
            version=OCI_PRICING_VERSION,
            currency=OCI_PRICING_CURRENCY,
            monthly_hours=OCI_MONTHLY_HOURS,
            shape=shape,
            family=normalized_family,
            ocpus=ocpu_count,
            memory_gb=memory,
            ocpu_monthly_cost=quantize_money(raw_ocpu_cost),
            memory_monthly_cost=quantize_money(raw_memory_cost),
            base_monthly_cost=quantize_money(raw_total),
            windows_license_included=include_windows_license,
        )

    def compute_monthly_cost(
        self,
        *,
        family: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        include_windows_license: bool = False,
    ) -> Decimal:
        """Backward-compatible family API returning only the monthly monetary value."""

        result = self.compute_monthly_pricing(
            family=family,
            ocpus=ocpus,
            memory_gb=memory_gb,
            include_windows_license=include_windows_license,
        )
        assert result.base_monthly_cost is not None
        return result.base_monthly_cost

    def price_compute_resource(
        self,
        *,
        shape: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
    ) -> OciComputePricingResult:
        """Resolve an OCI shape and return base Compute pricing without Windows licensing.

        Unsupported shapes and expected resource-data problems are represented as
        domain statuses rather than valid zero-valued prices.
        """

        try:
            family = resolve_compute_price_family(shape)
        except UnsupportedOciComputeShapeError as exc:
            return _empty_compute_result(
                status=PRICING_STATUS_UNSUPPORTED_SHAPE,
                shape=shape,
                reason=str(exc),
            )
        except InvalidOciPricingInputError as exc:
            return _empty_compute_result(
                status=PRICING_STATUS_MISSING_INPUT,
                shape=shape,
                reason=str(exc),
            )

        if ocpus is None:
            return _empty_compute_result(
                status=PRICING_STATUS_MISSING_INPUT,
                shape=shape,
                family=family,
                reason="ocpus must be provided",
            )
        if memory_gb is None:
            return _empty_compute_result(
                status=PRICING_STATUS_MISSING_INPUT,
                shape=shape,
                family=family,
                reason="memory_gb must be provided",
            )

        try:
            return self.compute_monthly_pricing(
                family=family,
                ocpus=ocpus,
                memory_gb=memory_gb,
                include_windows_license=False,
                shape=shape,
            )
        except InvalidOciPricingInputError as exc:
            return _empty_compute_result(
                status=PRICING_STATUS_INVALID_INPUT,
                shape=shape,
                family=family,
                reason=str(exc),
            )

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
