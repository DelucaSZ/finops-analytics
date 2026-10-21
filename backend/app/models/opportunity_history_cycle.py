import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityHistoryCycleStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OpportunityHistoryCycle(TimestampMixin, Base):
    __tablename__ = "opportunity_history_cycles"
    __table_args__ = (
        CheckConstraint(
            "period_start < period_end",
            name="ck_opportunity_history_cycles_period",
        ),
        UniqueConstraint(
            "period_start",
            "period_end",
            name="uq_opportunity_history_cycles_period",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'CLOSED')",
            name="ck_opportunity_history_cycles_status",
        ),
        Index("ix_opportunity_history_cycles_period", "period_start", "period_end"),
        Index("ix_opportunity_history_cycles_status_period", "status", "period_start"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default=OpportunityHistoryCycleStatus.OPEN.value,
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="UTC",
        server_default="UTC",
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )


@event.listens_for(Session, "before_flush")
def _protect_closed_opportunity_history_cycles(
    session: Session,
    _flush_context,
    _instances,
) -> None:
    for item in tuple(session.dirty):
        if not isinstance(item, OpportunityHistoryCycle):
            continue
        state = inspect(item)
        if not state.persistent or not session.is_modified(item, include_collections=False):
            continue

        status_history = state.attrs.status.history
        closing_now = (
            item.status == OpportunityHistoryCycleStatus.CLOSED.value
            and status_history.has_changes()
            and status_history.added
            and status_history.added[-1] == OpportunityHistoryCycleStatus.CLOSED.value
            and (
                not status_history.deleted
                or status_history.deleted[-1] == OpportunityHistoryCycleStatus.OPEN.value
            )
        )
        if item.status == OpportunityHistoryCycleStatus.CLOSED.value and not closing_now:
            raise ValueError("Closed opportunity history cycles are immutable")

    for item in tuple(session.deleted):
        if (
            isinstance(item, OpportunityHistoryCycle)
            and item.status == OpportunityHistoryCycleStatus.CLOSED.value
        ):
            raise ValueError("Closed opportunity history cycles cannot be deleted")
