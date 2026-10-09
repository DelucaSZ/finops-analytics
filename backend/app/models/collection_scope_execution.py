import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CollectionScopeExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CollectionScopeExecution(TimestampMixin, Base):
    """Execution coverage for one provider-neutral analyzer scope inside a collection run."""

    __tablename__ = "collection_scope_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILED', 'SKIPPED')",
            name="ck_collection_scope_executions_status",
        ),
        UniqueConstraint(
            "collection_run_id",
            "region",
            "rule_key",
            name="uq_collection_scope_execution_run_region_rule",
        ),
        Index(
            "ix_collection_scope_executions_identity",
            "provider",
            "account_id",
            "rule_key",
            "region",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(120), nullable=False)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resources_examined: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
