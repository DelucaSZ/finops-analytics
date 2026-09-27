"""Indexes for collection account/status history without a provider prefix."""

from alembic import op

revision = "0010_collection_workspace"
down_revision = "0009_collection_compare_idx"
branch_labels = None
depends_on = None


def upgrade():
    # Composite indexes retain the same leading key; replace redundant single indexes.
    op.drop_index("ix_collection_runs_account_id", table_name="collection_runs")
    op.drop_index("ix_collection_runs_status", table_name="collection_runs")
    op.create_index(
        "ix_collection_runs_account_started", "collection_runs", ["account_id", "started_at"]
    )
    op.create_index(
        "ix_collection_runs_status_started", "collection_runs", ["status", "started_at"]
    )


def downgrade():
    raise RuntimeError("Collection workspace indexes belong to the active schema; do not downgrade")
