"""Create provider-neutral pricing catalog and seed the approved OCI BRL rates."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0024_pricing_catalog"
down_revision = "0023_opportunity_retention"
branch_labels = None
depends_on = None

_SOURCE = "IMPORTED_OCI_CALCULATOR"
_EFFECTIVE_FROM = datetime(2026, 10, 1, tzinfo=UTC)
_IMPORTED_AT = datetime(2026, 10, 13, tzinfo=UTC)

_OCI_PRICES = (
    (
        "compute",
        "VM.Standard.E3.Flex.OCPU",
        "E3 Flex OCPU",
        "OCPU_HOUR",
        "0.0521",
    ),
    (
        "compute",
        "VM.Standard.E3.Flex.Memory",
        "E3 Flex memory",
        "GB_RAM_HOUR",
        "0.0031",
    ),
    (
        "compute",
        "VM.Standard.E4.Flex.OCPU",
        "E4 Flex OCPU",
        "OCPU_HOUR",
        "0.0689",
    ),
    (
        "compute",
        "VM.Standard.E4.Flex.Memory",
        "E4 Flex memory",
        "GB_RAM_HOUR",
        "0.0041",
    ),
    (
        "compute",
        "VM.Standard.E5.Flex.OCPU",
        "E5 Flex OCPU",
        "OCPU_HOUR",
        "0.08266",
    ),
    (
        "compute",
        "VM.Standard.E5.Flex.Memory",
        "E5 Flex memory",
        "GB_RAM_HOUR",
        "0.005511",
    ),
    (
        "compute",
        "WINDOWS_LICENSE_OCPU",
        "Windows license per OCPU",
        "OCPU_HOUR",
        "0.46092",
    ),
    (
        "block_volume",
        "BLOCK_VOLUME_GB_MONTH",
        "Block Volume capacity",
        "GB_MONTH",
        "0.0531",
    ),
    (
        "block_volume",
        "BLOCK_VOLUME_VPU_GB_MONTH",
        "Block Volume performance",
        "VPU_GB_MONTH",
        "0.0036",
    ),
)


def _seed_id(service: str, sku: str, unit: str) -> str:
    identity = f"deepops:pricing:oci:{service}:{sku}:{unit}:2026-10"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def upgrade() -> None:
    op.create_table(
        "pricing_catalog_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_pricing_catalog_items_price_non_negative",
        ),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_pricing_catalog_items_currency_iso_code",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_pricing_catalog_items_effective_interval",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "service",
            "sku",
            "unit",
            "effective_from",
            name="uq_pricing_catalog_items_identity_effective_from",
        ),
    )
    op.create_index(
        "ix_pricing_catalog_items_lookup",
        "pricing_catalog_items",
        ["provider", "service", "sku", "unit", "enabled", "effective_from"],
        unique=False,
    )

    pricing = sa.table(
        "pricing_catalog_items",
        sa.column("id", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("service", sa.String()),
        sa.column("sku", sa.String()),
        sa.column("description", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("price", sa.Numeric(20, 8)),
        sa.column("currency", sa.String()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_until", sa.DateTime(timezone=True)),
        sa.column("enabled", sa.Boolean()),
        sa.column("source", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        pricing,
        [
            {
                "id": _seed_id(service, sku, unit),
                "provider": "oci",
                "service": service,
                "sku": sku,
                "description": description,
                "unit": unit,
                "price": Decimal(price),
                "currency": "BRL",
                "effective_from": _EFFECTIVE_FROM,
                "effective_until": None,
                "enabled": True,
                "source": _SOURCE,
                "created_at": _IMPORTED_AT,
                "updated_at": _IMPORTED_AT,
            }
            for service, sku, description, unit, price in _OCI_PRICES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_pricing_catalog_items_lookup", table_name="pricing_catalog_items")
    op.drop_table("pricing_catalog_items")
