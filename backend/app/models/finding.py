import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Finding(TimestampMixin, Base):
    """Provider-neutral logical optimization opportunity."""

    __tablename__ = "findings"
    __table_args__ = (
        Index(
            "ix_findings_provider_account_status_last_seen",
            "provider",
            "account_id",
            "status",
            "last_seen_at",
        ),
        Index("ix_findings_status_severity", "status", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("scans.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    service: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    current_monthly_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD", nullable=False
    )
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    treated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    treated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    treatment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rejected_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
