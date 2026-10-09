import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityPresenceStatus(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"
    RESOLVED_EXTERNALLY = "resolved_externally"


class Finding(TimestampMixin, Base):
    """Provider-neutral logical optimization opportunity."""

    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "presence_status IN ('active', 'missing', 'resolved_externally')",
            name="ck_findings_presence_status",
        ),
        CheckConstraint(
            "archive_reason IS NULL OR archive_reason IN ('MANUAL', 'RETENTION_POLICY')",
            name="ck_findings_archive_reason",
        ),
        Index(
            "ix_findings_provider_account_status_last_seen",
            "provider",
            "account_id",
            "status",
            "last_seen_at",
        ),
        Index(
            "ix_findings_presence_reconciliation_scope",
            "provider",
            "account_id",
            "rule_key",
            "region",
            "presence_status",
        ),
        Index("ix_findings_status_severity", "status", "severity"),
        Index(
            "ix_findings_status_archived_last_seen",
            "status",
            "archived_at",
            "last_seen_at",
        ),
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
    presence_status: Mapped[str] = mapped_column(
        String(32),
        default=OpportunityPresenceStatus.ACTIVE.value,
        server_default=OpportunityPresenceStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    missing_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    missing_since_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_externally_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    presence_reconciled_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    presence_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_occurrence_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
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
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archive_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
