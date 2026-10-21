"""persistent opportunity management policy and automation state

Revision ID: 0033_opportunity_policy
Revises: 0032_opportunity_history_cycles
"""

import sqlalchemy as sa
from alembic import op

revision = "0033_opportunity_policy"
down_revision = "0032_opportunity_history_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunity_history_cycles",
        sa.Column("policy_version", sa.Integer(), nullable=True),
    )

    op.create_table(
        "opportunity_management_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=32), server_default="GLOBAL", nullable=False),
        sa.Column(
            "cycle_mode",
            sa.String(length=24),
            server_default="CALENDAR_MONTH",
            nullable=False,
        ),
        sa.Column("cycle_length_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("cycle_timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("cycle_anchor_date", sa.Date(), nullable=True),
        sa.Column(
            "automatic_cycle_close_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "treated_archive_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("treated_archive_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column(
            "rejected_archive_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("rejected_archive_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column(
            "resolved_external_archive_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "resolved_external_archive_days", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column("open_archive_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("open_archive_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("observation_retention_days", sa.Integer(), server_default="400", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "cycle_mode IN ('CALENDAR_MONTH', 'FIXED_DAYS')",
            name="ck_opportunity_management_policies_cycle_mode",
        ),
        sa.CheckConstraint(
            "cycle_length_days >= 7 AND cycle_length_days <= 365",
            name="ck_opportunity_management_policies_cycle_length",
        ),
        sa.CheckConstraint(
            "treated_archive_days >= 1 AND treated_archive_days <= 3650",
            name="ck_opportunity_management_policies_treated_days",
        ),
        sa.CheckConstraint(
            "rejected_archive_days >= 1 AND rejected_archive_days <= 3650",
            name="ck_opportunity_management_policies_rejected_days",
        ),
        sa.CheckConstraint(
            "resolved_external_archive_days >= 1 AND resolved_external_archive_days <= 3650",
            name="ck_opportunity_management_policies_resolved_days",
        ),
        sa.CheckConstraint(
            "open_archive_days >= 1 AND open_archive_days <= 3650",
            name="ck_opportunity_management_policies_open_days",
        ),
        sa.CheckConstraint(
            "observation_retention_days >= 30 AND observation_retention_days <= 3650",
            name="ck_opportunity_management_policies_observation_days",
        ),
        sa.CheckConstraint("version >= 1", name="ck_opportunity_management_policies_version"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", name="uq_opportunity_management_policies_scope"),
    )

    op.create_table(
        "opportunity_maintenance_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_retention_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cycle_close_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observation_cleanup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_retention_result", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("last_cycle_close_result", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "last_observation_cleanup_result", sa.JSON(), server_default="{}", nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_opportunity_maintenance_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_maintenance_state_retention",
        "opportunity_maintenance_state",
        ["last_retention_run_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_maintenance_state_retention",
        table_name="opportunity_maintenance_state",
    )
    op.drop_table("opportunity_maintenance_state")
    op.drop_table("opportunity_management_policies")
    op.drop_column("opportunity_history_cycles", "policy_version")
