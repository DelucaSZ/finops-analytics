import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CloudWatchPricingRule(TimestampMixin, Base):
    """Effective-dated public pricing rule for Aven CloudWatch usage estimates."""

    __tablename__ = "cloudwatch_pricing_rules"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_cloudwatch_pricing_price_non_negative"),
        CheckConstraint(
            "unit_quantity > 0",
            name="ck_cloudwatch_pricing_unit_quantity_positive",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_cloudwatch_pricing_effective_interval",
        ),
        CheckConstraint("tier_from >= 0", name="ck_cloudwatch_pricing_tier_from_non_negative"),
        CheckConstraint(
            "tier_to IS NULL OR tier_to > tier_from",
            name="ck_cloudwatch_pricing_tier_interval",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_cloudwatch_pricing_currency_iso_code",
        ),
        UniqueConstraint(
            "operation",
            "pricing_dimension",
            "region_scope",
            "effective_from",
            "tier_from",
            name="uq_cloudwatch_pricing_identity_effective_tier",
        ),
        Index(
            "ix_cloudwatch_pricing_lookup",
            "operation",
            "pricing_dimension",
            "region_scope",
            "enabled",
            "effective_from",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_dimension: Mapped[str] = mapped_column(String(48), nullable=False)
    region_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tier_from: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False, default=Decimal("0"))
    tier_to: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    tier_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="NONE")
    applicability: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    pricing_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )
