from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class AuditEvent(Base):
    """Append-only administrative audit event."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_actor_created_at", "actor_id", "created_at"),
        Index("ix_audit_events_module_created_at", "module", "created_at"),
        Index("ix_audit_events_action", "action"),
        Index(
            "ix_audit_events_entity_created_at",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index("ix_audit_events_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_email_snapshot: Mapped[str | None] = mapped_column(String(254), nullable=True)

    action: Mapped[str] = mapped_column(String(120), nullable=False)
    module: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    before_data: Mapped[dict[str, Any] | None] = mapped_column("before", JSON, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column("after", JSON, nullable=True)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
