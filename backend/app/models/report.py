"""Persistent Reports domain models.

Reports describe reusable report definitions. Executions preserve immutable input
snapshots, while artifacts only reference objects stored outside the database.
"""

from __future__ import annotations

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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class ReportType(StrEnum):
    COST = "COST"
    EXECUTIVE = "EXECUTIVE"
    INVENTORY = "INVENTORY"
    RESERVATIONS = "RESERVATIONS"
    OPTIMIZATION = "OPTIMIZATION"


class ReportExecutionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ReportArtifactFormat(StrEnum):
    PDF = "PDF"
    CSV = "CSV"
    XLSX = "XLSX"
    JSON = "JSON"


class Report(TimestampMixin, Base):
    """Persisted business definition of a report, independent from executions."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_created_by_created_at", "created_by", "created_at"),
        Index("ix_reports_type_created_at", "report_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ReportExecution(TimestampMixin, Base):
    """One asynchronous attempt to materialize a Report."""

    __tablename__ = "report_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED')",
            name="ck_report_executions_status",
        ),
        CheckConstraint("attempt >= 1", name="ck_report_executions_attempt"),
        Index("ix_report_executions_report_created", "report_id", "created_at"),
        Index("ix_report_executions_status_created", "status", "created_at"),
        Index("ix_report_executions_requested_by_created", "requested_by", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReportExecutionStatus.QUEUED.value, index=True
    )
    parameters_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scope_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requested_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    execution_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReportArtifact(Base):
    """Storage-agnostic reference to an artifact produced by one execution."""

    __tablename__ = "report_artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_report_artifacts_size"),
        Index("ix_report_artifacts_execution_created", "report_execution_id", "created_at"),
        Index("ix_report_artifacts_format_created", "format", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_execution_id: Mapped[str] = mapped_column(
        ForeignKey("report_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
