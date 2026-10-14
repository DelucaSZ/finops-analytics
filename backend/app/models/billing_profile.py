import uuid

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, String, Text, false, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BillingProfile(TimestampMixin, Base):
    """Reusable DeepOps configuration for AWS Billing queries."""

    __tablename__ = "billing_profiles"
    __table_args__ = (
        CheckConstraint(
            "granularity IN ('DAILY', 'MONTHLY')",
            name="ck_billing_profiles_granularity",
        ),
        CheckConstraint(
            "metric IN ('AMORTIZED_COST', 'NET_AMORTIZED_COST', 'UNBLENDED_COST')",
            name="ck_billing_profiles_metric",
        ),
        CheckConstraint(
            "group_by IN ('NONE', 'SERVICE', 'ACCOUNT')",
            name="ck_billing_profiles_group_by",
        ),
        Index("uq_billing_profiles_name", "name", unique=True),
        Index(
            "uq_billing_profiles_one_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    granularity: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    group_by: Mapped[str] = mapped_column(String(16), nullable=False)
    exclude_record_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
