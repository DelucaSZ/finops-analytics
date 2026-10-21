"""immutable opportunity history cycles and snapshots

Revision ID: 0032_opportunity_history_cycles
Revises: 0031_audit_events
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_opportunity_history_cycles"
down_revision = "0031_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_history_cycles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("close_reason", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_start < period_end",
            name="ck_opportunity_history_cycles_period",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'CLOSED')",
            name="ck_opportunity_history_cycles_status",
        ),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period_start",
            "period_end",
            name="uq_opportunity_history_cycles_period",
        ),
    )
    op.create_index(
        "ix_opportunity_history_cycles_period",
        "opportunity_history_cycles",
        ["period_start", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_cycles_status_period",
        "opportunity_history_cycles",
        ["status", "period_start"],
        unique=False,
    )

    op.create_table(
        "opportunity_history_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("service", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=True),
        sa.Column("rule_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("presence_status", sa.String(length=32), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("archive_reason", sa.String(length=32), nullable=True),
        sa.Column("treated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_externally_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("treatment_note", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=32), nullable=True),
        sa.Column("rejection_note", sa.Text(), nullable=True),
        sa.Column("current_monthly_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("estimated_monthly_savings", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "first_observed_in_cycle_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_observed_in_cycle_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("occurrence_count_in_cycle", sa.Integer(), nullable=False),
        sa.Column("total_occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_collection_run_id_in_cycle", sa.String(length=36), nullable=True),
        sa.Column("last_collection_run_id_in_cycle", sa.String(length=36), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_reason", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["opportunity_history_cycles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["findings.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id",
            "opportunity_id",
            name="uq_opportunity_history_cycle_opportunity",
        ),
    )
    op.create_index(
        "ix_opportunity_history_snapshots_cycle_id",
        "opportunity_history_snapshots",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_opportunity_id",
        "opportunity_history_snapshots",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_cycle_status",
        "opportunity_history_snapshots",
        ["cycle_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_cycle_provider_account",
        "opportunity_history_snapshots",
        ["cycle_id", "provider", "account_id"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_cycle_severity",
        "opportunity_history_snapshots",
        ["cycle_id", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_cycle_last_observed",
        "opportunity_history_snapshots",
        ["cycle_id", "last_observed_in_cycle_at"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_rule",
        "opportunity_history_snapshots",
        ["rule_key"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_history_snapshots_resource",
        "opportunity_history_snapshots",
        ["resource_id"],
        unique=False,
    )


def downgrade() -> None:
    for index_name in (
        "ix_opportunity_history_snapshots_resource",
        "ix_opportunity_history_snapshots_rule",
        "ix_opportunity_history_snapshots_cycle_last_observed",
        "ix_opportunity_history_snapshots_cycle_severity",
        "ix_opportunity_history_snapshots_cycle_provider_account",
        "ix_opportunity_history_snapshots_cycle_status",
        "ix_opportunity_history_snapshots_opportunity_id",
        "ix_opportunity_history_snapshots_cycle_id",
    ):
        op.drop_index(index_name, table_name="opportunity_history_snapshots")
    op.drop_table("opportunity_history_snapshots")
    op.drop_index(
        "ix_opportunity_history_cycles_status_period",
        table_name="opportunity_history_cycles",
    )
    op.drop_index(
        "ix_opportunity_history_cycles_period",
        table_name="opportunity_history_cycles",
    )
    op.drop_table("opportunity_history_cycles")
