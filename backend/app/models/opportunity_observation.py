import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityObservation(TimestampMixin, Base):
    __tablename__ = "opportunity_observations"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "collection_run_id",
            name="uq_opportunity_observation_run",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    current_monthly_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
