import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True, nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("aws_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    service: Mapped[str] = mapped_column(String(40), nullable=False)
    region: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    current_monthly_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
