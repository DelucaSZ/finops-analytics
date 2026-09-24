"""Add provider-neutral collection execution tracking."""

import sqlalchemy as sa
from alembic import op

revision = "0005_collection_runs"
down_revision = "0004_totp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resources_analyzed", sa.Integer(), nullable=False),
        sa.Column("opportunities_found", sa.Integer(), nullable=False),
        sa.Column("analyzer_version", sa.String(length=80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id"),
    )
    op.create_index("ix_collection_runs_account_id", "collection_runs", ["account_id"])
    op.create_index("ix_collection_runs_provider", "collection_runs", ["provider"])
    op.create_index("ix_collection_runs_started_at", "collection_runs", ["started_at"])
    op.create_index("ix_collection_runs_status", "collection_runs", ["status"])
    op.create_index(
        "ix_collection_runs_provider_account_started",
        "collection_runs",
        ["provider", "account_id", "started_at"],
    )


def downgrade():
    raise RuntimeError("Collection history must be preserved; do not downgrade")
