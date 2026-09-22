from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AwsAccount(TimestampMixin, Base):
    __tablename__ = "aws_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    aws_account_id: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    role_arn: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    regions: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["sa-east-1"])
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_management_account: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(24), default="untested")
    last_connection_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
