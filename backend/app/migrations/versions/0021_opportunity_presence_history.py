"""Add auditable opportunity technical presence history."""

import sqlalchemy as sa
from alembic import op

revision = "0021_opportunity_presence_audit"
down_revision = "0020_opportunity_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "opportunity_presence_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("collection_run_id", sa.String(length=36), nullable=True),
        sa.Column("collection_scope_execution_id", sa.String(length=36), nullable=True),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("missing_threshold", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_status IN ('active', 'missing', 'resolved_externally')",
            name="ck_opportunity_presence_history_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('active', 'missing', 'resolved_externally')",
            name="ck_opportunity_presence_history_to_status",
        ),
        sa.CheckConstraint(
            "reason IN ('NOT_OBSERVED_IN_SUCCESSFUL_SCOPE', "
            "'MISSING_THRESHOLD_REACHED', 'OBSERVED_AGAIN')",
            name="ck_opportunity_presence_history_reason",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["findings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["collection_scope_execution_id"],
            ["collection_scope_executions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id",
            "collection_run_id",
            "reason",
            name="uq_opportunity_presence_history_run_reason",
        ),
    )
    op.create_index(
        "ix_opportunity_presence_history_collection_run_id",
        "opportunity_presence_history",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_opportunity_presence_history_collection_scope_execution_id",
        "opportunity_presence_history",
        ["collection_scope_execution_id"],
    )
    op.create_index(
        "ix_opportunity_presence_history_occurred_at",
        "opportunity_presence_history",
        ["occurred_at"],
    )
    op.create_index(
        "ix_opportunity_presence_history_opportunity_occurred",
        "opportunity_presence_history",
        ["opportunity_id", "occurred_at"],
    )
    op.create_index(
        "ix_opportunity_presence_history_to_status_occurred",
        "opportunity_presence_history",
        ["to_status", "occurred_at"],
    )


def downgrade():
    raise RuntimeError("Opportunity presence audit history must be preserved; do not downgrade")
