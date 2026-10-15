"""AWS Billing profiles and FinOps preset

Revision ID: 0027_billing_profiles
Revises: 0026_finops_ledger
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0027_billing_profiles"
down_revision = "0026_finops_ledger"
branch_labels = None
depends_on = None

FINOPS_PROFILE_ID = "00000000-0000-0000-0000-000000023015"


def upgrade() -> None:
    op.create_table(
        "billing_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("granularity", sa.String(length=16), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("group_by", sa.String(length=16), nullable=False),
        sa.Column("exclude_record_types", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "granularity IN ('DAILY', 'MONTHLY')",
            name="ck_billing_profiles_granularity",
        ),
        sa.CheckConstraint(
            "metric IN ('AMORTIZED_COST', 'NET_AMORTIZED_COST', 'UNBLENDED_COST')",
            name="ck_billing_profiles_metric",
        ),
        sa.CheckConstraint(
            "group_by IN ('NONE', 'SERVICE', 'ACCOUNT')",
            name="ck_billing_profiles_group_by",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_billing_profiles_name", "billing_profiles", ["name"], unique=True)
    op.create_index(
        "uq_billing_profiles_one_default",
        "billing_profiles",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        sqlite_where=sa.text("is_default = 1"),
    )
    op.create_index(
        "ix_billing_profiles_created_by",
        "billing_profiles",
        ["created_by"],
        unique=False,
    )

    now = datetime.now(UTC)
    profiles = sa.table(
        "billing_profiles",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("granularity", sa.String()),
        sa.column("metric", sa.String()),
        sa.column("group_by", sa.String()),
        sa.column("exclude_record_types", sa.JSON()),
        sa.column("is_default", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_by", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        profiles,
        [
            {
                "id": FINOPS_PROFILE_ID,
                "name": "FinOps",
                "description": "Visão diária amortizada usada pelo time FinOps.",
                "granularity": "DAILY",
                "metric": "AMORTIZED_COST",
                "group_by": "NONE",
                "exclude_record_types": ["Credit"],
                "is_default": True,
                "enabled": True,
                "is_system": True,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("billing_profiles")
