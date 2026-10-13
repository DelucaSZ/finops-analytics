from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import func, select

from app.models.pricing import PricingCatalogItem
from app.models.pricing_audit import (
    PricingAuditAction,
    PricingAuditActorType,
    PricingAuditEvent,
)
from app.models.user import User
from app.services.pricing_admin import (
    PricingAdminValidationError,
    PricingCatalogAdminService,
)

_MIN_REASON_LENGTH = 3
_MAX_REASON_LENGTH = 500


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def pricing_snapshot(item: PricingCatalogItem) -> dict[str, Any]:
    """Serialize only audit-safe catalog fields; Decimal is never converted to float."""

    return {
        "id": item.id,
        "provider": item.provider,
        "service": item.service,
        "sku": item.sku,
        "description": item.description,
        "unit": item.unit,
        "price": format(Decimal(item.price), "f"),
        "currency": item.currency,
        "effective_from": _iso(item.effective_from),
        "effective_until": _iso(item.effective_until),
        "enabled": item.enabled,
        "source": item.source,
    }


def normalize_reason(reason: str | None, *, required: bool) -> str | None:
    if reason is None:
        if required:
            raise PricingAdminValidationError(
                "A reason with at least 3 characters is required for this pricing change."
            )
        return None
    cleaned = reason.strip()
    if not cleaned:
        if required:
            raise PricingAdminValidationError(
                "A reason with at least 3 characters is required for this pricing change."
            )
        return None
    if len(cleaned) < _MIN_REASON_LENGTH:
        raise PricingAdminValidationError("Pricing change reason must have at least 3 characters.")
    if len(cleaned) > _MAX_REASON_LENGTH:
        raise PricingAdminValidationError("Pricing change reason must have at most 500 characters.")
    return cleaned


class AuditedPricingCatalogAdminService(PricingCatalogAdminService):
    """Pricing administration plus immutable audit rows in the caller's transaction."""

    def _record(
        self,
        *,
        item: PricingCatalogItem,
        action: str,
        actor: User | None,
        reason: str | None,
        before_data: dict[str, Any] | None,
        after_data: dict[str, Any] | None,
    ) -> PricingAuditEvent:
        actor_type = (
            PricingAuditActorType.USER if actor is not None else PricingAuditActorType.SYSTEM
        )
        event = PricingAuditEvent(
            pricing_item_id=item.id,
            provider=item.provider,
            service=item.service,
            sku=item.sku,
            unit=item.unit,
            action=action,
            actor_type=actor_type,
            actor_id=actor.id if actor is not None else None,
            actor_name=actor.name if actor is not None else None,
            actor_email=actor.email if actor is not None else None,
            reason=reason,
            before_data=before_data,
            after_data=after_data,
        )
        self.db.add(event)
        return event

    def create_item_audited(
        self,
        *,
        actor: User,
        reason: str | None = None,
        **kwargs: Any,
    ) -> PricingCatalogItem:
        cleaned_reason = normalize_reason(reason, required=False)
        item = super().create_item(**kwargs)
        self._record(
            item=item,
            action=PricingAuditAction.CREATED,
            actor=actor,
            reason=cleaned_reason,
            before_data=None,
            after_data=pricing_snapshot(item),
        )
        return item

    def update_item_audited(
        self,
        item_id: str,
        *,
        actor: User,
        reason: str | None,
        price: Decimal | None = None,
        description: str | None = None,
        effective_from: datetime | None = None,
        source: str = "MANUAL",
    ) -> PricingCatalogItem:
        # Lock before taking the snapshot so concurrent administrators cannot produce
        # an audit event whose before image is already stale.
        selected = self.get_item(item_id, lock=True)
        before = pricing_snapshot(selected)
        financial_change = price is not None or effective_from is not None
        cleaned_reason = normalize_reason(reason, required=financial_change)

        item = super().update_item(
            item_id,
            price=price,
            description=description,
            effective_from=effective_from,
            source=source,
        )
        after = pricing_snapshot(item)
        if before == after:
            return item

        if price is not None:
            reference = datetime.now(UTC)
            effective = item.effective_from
            if effective.tzinfo is None:
                effective = effective.replace(tzinfo=UTC)
            action = (
                PricingAuditAction.FUTURE_VERSION_CREATED
                if effective.astimezone(UTC) > reference
                else PricingAuditAction.PRICE_CHANGED
            )
        else:
            action = PricingAuditAction.METADATA_CHANGED

        self._record(
            item=item,
            action=action,
            actor=actor,
            reason=cleaned_reason,
            before_data=before,
            after_data=after,
        )
        return item

    def deactivate_audited(
        self,
        item_id: str,
        *,
        actor: User,
        reason: str,
    ) -> PricingCatalogItem:
        selected = self.get_item(item_id, lock=True)
        before = pricing_snapshot(selected)
        cleaned_reason = normalize_reason(reason, required=True)
        item = super().deactivate(item_id)
        after = pricing_snapshot(item)
        if before != after:
            self._record(
                item=item,
                action=PricingAuditAction.DEACTIVATED,
                actor=actor,
                reason=cleaned_reason,
                before_data=before,
                after_data=after,
            )
        return item

    def audit_history(
        self,
        item_id: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        item = self.get_item(item_id)
        key_filter = (
            PricingAuditEvent.provider == item.provider,
            PricingAuditEvent.service == item.service,
            PricingAuditEvent.sku == item.sku,
            PricingAuditEvent.unit == item.unit,
        )
        total = (
            self.db.scalar(
                select(func.count()).select_from(PricingAuditEvent).where(*key_filter)
            )
            or 0
        )
        events = list(
            self.db.scalars(
                select(PricingAuditEvent)
                .where(*key_filter)
                .order_by(PricingAuditEvent.occurred_at.desc(), PricingAuditEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return {
            "items": events,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        }
