"""CloudWatch usage telemetry

Revision ID: 0028_cloudwatch_usage_telemetry
Revises: 0027_billing_profiles
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_cloudwatch_usage_telemetry"
down_revision = "0027_billing_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloudwatch_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("aws_service", sa.String(length=32), nullable=False),
        sa.Column("cloud_account_id", sa.Integer(), nullable=True),
        sa.Column("aws_account_id", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("collector", sa.String(length=80), nullable=True),
        sa.Column("analyzer", sa.String(length=80), nullable=True),
        sa.Column("collection_run_id", sa.String(length=36), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("request_count_is_exact", sa.Boolean(), nullable=False),
        sa.Column("metrics_requested", sa.Integer(), nullable=True),
        sa.Column("metric_query_count", sa.Integer(), nullable=True),
        sa.Column("metric_stat_query_count", sa.Integer(), nullable=True),
        sa.Column("expression_query_count", sa.Integer(), nullable=True),
        sa.Column("metrics_insights_query_count", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("request_duration_ms", sa.Integer(), nullable=True),
        sa.Column("aws_request_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cloud_account_id"], ["cloud_accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"], ["collection_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cloudwatch_usage_events_occurred_at",
        "cloudwatch_usage_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_events_collection_run_id",
        "cloudwatch_usage_events",
        ["collection_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_account_occurred",
        "cloudwatch_usage_events",
        ["cloud_account_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_operation_occurred",
        "cloudwatch_usage_events",
        ["operation", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_collector_occurred",
        "cloudwatch_usage_events",
        ["collector", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_analyzer_occurred",
        "cloudwatch_usage_events",
        ["analyzer", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_cloudwatch_usage_region_occurred",
        "cloudwatch_usage_events",
        ["region", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("cloudwatch_usage_events")
