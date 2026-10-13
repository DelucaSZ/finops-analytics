"""Add persistent daily execution checkpoint for opportunity retention."""

from alembic import op
import sqlalchemy as sa

revision = "0023_opportunity_retention"
down_revision = "0022_opportunity_archiving"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_retention_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_date", name="uq_opportunity_retention_runs_period_date"),
    )
    op.create_index(
        "ix_opportunity_retention_runs_period_date",
        "opportunity_retention_runs",
        ["period_date"],
        unique=False,
    )
    op.create_index(
        "ix_opportunity_retention_runs_status",
        "opportunity_retention_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_retention_runs_status",
        table_name="opportunity_retention_runs",
    )
    op.drop_index(
        "ix_opportunity_retention_runs_period_date",
        table_name="opportunity_retention_runs",
    )
    op.drop_table("opportunity_retention_runs")
