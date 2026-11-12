"""Verified DB System SKU bindings; monetary amounts remain in pricing_catalog_items."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OciDbCalculatorBinding(Base):
    """An approved regional product configuration to a real catalog SKU identity.

    Binding rows never contain rates. Catalog versions, validity and BRL currency
    are still resolved by PricingResolver at quotation time.
    """

    __tablename__ = "oci_db_calculator_bindings"
    __table_args__ = (
        CheckConstraint(
            "component IN ('capacity', 'license', 'storage')",
            name="ck_oci_db_binding_component",
        ),
        CheckConstraint(
            "cpu_unit = 'ECPU'",
            name="ck_oci_db_binding_ecpu",
        ),
        UniqueConstraint(
            "region",
            "deployment_model",
            "shape",
            "edition",
            "license_model",
            "cpu_unit",
            "component",
            name="uq_oci_db_calculator_binding",
        ),
        Index("ix_oci_db_calculator_bindings_region", "region", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    deployment_model: Mapped[str] = mapped_column(String(32), nullable=False)
    shape: Mapped[str] = mapped_column(String(80), nullable=False)
    edition: Mapped[str] = mapped_column(String(32), nullable=False)
    license_model: Mapped[str] = mapped_column(String(24), nullable=False)
    cpu_unit: Mapped[str] = mapped_column(String(8), nullable=False)
    component: Mapped[str] = mapped_column(String(24), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    # Only relevant to capacity; true means the selected rate includes license.
    includes_license: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
