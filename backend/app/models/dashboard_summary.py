from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class DashboardAccountSummary(Base):
    """Derived current-state aggregate for one provider/account scope."""

    __tablename__ = "dashboard_account_summaries"
    __table_args__ = (
        Index(
            "ux_dashboard_account_summaries_collection_run_id",
            "collection_run_id",
            unique=True,
        ),
    )

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    baseline_collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    treated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    severity_counts: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    financial: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)

    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_longer_detected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_baseline: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    rules_version_changed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    rules_version_unknown: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
