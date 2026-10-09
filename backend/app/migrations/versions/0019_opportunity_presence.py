"""Add provider-neutral opportunity presence lifecycle state."""

import sqlalchemy as sa
from alembic import op

revision = "0019_opportunity_presence"
down_revision = "0018_cloud_account_scheduling"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("findings") as batch:
        batch.add_column(
            sa.Column(
                "presence_status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            )
        )
        batch.add_column(sa.Column("missing_since_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("resolved_externally_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "ck_findings_presence_status",
            "presence_status IN ('active', 'missing', 'resolved_externally')",
        )
        batch.create_index("ix_findings_presence_status", ["presence_status"])


def downgrade():
    raise RuntimeError("Opportunity presence lifecycle state must be preserved; do not downgrade")
