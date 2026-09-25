import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityStatusHistory(TimestampMixin, Base):
    __tablename__ = "opportunity_status_history"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
