"""Use service grouping by default in the FinOps Billing profile.

Revision ID: 0030_billing_service_default
Revises: 0029_cloudwatch_cost_engine
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_billing_service_default"
down_revision = "0029_cloudwatch_cost_engine"
branch_labels = None
depends_on = None

FINOPS_PROFILE_ID = "00000000-0000-0000-0000-000000023015"


def _billing_profiles():
    return sa.table(
        "billing_profiles",
        sa.column("id", sa.String()),
        sa.column("group_by", sa.String()),
    )


def upgrade() -> None:
    profiles = _billing_profiles()
    op.execute(
        profiles.update()
        .where(profiles.c.id == FINOPS_PROFILE_ID)
        .where(profiles.c.group_by == "NONE")
        .values(group_by="SERVICE")
    )


def downgrade() -> None:
    profiles = _billing_profiles()
    op.execute(
        profiles.update()
        .where(profiles.c.id == FINOPS_PROFILE_ID)
        .where(profiles.c.group_by == "SERVICE")
        .values(group_by="NONE")
    )
