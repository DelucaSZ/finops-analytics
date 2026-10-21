import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class OpportunityHistorySnapshot(Base):
    __tablename__ = "opportunity_history_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id",
            "opportunity_id",
            name="uq_opportunity_history_cycle_opportunity",
        ),
        Index("ix_opportunity_history_snapshots_cycle_status", "cycle_id", "status"),
        Index(
            "ix_opportunity_history_snapshots_cycle_provider_account",
            "cycle_id",
            "provider",
            "account_id",
        ),
        Index(
            "ix_opportunity_history_snapshots_cycle_severity",
            "cycle_id",
            "severity",
        ),
        Index(
            "ix_opportunity_history_snapshots_cycle_last_observed",
            "cycle_id",
            "last_observed_in_cycle_at",
        ),
        Index("ix_opportunity_history_snapshots_rule", "rule_key"),
        Index("ix_opportunity_history_snapshots_resource", "resource_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    cycle_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_history_cycles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    service: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    presence_status: Mapped[str] = mapped_column(String(32), nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
    archive_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    treated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_externally_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    treatment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    current_monthly_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_observed_in_cycle_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_observed_in_cycle_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    occurrence_count_in_cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    total_occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_collection_run_id_in_cycle: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    last_collection_run_id_in_cycle: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


@event.listens_for(Session, "before_flush")
def _protect_opportunity_history_snapshots(
    session: Session,
    _flush_context,
    _instances,
) -> None:
    for item in tuple(session.dirty):
        if (
            isinstance(item, OpportunityHistorySnapshot)
            and inspect(item).persistent
            and session.is_modified(item, include_collections=False)
        ):
            raise ValueError("Opportunity history snapshots are append-only")
    for item in tuple(session.deleted):
        if isinstance(item, OpportunityHistorySnapshot):
            raise ValueError("Opportunity history snapshots cannot be deleted")
