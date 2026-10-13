from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Protocol

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.pricing import PricingCatalogItem

logger = logging.getLogger("deepops.pricing")


class PricingCatalogError(RuntimeError):
    """Base error for invalid or incomplete pricing catalog configuration."""


class PricingNotFoundError(PricingCatalogError):
    """No enabled price is effective for the requested pricing identity."""


class PricingAmbiguityError(PricingCatalogError):
    """More than one enabled price is effective for the same pricing identity."""


class PricingCurrencyMismatchError(PricingCatalogError):
    """The resolved price is denominated in a currency the caller did not expect."""


@dataclass(frozen=True, slots=True)
class PricingIdentity:
    provider: str
    service: str
    sku: str
    unit: str


@dataclass(frozen=True, slots=True)
class ResolvedPrice:
    id: str
    provider: str
    service: str
    sku: str
    description: str
    unit: str
    amount: Decimal
    currency: str
    effective_from: datetime
    effective_until: datetime | None
    source: str

    @property
    def identity(self) -> PricingIdentity:
        return PricingIdentity(self.provider, self.service, self.sku, self.unit)


class PriceResolver(Protocol):
    def resolve_price(
        self,
        *,
        provider: str,
        service: str,
        sku: str,
        unit: str,
        at: datetime | None = None,
        expected_currency: str | None = None,
    ) -> ResolvedPrice: ...


def _utc_reference(value: datetime | None) -> datetime:
    reference = value or datetime.now(UTC)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=UTC)
    return reference.astimezone(UTC)


def _identity(provider: str, service: str, sku: str, unit: str) -> PricingIdentity:
    return PricingIdentity(
        provider=provider.strip().lower(),
        service=service.strip().lower(),
        sku=sku.strip(),
        unit=unit.strip().upper(),
    )


def _resolved(item: PricingCatalogItem) -> ResolvedPrice:
    return ResolvedPrice(
        id=item.id,
        provider=item.provider,
        service=item.service,
        sku=item.sku,
        description=item.description,
        unit=item.unit,
        amount=Decimal(item.price),
        currency=item.currency,
        effective_from=item.effective_from,
        effective_until=item.effective_until,
        source=item.source,
    )


def _validate_currency(price: ResolvedPrice, expected_currency: str | None) -> None:
    if expected_currency is None:
        return
    normalized = expected_currency.strip().upper()
    if price.currency != normalized:
        logger.error(
            "event=pricing_currency_mismatch provider=%s service=%s sku=%s unit=%s "
            "expected_currency=%s actual_currency=%s",
            price.provider,
            price.service,
            price.sku,
            price.unit,
            normalized,
            price.currency,
        )
        raise PricingCurrencyMismatchError(
            f"pricing currency mismatch for {price.provider}/{price.service}/{price.sku}/"
            f"{price.unit}: expected {normalized}, found {price.currency}"
        )


class PricingSnapshot:
    """Immutable batch snapshot of all effective prices for one provider/date."""

    def __init__(
        self,
        *,
        provider: str,
        reference_at: datetime,
        items: Mapping[PricingIdentity, ResolvedPrice],
    ) -> None:
        self.provider = provider
        self.reference_at = reference_at
        self._items = MappingProxyType(dict(items))

    @property
    def items(self) -> Mapping[PricingIdentity, ResolvedPrice]:
        return self._items

    def resolve_price(
        self,
        *,
        provider: str,
        service: str,
        sku: str,
        unit: str,
        at: datetime | None = None,
        expected_currency: str | None = None,
    ) -> ResolvedPrice:
        requested_at = self.reference_at if at is None else _utc_reference(at)
        if requested_at != self.reference_at:
            raise PricingCatalogError(
                "pricing snapshot cannot resolve a different reference date; create another snapshot"
            )
        identity = _identity(provider, service, sku, unit)
        price = self._items.get(identity)
        if price is None:
            logger.error(
                "event=pricing_not_found provider=%s service=%s sku=%s unit=%s",
                identity.provider,
                identity.service,
                identity.sku,
                identity.unit,
            )
            raise PricingNotFoundError(
                f"pricing not found for {identity.provider}/{identity.service}/{identity.sku}/"
                f"{identity.unit} at {self.reference_at.isoformat()}"
            )
        _validate_currency(price, expected_currency)
        return price


class PricingResolver:
    """Resolve provider-neutral effective-dated prices from the persistent catalog."""

    def __init__(self, db: Session, *, reference_at: datetime | None = None) -> None:
        self._db = db
        self.reference_at = _utc_reference(reference_at)
        self._cache: dict[tuple[PricingIdentity, datetime], ResolvedPrice] = {}

    @staticmethod
    def _effective_query(reference_at: datetime) -> Select[tuple[PricingCatalogItem]]:
        return select(PricingCatalogItem).where(
            PricingCatalogItem.enabled.is_(True),
            PricingCatalogItem.effective_from <= reference_at,
            or_(
                PricingCatalogItem.effective_until.is_(None),
                reference_at < PricingCatalogItem.effective_until,
            ),
        )

    def snapshot(
        self,
        *,
        provider: str,
        at: datetime | None = None,
        expected_currency: str | None = None,
    ) -> PricingSnapshot:
        reference = self.reference_at if at is None else _utc_reference(at)
        normalized_provider = provider.strip().lower()
        rows = self._db.scalars(
            self._effective_query(reference).where(
                PricingCatalogItem.provider == normalized_provider
            )
        ).all()
        items: dict[PricingIdentity, ResolvedPrice] = {}
        for row in rows:
            price = _resolved(row)
            identity = price.identity
            if identity in items:
                logger.error(
                    "event=pricing_ambiguous provider=%s service=%s sku=%s unit=%s",
                    identity.provider,
                    identity.service,
                    identity.sku,
                    identity.unit,
                )
                raise PricingAmbiguityError(
                    f"multiple effective prices for {identity.provider}/{identity.service}/"
                    f"{identity.sku}/{identity.unit} at {reference.isoformat()}"
                )
            _validate_currency(price, expected_currency)
            items[identity] = price
            self._cache[(identity, reference)] = price
        return PricingSnapshot(
            provider=normalized_provider,
            reference_at=reference,
            items=items,
        )

    def resolve_price(
        self,
        *,
        provider: str,
        service: str,
        sku: str,
        unit: str,
        at: datetime | None = None,
        expected_currency: str | None = None,
    ) -> ResolvedPrice:
        reference = self.reference_at if at is None else _utc_reference(at)
        identity = _identity(provider, service, sku, unit)
        cached = self._cache.get((identity, reference))
        if cached is not None:
            _validate_currency(cached, expected_currency)
            return cached

        rows = self._db.scalars(
            self._effective_query(reference).where(
                PricingCatalogItem.provider == identity.provider,
                PricingCatalogItem.service == identity.service,
                PricingCatalogItem.sku == identity.sku,
                PricingCatalogItem.unit == identity.unit,
            )
        ).all()
        if not rows:
            logger.error(
                "event=pricing_not_found provider=%s service=%s sku=%s unit=%s",
                identity.provider,
                identity.service,
                identity.sku,
                identity.unit,
            )
            raise PricingNotFoundError(
                f"pricing not found for {identity.provider}/{identity.service}/{identity.sku}/"
                f"{identity.unit} at {reference.isoformat()}"
            )
        if len(rows) > 1:
            logger.error(
                "event=pricing_ambiguous provider=%s service=%s sku=%s unit=%s",
                identity.provider,
                identity.service,
                identity.sku,
                identity.unit,
            )
            raise PricingAmbiguityError(
                f"multiple effective prices for {identity.provider}/{identity.service}/"
                f"{identity.sku}/{identity.unit} at {reference.isoformat()}"
            )

        price = _resolved(rows[0])
        _validate_currency(price, expected_currency)
        self._cache[(identity, reference)] = price
        return price
