"""Add opportunity archive state and auditable archive history."""

import sqlalchemy as sa
from alembic import op

revision = "0022_opportunity_archiving"
down_revision = "0021_opportunity_presence_audit"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("archived_by", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("archive_reason", sa.String(length=32), nullable=True))
        batch.create_foreign_key(
            "fk_findings_archived_by_users",
            "users",
            ["archived_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_findings_archive_reason",
            "archive_reason IS NULL OR archive_reason IN ('MANUAL', 'RETENTION_POLICY')",
        )
        batch.create_index("ix_findings_archived_at", ["archived_at"])
        batch.create_index(
            "ix_findings_status_archived_last_seen",
            ["status", "archived_at", "last_seen_at"],
        )

    op.create_table(
        "opportunity_archive_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("collection_run_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('ARCHIVE', 'UNARCHIVE')",
            name="ck_opportunity_archive_history_action",
        ),
        sa.CheckConstraint(
            "reason IN ('MANUAL', 'RETENTION_POLICY', 'REAPPEARED')",
            name="ck_opportunity_archive_history_reason",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["findings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_archive_history_opportunity_id",
        "opportunity_archive_history",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_opportunity_archive_history_changed_by",
        "opportunity_archive_history",
        ["changed_by"],
    )
    op.create_index(
        "ix_opportunity_archive_history_collection_run_id",
        "opportunity_archive_history",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_opportunity_archive_history_occurred_at",
        "opportunity_archive_history",
        ["occurred_at"],
    )
    op.create_index(
        "ix_opportunity_archive_history_opportunity_occurred",
        "opportunity_archive_history",
        ["opportunity_id", "occurred_at"],
    )


def downgrade():
    raise RuntimeError("Opportunity archive history must be preserved; do not downgrade")
