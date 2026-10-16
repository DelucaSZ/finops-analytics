"""CloudWatch cost engine pricing rules.

Revision ID: 0029_cloudwatch_cost_engine
Revises: 0028_cloudwatch_usage_telemetry
"""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0029_cloudwatch_cost_engine"
down_revision = "0028_cloudwatch_usage_telemetry"
branch_labels = None
depends_on = None


_PRICING_SOURCE = "AWS_OFFICIAL_PRICING"
_PRICING_REFERENCE = (
    "https://aws.amazon.com/cloudwatch/pricing/ | "
    "https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html"
)


def upgrade() -> None:
    op.create_table(
        "cloudwatch_pricing_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("pricing_dimension", sa.String(length=48), nullable=False),
        sa.Column("region_scope", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("unit_quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tier_from", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("tier_to", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("tier_scope", sa.String(length=80), nullable=False),
        sa.Column("applicability", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("pricing_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "currency = upper(currency) AND length(currency) = 3",
            name="ck_cloudwatch_pricing_currency_iso_code",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_cloudwatch_pricing_effective_interval",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_cloudwatch_pricing_price_non_negative",
        ),
        sa.CheckConstraint(
            "tier_from >= 0",
            name="ck_cloudwatch_pricing_tier_from_non_negative",
        ),
        sa.CheckConstraint(
            "tier_to IS NULL OR tier_to > tier_from",
            name="ck_cloudwatch_pricing_tier_interval",
        ),
        sa.CheckConstraint(
            "unit_quantity > 0",
            name="ck_cloudwatch_pricing_unit_quantity_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation",
            "pricing_dimension",
            "region_scope",
            "effective_from",
            "tier_from",
            name="uq_cloudwatch_pricing_identity_effective_tier",
        ),
    )
    op.create_index(
        "ix_cloudwatch_pricing_lookup",
        "cloudwatch_pricing_rules",
        [
            "operation",
            "pricing_dimension",
            "region_scope",
            "enabled",
            "effective_from",
        ],
        unique=False,
    )

    pricing_rules = sa.table(
        "cloudwatch_pricing_rules",
        sa.column("id", sa.String),
        sa.column("operation", sa.String),
        sa.column("pricing_dimension", sa.String),
        sa.column("region_scope", sa.String),
        sa.column("unit", sa.String),
        sa.column("unit_quantity", sa.Numeric),
        sa.column("price", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_until", sa.DateTime(timezone=True)),
        sa.column("tier_from", sa.Numeric),
        sa.column("tier_to", sa.Numeric),
        sa.column("tier_scope", sa.String),
        sa.column("applicability", sa.String),
        sa.column("source", sa.String),
        sa.column("source_reference", sa.String),
        sa.column("pricing_verified_at", sa.DateTime(timezone=True)),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    effective_from = datetime(2026, 10, 16, tzinfo=UTC)
    verified_at = datetime(2026, 10, 16, tzinfo=UTC)
    op.bulk_insert(
        pricing_rules,
        [
            {
                "id": "cw-gms-api-20261016",
                "operation": "GetMetricStatistics",
                "pricing_dimension": "API_REQUEST",
                "region_scope": "AWS_COMMERCIAL",
                "unit": "REQUEST",
                "unit_quantity": Decimal("1000"),
                "price": Decimal("0.01"),
                "currency": "USD",
                "effective_from": effective_from,
                "effective_until": None,
                "tier_from": Decimal("0"),
                "tier_to": None,
                "tier_scope": "NONE",
                "applicability": (
                    "Gross public API request rate; shared AWS Free Tier is not applied"
                ),
                "source": _PRICING_SOURCE,
                "source_reference": _PRICING_REFERENCE,
                "pricing_verified_at": verified_at,
                "enabled": True,
                "created_at": verified_at,
                "updated_at": verified_at,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_cloudwatch_pricing_lookup", table_name="cloudwatch_pricing_rules")
    op.drop_table("cloudwatch_pricing_rules")
