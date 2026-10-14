from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class PricingAuditAction:
    CREATED = "CREATED"
    PRICE_CHANGED = "PRICE_CHANGED"
    METADATA_CHANGED = "METADATA_CHANGED"
    DEACTIVATED = "DEACTIVATED"
    REACTIVATED = "REACTIVATED"
    FUTURE_VERSION_CREATED = "FUTURE_VERSION_CREATED"
    VALIDITY_CHANGED = "VALIDITY_CHANGED"
    IMPORTED = "IMPORTED"

    VALUES = (
        CREATED,
        PRICE_CHANGED,
        METADATA_CHANGED,
        DEACTIVATED,
        REACTIVATED,
        FUTURE_VERSION_CREATED,
        VALIDITY_CHANGED,
        IMPORTED,
    )


class PricingAuditActorType:
    USER = "USER"
    SYSTEM = "SYSTEM"

    VALUES = (USER, SYSTEM)


class PricingAuditEvent(Base):
    """Append-only administrative audit event for one logical pricing key."""

    __tablename__ = "pricing_audit_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATED', 'PRICE_CHANGED', 'METADATA_CHANGED', 'DEACTIVATED', "
            "'REACTIVATED', 'FUTURE_VERSION_CREATED', 'VALIDITY_CHANGED', 'IMPORTED')",
            name="ck_pricing_audit_action",
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM')",
            name="ck_pricing_audit_actor_type",
        ),
        Index(
            "ix_pricing_audit_key_occurred",
            "provider",
            "service",
            "sku",
            "unit",
            "occurred_at",
        ),
        Index("ix_pricing_audit_item_occurred", "pricing_item_id", "occurred_at"),
        Index("ix_pricing_audit_actor", "actor_id"),
        Index("ix_pricing_audit_action", "action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pricing_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pricing_catalog_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
