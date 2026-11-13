"""Represent unavailable AWS policy prices without fabricating zero savings.

Revision ID: 0043_aws_policy_nullable_finance
Revises: 0042_aws_pricing_manual_requests
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_aws_policy_nullable_finance"
down_revision = "0042_aws_pricing_manual_requests"
branch_labels = None
depends_on = None

_TABLES = (
    "findings",
    "opportunity_observations",
    "opportunity_history_snapshots",
)
_COLUMNS = ("current_monthly_cost", "estimated_monthly_savings")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            for column in _COLUMNS:
                batch_op.alter_column(
                    column,
                    existing_type=sa.Numeric(14, 2),
                    existing_nullable=False,
                    nullable=True,
                )


def downgrade() -> None:
    connection = op.get_bind()
    for table in _TABLES:
        nulls = connection.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE current_monthly_cost IS NULL OR estimated_monthly_savings IS NULL"
            )
        ).scalar_one()
        if nulls:
            raise RuntimeError(
                f"Cannot restore NOT NULL monetary columns on {table}: "
                f"{nulls} rows contain unknown estimates"
            )
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch_op:
            for column in _COLUMNS:
                batch_op.alter_column(
                    column,
                    existing_type=sa.Numeric(14, 2),
                    existing_nullable=True,
                    nullable=False,
                )
