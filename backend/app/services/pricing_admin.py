from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.pricing import PricingCatalogItem

PricingStatus = Literal["active", "inactive", "future", "expired", "all"]


class PricingAdminError(RuntimeError):
    code = "pricing_admin_error"


class PricingAdminNotFoundError(PricingAdminError):
    code = "pricing_not_found"


class PricingAdminConflictError(PricingAdminError):
    code = "pricing_overlap"


class PricingAdminValidationError(PricingAdminError):
    code = "pricing_invalid"


def _utc(value: datetime | None) -> datetime:
    current = value or utcnow()
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _clean_identity(
    provider: str,
    service: str,
    sku: str,
    unit: str,
) -> tuple[str, str, str, str]:
    return (
        provider.strip().lower(),
        service.strip().lower(),
        sku.strip(),
        unit.strip().upper(),
    )


def lifecycle_status(item: PricingCatalogItem, *, at: datetime | None = None) -> str:
    reference = _utc(at)
    if not item.enabled:
        return "inactive"
    effective_from = _utc(item.effective_from)
    effective_until = _utc(item.effective_until) if item.effective_until else None
    if effective_from > reference:
        return "future"
    if effective_until is not None and effective_until <= reference:
        return "expired"
    return "active"


class PricingCatalogAdminService:
    """Provider-neutral administration rules for the persistent pricing catalog."""

    def __init__(self, db: Session, *, provider: str) -> None:
        self.db = db
        self.provider = provider.strip().lower()

    def list_items(
        self,
        *,
        q: str = "",
        service: str | None = None,
        status: PricingStatus = "active",
        limit: int = 50,
        offset: int = 0,
        at: datetime | None = None,
    ) -> tuple[list[PricingCatalogItem], int]:
        reference = _utc(at)
        filters = [PricingCatalogItem.provider == self.provider]
        query = q.strip()
        if query:
            filters.append(
                or_(
                    PricingCatalogItem.sku.icontains(query, autoescape=True),
                    PricingCatalogItem.description.icontains(query, autoescape=True),
                    PricingCatalogItem.service.icontains(query, autoescape=True),
                )
            )
        if service and service.strip():
            filters.append(PricingCatalogItem.service == service.strip().lower())

        if status == "active":
            filters.extend(
                [
                    PricingCatalogItem.enabled.is_(True),
                    PricingCatalogItem.effective_from <= reference,
                    or_(
                        PricingCatalogItem.effective_until.is_(None),
                        PricingCatalogItem.effective_until > reference,
                    ),
                ]
            )
        elif status == "inactive":
            filters.append(PricingCatalogItem.enabled.is_(False))
        elif status == "future":
            filters.extend(
                [
                    PricingCatalogItem.enabled.is_(True),
                    PricingCatalogItem.effective_from > reference,
                ]
            )
        elif status == "expired":
            filters.extend(
                [
                    PricingCatalogItem.enabled.is_(True),
                    PricingCatalogItem.effective_until.is_not(None),
                    PricingCatalogItem.effective_until <= reference,
                ]
            )
        elif status != "all":
            raise PricingAdminValidationError(f"unsupported pricing status: {status}")

        total = self.db.scalar(
            select(func.count()).select_from(PricingCatalogItem).where(*filters)
        )
        items = list(
            self.db.scalars(
                select(PricingCatalogItem)
                .where(*filters)
                .order_by(
                    PricingCatalogItem.service.asc(),
                    PricingCatalogItem.sku.asc(),
                    PricingCatalogItem.effective_from.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        return items, int(total or 0)

    def get_item(self, item_id: str, *, lock: bool = False) -> PricingCatalogItem:
        statement = select(PricingCatalogItem).where(
            PricingCatalogItem.id == item_id,
            PricingCatalogItem.provider == self.provider,
        )
        if lock:
            statement = statement.with_for_update()
        item = self.db.scalar(statement)
        if item is None:
            raise PricingAdminNotFoundError("pricing item not found")
        return item

    def history(self, item_id: str) -> list[PricingCatalogItem]:
        item = self.get_item(item_id)
        provider, service, sku, unit = _clean_identity(
            item.provider, item.service, item.sku, item.unit
        )
        return list(
            self.db.scalars(
                select(PricingCatalogItem)
                .where(
                    PricingCatalogItem.provider == provider,
                    PricingCatalogItem.service == service,
                    PricingCatalogItem.sku == sku,
                    PricingCatalogItem.unit == unit,
                )
                .order_by(PricingCatalogItem.effective_from.desc(), PricingCatalogItem.id)
            )
        )

    def metadata(self) -> dict[str, list[str]]:
        def distinct(column) -> list[str]:
            return list(
                self.db.scalars(
                    select(column)
                    .where(PricingCatalogItem.provider == self.provider)
                    .distinct()
                    .order_by(column)
                )
            )

        return {
            "services": distinct(PricingCatalogItem.service),
            "units": distinct(PricingCatalogItem.unit),
            "sources": distinct(PricingCatalogItem.source),
        }

    def create_item(
        self,
        *,
        service: str,
        sku: str,
        description: str,
        unit: str,
        price: Decimal,
        currency: str,
        effective_from: datetime,
        effective_until: datetime | None = None,
        enabled: bool = True,
        source: str,
    ) -> PricingCatalogItem:
        provider, normalized_service, normalized_sku, normalized_unit = _clean_identity(
            self.provider, service, sku, unit
        )
        normalized_description = description.strip()
        normalized_currency = currency.strip().upper()
        normalized_source = source.strip().upper()
        start = _utc(effective_from)
        end = _utc(effective_until) if effective_until else None
        self._validate_values(
            service=normalized_service,
            sku=normalized_sku,
            description=normalized_description,
            unit=normalized_unit,
            price=price,
            currency=normalized_currency,
            source=normalized_source,
            effective_from=start,
            effective_until=end,
        )
        identity = (provider, normalized_service, normalized_sku, normalized_unit)
        self._lock_identity(identity)
        if enabled:
            self._ensure_no_overlap(identity, start=start, end=end)

        item = PricingCatalogItem(
            provider=provider,
            service=normalized_service,
            sku=normalized_sku,
            description=normalized_description,
            unit=normalized_unit,
            price=price,
            currency=normalized_currency,
            effective_from=start,
            effective_until=end,
            enabled=enabled,
            source=normalized_source,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def update_item(
        self,
        item_id: str,
        *,
        price: Decimal | None = None,
        description: str | None = None,
        effective_from: datetime | None = None,
        source: str,
    ) -> PricingCatalogItem:
        item = self.get_item(item_id, lock=True)
        identity = _clean_identity(item.provider, item.service, item.sku, item.unit)
        self._lock_identity(identity)
        self.db.refresh(item)

        if price is None:
            if effective_from is not None:
                raise PricingAdminValidationError(
                    "effective_from can only be changed when creating a new price version"
                )
            if description is None:
                raise PricingAdminValidationError("no pricing changes were provided")
            cleaned_description = description.strip()
            if not cleaned_description:
                raise PricingAdminValidationError("description cannot be blank")
            item.description = cleaned_description
            self.db.flush()
            return item

        if price < 0:
            raise PricingAdminValidationError("price must be greater than or equal to zero")
        if not item.enabled:
            raise PricingAdminConflictError(
                "inactive pricing cannot be versioned; create a new price instead"
            )

        transition = _utc(effective_from)
        current_from = _utc(item.effective_from)
        current_until = _utc(item.effective_until) if item.effective_until else None
        if transition <= current_from:
            raise PricingAdminValidationError(
                "new pricing effective_from must be after the current version start"
            )
        if current_until is not None and transition >= current_until:
            raise PricingAdminValidationError(
                "new pricing effective_from must be inside the current version interval"
            )

        self._ensure_no_overlap(
            identity,
            start=transition,
            end=current_until,
            exclude_ids={item.id},
        )

        new_description = description.strip() if description is not None else item.description
        if not new_description:
            raise PricingAdminValidationError("description cannot be blank")

        item.effective_until = transition
        next_item = PricingCatalogItem(
            provider=item.provider,
            service=item.service,
            sku=item.sku,
            description=new_description,
            unit=item.unit,
            price=price,
            currency=item.currency,
            effective_from=transition,
            effective_until=current_until,
            enabled=True,
            source=source.strip().upper(),
        )
        self.db.add(next_item)
        self.db.flush()
        return next_item

    def deactivate(self, item_id: str) -> PricingCatalogItem:
        item = self.get_item(item_id, lock=True)
        identity = _clean_identity(item.provider, item.service, item.sku, item.unit)
        self._lock_identity(identity)
        self.db.refresh(item)
        if not item.enabled:
            return item
        item.enabled = False
        self.db.flush()
        return item

    def _lock_identity(self, identity: tuple[str, str, str, str]) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        key = ":".join(identity)
        self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})

    def _ensure_no_overlap(
        self,
        identity: tuple[str, str, str, str],
        *,
        start: datetime,
        end: datetime | None,
        exclude_ids: set[str] | None = None,
    ) -> None:
        provider, service, sku, unit = identity
        filters = [
            PricingCatalogItem.provider == provider,
            PricingCatalogItem.service == service,
            PricingCatalogItem.sku == sku,
            PricingCatalogItem.unit == unit,
            PricingCatalogItem.enabled.is_(True),
            or_(
                PricingCatalogItem.effective_until.is_(None),
                PricingCatalogItem.effective_until > start,
            ),
        ]
        if end is not None:
            filters.append(PricingCatalogItem.effective_from < end)
        if exclude_ids:
            filters.append(PricingCatalogItem.id.not_in(exclude_ids))
        conflict = self.db.scalar(select(PricingCatalogItem.id).where(*filters).limit(1))
        if conflict is not None:
            raise PricingAdminConflictError(
                "another enabled price already covers part of this effective interval"
            )

    @staticmethod
    def _validate_values(
        *,
        service: str,
        sku: str,
        description: str,
        unit: str,
        price: Decimal,
        currency: str,
        source: str,
        effective_from: datetime,
        effective_until: datetime | None,
    ) -> None:
        if not service or not sku or not description or not unit:
            raise PricingAdminValidationError(
                "service, sku, description and unit are required"
            )
        if price < 0:
            raise PricingAdminValidationError("price must be greater than or equal to zero")
        if len(currency) != 3 or currency != currency.upper():
            raise PricingAdminValidationError("currency must be an uppercase ISO code")
        if not source:
            raise PricingAdminValidationError("source is required")
        if effective_until is not None and effective_until <= effective_from:
            raise PricingAdminValidationError(
                "effective_until must be after effective_from"
            )
