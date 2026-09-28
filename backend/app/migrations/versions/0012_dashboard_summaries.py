"""Persist current dashboard aggregates per provider/account."""

import sqlalchemy as sa
from alembic import op

revision = "0012_dashboard_summaries"
down_revision = "0011_multicloud_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_account_summaries",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("collection_run_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_collection_run_id", sa.String(length=36), nullable=True),
        sa.Column("open_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("treated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "severity_counts",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "financial",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("new_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "no_longer_detected_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "has_baseline",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "rules_version_changed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "rules_version_unknown",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_collection_run_id"],
            ["collection_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("provider", "account_id"),
    )
    op.create_index(
        "ux_dashboard_account_summaries_collection_run_id",
        "dashboard_account_summaries",
        ["collection_run_id"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "ux_dashboard_account_summaries_collection_run_id",
        table_name="dashboard_account_summaries",
    )
    op.drop_table("dashboard_account_summaries")
