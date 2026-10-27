"""OCI pricing formulas backed by the persistent Aven Pricing Catalog.

The approved OCI commercial rates are no longer embedded in application code.
Task 23.7 migrates those values to ``pricing_catalog_items`` and this module keeps
only stable pricing keys, formulas, the exact supported-shape allowlist and the
744-hour monthly Compute convention.

The imported OCI calculator is denominated in BRL. Every lookup therefore asks
the provider-neutral resolver for an explicit BRL price. A missing, ambiguous or
unexpected-currency catalog row is a configuration error and is never converted
to a zero-valued cost.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final

from app.services.pricing_catalog import (
    PriceResolver,
    PricingResolver,
    PricingSnapshot,
    ResolvedPrice,
)

OCI_PRICING_SOURCE: Final = "IMPORTED_OCI_CALCULATOR"
OCI_PRICING_VERSION: Final = "2026-10"
OCI_PRICING_CURRENCY: Final = "BRL"
OCI_MONTHLY_HOURS: Final = Decimal("744")
OCI_MONEY_QUANTUM: Final = Decimal("0.01")

OCI_SERVICE_COMPUTE: Final = "compute"
OCI_SERVICE_BLOCK_VOLUME: Final = "block_volume"
OCI_UNIT_OCPU_HOUR: Final = "OCPU_HOUR"
OCI_UNIT_GB_RAM_HOUR: Final = "GB_RAM_HOUR"
OCI_UNIT_GB_MONTH: Final = "GB_MONTH"
OCI_UNIT_VPU_GB_MONTH: Final = "VPU_GB_MONTH"
OCI_WINDOWS_LICENSE_SKU: Final = "WINDOWS_LICENSE_OCPU"
OCI_BLOCK_STORAGE_SKU: Final = "BLOCK_VOLUME_GB_MONTH"
OCI_BLOCK_VPU_SKU: Final = "BLOCK_VOLUME_VPU_GB_MONTH"

PRICING_STATUS_PRICED: Final = "priced"
PRICING_STATUS_UNSUPPORTED_SHAPE: Final = "unsupported_shape"
PRICING_STATUS_MISSING_INPUT: Final = "missing_pricing_input"
PRICING_STATUS_INVALID_INPUT: Final = "invalid_pricing_input"


class OciPricingError(ValueError):
    """Base error for unsupported or invalid OCI pricing input."""


class UnsupportedOciComputeFamilyError(OciPricingError):
    """Raised when no approved pricing key exists for a requested Compute family."""


class UnsupportedOciComputeShapeError(OciPricingError):
    """Raised when no approved Compute pricing family exists for an OCI shape."""


class InvalidOciPricingInputError(OciPricingError):
    """Raised when a pricing input is missing or invalid."""


@dataclass(frozen=True)
class OciComputePriceKeys:
    ocpu_sku: str
    memory_sku: str


@dataclass(frozen=True)
class OciPricingMetadata:
    source: str
    version: str
    currency: str
    monthly_hours: Decimal


@dataclass(frozen=True)
class OciPricingComponent:
    """Exact catalog version plus the monetary snapshot used by one formula component."""

    pricing_item_id: str
    service: str
    sku: str
    unit: str
    unit_price: Decimal
    currency: str
    source: str
    effective_from: datetime
    effective_until: datetime | None
    quantity: Decimal

    def as_evidence(self) -> dict[str, str | None]:
        return {
            "pricing_item_id": self.pricing_item_id,
            "service": self.service,
            "sku": self.sku,
            "unit": self.unit,
            "unit_price": format(self.unit_price, "f"),
            "currency": self.currency,
            "source": self.source,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": (
                self.effective_until.isoformat() if self.effective_until is not None else None
            ),
            "quantity": format(self.quantity, "f"),
        }


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
    windows_monthly_cost: Decimal | None = None
    base_monthly_cost: Decimal | None = None
    windows_license_included: bool = False
    reason: str | None = None
    pricing_components: tuple[OciPricingComponent, ...] = ()

    @property
    def financial_value_populated(self) -> bool:
        return self.status == PRICING_STATUS_PRICED and self.base_monthly_cost is not None


@dataclass(frozen=True)
class OciBlockVolumePricingResult:
    monthly_cost: Decimal
    currency: str
    size_gb: Decimal
    vpus_per_gb: Decimal
    pricing_components: tuple[OciPricingComponent, ...]


OCI_COMPUTE_PRICE_KEYS: Final[Mapping[str, OciComputePriceKeys]] = MappingProxyType(
    {
        "E3": OciComputePriceKeys(
            ocpu_sku="VM.Standard.E3.Flex.OCPU",
            memory_sku="VM.Standard.E3.Flex.Memory",
        ),
        "E4": OciComputePriceKeys(
            ocpu_sku="VM.Standard.E4.Flex.OCPU",
            memory_sku="VM.Standard.E4.Flex.Memory",
        ),
        "E5": OciComputePriceKeys(
            ocpu_sku="VM.Standard.E5.Flex.OCPU",
            memory_sku="VM.Standard.E5.Flex.Memory",
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


def _compute_family(family: str | None) -> tuple[str, OciComputePriceKeys]:
    if family is None or not isinstance(family, str) or not family.strip():
        raise InvalidOciPricingInputError("family must be provided")
    normalized = family.strip().upper()
    try:
        return normalized, OCI_COMPUTE_PRICE_KEYS[normalized]
    except KeyError as exc:
        raise UnsupportedOciComputeFamilyError(
            f"unsupported OCI Compute family: {family!r}"
        ) from exc


def _source_of(*prices: ResolvedPrice) -> str:
    sources = {price.source for price in prices}
    return next(iter(sources)) if len(sources) == 1 else "MULTIPLE_SOURCES"


def _component(price: ResolvedPrice, *, quantity: Decimal) -> OciPricingComponent:
    return OciPricingComponent(
        pricing_item_id=price.id,
        service=price.service,
        sku=price.sku,
        unit=price.unit,
        unit_price=price.amount,
        currency=price.currency,
        source=price.source,
        effective_from=price.effective_from,
        effective_until=price.effective_until,
        quantity=quantity,
    )


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
    """OCI cost formulas whose unit rates come only from the Pricing Catalog."""

    def __init__(self, resolver: PriceResolver | None = None) -> None:
        self._resolver = resolver
        self._catalog_snapshot: PricingSnapshot | None = None

    @property
    def metadata(self) -> OciPricingMetadata:
        return OCI_PRICING_METADATA

    def clear_cache(self) -> None:
        """Discard the process-local read snapshot so a subsequent call reloads the DB catalog."""

        self._catalog_snapshot = None

    def _catalog(self, *, at: datetime | None = None) -> PriceResolver:
        if self._resolver is not None:
            return self._resolver
        if at is None and self._catalog_snapshot is not None:
            return self._catalog_snapshot

        from app.db.session import SessionLocal

        with SessionLocal() as db:
            snapshot = PricingResolver(db, reference_at=at).snapshot(
                provider="oci",
                expected_currency=OCI_PRICING_CURRENCY,
            )
        if at is None:
            self._catalog_snapshot = snapshot
        return snapshot

    @staticmethod
    def _price(
        catalog: PriceResolver,
        *,
        service: str,
        sku: str,
        unit: str,
        at: datetime | None = None,
    ) -> ResolvedPrice:
        return catalog.resolve_price(
            provider="oci",
            service=service,
            sku=sku,
            unit=unit,
            at=at,
            expected_currency=OCI_PRICING_CURRENCY,
        )

    def compute_monthly_pricing(
        self,
        *,
        family: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        include_windows_license: bool = False,
        shape: str | None = None,
        at: datetime | None = None,
    ) -> OciComputePricingResult:
        """Calculate monthly Compute and retain every catalog version used."""

        normalized_family, keys = _compute_family(family)
        ocpu_count = _positive_compute_input("ocpus", ocpus)
        memory = _positive_compute_input("memory_gb", memory_gb)
        if not isinstance(include_windows_license, bool):
            raise InvalidOciPricingInputError("include_windows_license must be a boolean")

        catalog = self._catalog(at=at)
        ocpu_price = self._price(
            catalog,
            service=OCI_SERVICE_COMPUTE,
            sku=keys.ocpu_sku,
            unit=OCI_UNIT_OCPU_HOUR,
            at=at,
        )
        memory_price = self._price(
            catalog,
            service=OCI_SERVICE_COMPUTE,
            sku=keys.memory_sku,
            unit=OCI_UNIT_GB_RAM_HOUR,
            at=at,
        )
        resolved_prices = [ocpu_price, memory_price]
        components = [
            _component(ocpu_price, quantity=ocpu_count * OCI_MONTHLY_HOURS),
            _component(memory_price, quantity=memory * OCI_MONTHLY_HOURS),
        ]

        raw_ocpu_cost = ocpu_count * ocpu_price.amount * OCI_MONTHLY_HOURS
        raw_memory_cost = memory * memory_price.amount * OCI_MONTHLY_HOURS
        raw_total = raw_ocpu_cost + raw_memory_cost
        windows_monthly_cost = Decimal("0")
        if include_windows_license:
            windows_price = self._price(
                catalog,
                service=OCI_SERVICE_COMPUTE,
                sku=OCI_WINDOWS_LICENSE_SKU,
                unit=OCI_UNIT_OCPU_HOUR,
                at=at,
            )
            resolved_prices.append(windows_price)
            components.append(_component(windows_price, quantity=ocpu_count * OCI_MONTHLY_HOURS))
            windows_monthly_cost = quantize_money(
                ocpu_count * windows_price.amount * OCI_MONTHLY_HOURS
            )
            raw_total += ocpu_count * windows_price.amount * OCI_MONTHLY_HOURS

        return OciComputePricingResult(
            status=PRICING_STATUS_PRICED,
            source=_source_of(*resolved_prices),
            version=OCI_PRICING_VERSION,
            currency=OCI_PRICING_CURRENCY,
            monthly_hours=OCI_MONTHLY_HOURS,
            shape=shape,
            family=normalized_family,
            ocpus=ocpu_count,
            memory_gb=memory,
            ocpu_monthly_cost=quantize_money(raw_ocpu_cost),
            memory_monthly_cost=quantize_money(raw_memory_cost),
            windows_monthly_cost=windows_monthly_cost,
            base_monthly_cost=quantize_money(raw_total),
            windows_license_included=include_windows_license,
            pricing_components=tuple(components),
        )

    def compute_monthly_cost(
        self,
        *,
        family: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        include_windows_license: bool = False,
        at: datetime | None = None,
    ) -> Decimal:
        result = self.compute_monthly_pricing(
            family=family,
            ocpus=ocpus,
            memory_gb=memory_gb,
            include_windows_license=include_windows_license,
            at=at,
        )
        assert result.base_monthly_cost is not None
        return result.base_monthly_cost

    def windows_license_monthly_cost(
        self,
        *,
        ocpus: Decimal | int | float | str | None,
        at: datetime | None = None,
    ) -> Decimal:
        ocpu_count = _positive_compute_input("ocpus", ocpus)
        catalog = self._catalog(at=at)
        price = self._price(
            catalog,
            service=OCI_SERVICE_COMPUTE,
            sku=OCI_WINDOWS_LICENSE_SKU,
            unit=OCI_UNIT_OCPU_HOUR,
            at=at,
        )
        return quantize_money(ocpu_count * price.amount * OCI_MONTHLY_HOURS)

    def price_compute_resource(
        self,
        *,
        shape: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        at: datetime | None = None,
    ) -> OciComputePricingResult:
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
                at=at,
            )
        except InvalidOciPricingInputError as exc:
            return _empty_compute_result(
                status=PRICING_STATUS_INVALID_INPUT,
                shape=shape,
                family=family,
                reason=str(exc),
            )

    def block_volume_monthly_pricing(
        self,
        *,
        size_gb: Decimal | int | str | None,
        vpus_per_gb: Decimal | int | str | None,
        at: datetime | None = None,
    ) -> OciBlockVolumePricingResult:
        """Calculate Block Volume and retain both capacity and VPU catalog versions."""

        size = _decimal_input("size_gb", size_gb)
        vpus = _decimal_input("vpus_per_gb", vpus_per_gb)
        catalog = self._catalog(at=at)
        storage_price = self._price(
            catalog,
            service=OCI_SERVICE_BLOCK_VOLUME,
            sku=OCI_BLOCK_STORAGE_SKU,
            unit=OCI_UNIT_GB_MONTH,
            at=at,
        )
        vpu_price = self._price(
            catalog,
            service=OCI_SERVICE_BLOCK_VOLUME,
            sku=OCI_BLOCK_VPU_SKU,
            unit=OCI_UNIT_VPU_GB_MONTH,
            at=at,
        )
        monthly = size * storage_price.amount + size * vpus * vpu_price.amount
        return OciBlockVolumePricingResult(
            monthly_cost=quantize_money(monthly),
            currency=OCI_PRICING_CURRENCY,
            size_gb=size,
            vpus_per_gb=vpus,
            pricing_components=(
                _component(storage_price, quantity=size),
                _component(vpu_price, quantity=size * vpus),
            ),
        )

    def block_volume_monthly_cost(
        self,
        *,
        size_gb: Decimal | int | str | None,
        vpus_per_gb: Decimal | int | str | None,
        at: datetime | None = None,
    ) -> Decimal:
        return self.block_volume_monthly_pricing(
            size_gb=size_gb,
            vpus_per_gb=vpus_per_gb,
            at=at,
        ).monthly_cost
