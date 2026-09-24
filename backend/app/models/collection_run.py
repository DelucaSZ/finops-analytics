import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CollectionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class CollectionRun(TimestampMixin, Base):
    __tablename__ = "collection_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str | None] = mapped_column(
        String(36), unique=True, index=True, nullable=True
    )
    provider: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    resources_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opportunities_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analyzer_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
