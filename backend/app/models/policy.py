from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("scope", "account_id", "rule_key", name="uq_policy_scope_rule"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
