import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityArchiveAction(StrEnum):
    ARCHIVE = "ARCHIVE"
    UNARCHIVE = "UNARCHIVE"


class OpportunityArchiveReason(StrEnum):
    MANUAL = "MANUAL"
    RETENTION_POLICY = "RETENTION_POLICY"
    REAPPEARED = "REAPPEARED"


class OpportunityArchiveHistory(TimestampMixin, Base):
    """Immutable audit trail for opportunity archive state transitions."""

    __tablename__ = "opportunity_archive_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('ARCHIVE', 'UNARCHIVE')",
            name="ck_opportunity_archive_history_action",
        ),
        CheckConstraint(
            "reason IN ('MANUAL', 'RETENTION_POLICY', 'REAPPEARED')",
            name="ck_opportunity_archive_history_reason",
        ),
        Index(
            "ix_opportunity_archive_history_opportunity_occurred",
            "opportunity_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
