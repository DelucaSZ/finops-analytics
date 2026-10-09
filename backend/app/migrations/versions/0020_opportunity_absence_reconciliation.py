"""Add safe opportunity absence reconciliation coverage and state."""

import sqlalchemy as sa
from alembic import op

revision = "0020_opportunity_absence_reconciliation"
down_revision = "0019_opportunity_presence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collection_scope_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_run_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("rule_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resources_examined", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'FAILED', 'SKIPPED')",
            name="ck_collection_scope_executions_status",
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_run_id",
            "region",
            "rule_key",
            name="uq_collection_scope_execution_run_region_rule",
        ),
    )
    op.create_index(
        "ix_collection_scope_executions_collection_run_id",
        "collection_scope_executions",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_collection_scope_executions_identity",
        "collection_scope_executions",
        ["provider", "account_id", "rule_key", "region", "status"],
    )

    with op.batch_alter_table("findings") as batch:
        batch.add_column(
            sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("presence_reconciled_run_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("presence_reconciled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_index(
            "ix_findings_presence_reconciliation_scope",
            ["provider", "account_id", "rule_key", "region", "presence_status"],
        )


def downgrade():
    raise RuntimeError("Opportunity absence reconciliation state must be preserved; do not downgrade")
