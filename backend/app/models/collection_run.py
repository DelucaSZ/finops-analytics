import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CollectionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class CollectionRun(TimestampMixin, Base):
    __tablename__ = "collection_runs"
    __table_args__ = (
        Index("ix_collection_runs_account_started", "account_id", "started_at"),
        Index("ix_collection_runs_status_started", "status", "started_at"),
        Index(
            "ix_collection_runs_provider_account_started",
            "provider",
            "account_id",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("scans.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resources_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opportunities_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detailed_observations_available: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    analyzer_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
