import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityPresenceReason(StrEnum):
    NOT_OBSERVED_IN_SUCCESSFUL_SCOPE = "NOT_OBSERVED_IN_SUCCESSFUL_SCOPE"
    MISSING_THRESHOLD_REACHED = "MISSING_THRESHOLD_REACHED"
    OBSERVED_AGAIN = "OBSERVED_AGAIN"


class OpportunityPresenceHistory(TimestampMixin, Base):
    """Immutable audit event for the provider-neutral technical presence lifecycle."""

    __tablename__ = "opportunity_presence_history"
    __table_args__ = (
        CheckConstraint(
            "from_status IN ('active', 'missing', 'resolved_externally')",
            name="ck_opportunity_presence_history_from_status",
        ),
        CheckConstraint(
            "to_status IN ('active', 'missing', 'resolved_externally')",
            name="ck_opportunity_presence_history_to_status",
        ),
        CheckConstraint(
            "reason IN ('NOT_OBSERVED_IN_SUCCESSFUL_SCOPE', "
            "'MISSING_THRESHOLD_REACHED', 'OBSERVED_AGAIN')",
            name="ck_opportunity_presence_history_reason",
        ),
        UniqueConstraint(
            "opportunity_id",
            "collection_run_id",
            "reason",
            name="uq_opportunity_presence_history_run_reason",
        ),
        Index(
            "ix_opportunity_presence_history_opportunity_occurred",
            "opportunity_id",
            "occurred_at",
        ),
        Index(
            "ix_opportunity_presence_history_to_status_occurred",
            "to_status",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    collection_scope_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_scope_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
