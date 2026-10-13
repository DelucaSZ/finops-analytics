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


class PricingCatalogItem(TimestampMixin, Base):
    """Provider-neutral, effective-dated unit price used by cloud cost estimators."""

    __tablename__ = "pricing_catalog_items"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_pricing_catalog_items_price_non_negative"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_pricing_catalog_items_currency_iso_code",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_pricing_catalog_items_effective_interval",
        ),
        UniqueConstraint(
            "provider",
            "service",
            "sku",
            "unit",
            "effective_from",
            name="uq_pricing_catalog_items_identity_effective_from",
        ),
        Index(
            "ix_pricing_catalog_items_lookup",
            "provider",
            "service",
            "sku",
            "unit",
            "enabled",
            "effective_from",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
