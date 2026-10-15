import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class CloudWatchUsageEvent(Base):
    __tablename__ = "cloudwatch_usage_events"
    __table_args__ = (
        Index("ix_cloudwatch_usage_account_occurred", "cloud_account_id", "occurred_at"),
        Index("ix_cloudwatch_usage_operation_occurred", "operation", "occurred_at"),
        Index("ix_cloudwatch_usage_collector_occurred", "collector", "occurred_at"),
        Index("ix_cloudwatch_usage_analyzer_occurred", "analyzer", "occurred_at"),
        Index("ix_cloudwatch_usage_region_occurred", "region", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), default="aws", nullable=False)
    aws_service: Mapped[str] = mapped_column(String(32), default="cloudwatch", nullable=False)
    cloud_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="SET NULL"), nullable=True
    )
    aws_account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    collector: Mapped[str | None] = mapped_column(String(80), nullable=True)
    analyzer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_count_is_exact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metrics_requested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_query_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_stat_query_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expression_query_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_insights_query_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aws_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
