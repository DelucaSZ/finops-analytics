"""Durable AWS pricing synchronization run history.

Revision ID: 0041_aws_pricing_sync_runs
Revises: 0040_aws_regional_pricing
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0041_aws_pricing_sync_runs"
down_revision = "0040_aws_regional_pricing"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "aws_pricing_sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_code", sa.String(80), nullable=False),
        sa.Column("region_code", sa.String(40), nullable=False),
        sa.Column("trigger", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("source_reference", sa.String(500)),
        sa.Column("source_version", sa.String(160)),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("aws_pricing_import_batches.id", ondelete="RESTRICT"),
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("products_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rates_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rates_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rates_published", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", _JSON),
        sa.Column("coverage", _JSON),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_summary", sa.String(500)),
        sa.CheckConstraint(
            "status IN ('running','unchanged','published','partial','failed',"
            "'interrupted','validated')",
            name="ck_aws_pricing_sync_run_status",
        ),
    )
    op.create_index(
        "ix_aws_pricing_sync_run_unit",
        "aws_pricing_sync_runs",
        ["service_code", "region_code", "started_at"],
    )
    op.create_index(
        "ix_aws_pricing_sync_run_status",
        "aws_pricing_sync_runs",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    # Operational history is discarded only during an explicit schema downgrade.
    op.drop_index("ix_aws_pricing_sync_run_status", table_name="aws_pricing_sync_runs")
    op.drop_index("ix_aws_pricing_sync_run_unit", table_name="aws_pricing_sync_runs")
    op.drop_table("aws_pricing_sync_runs")
