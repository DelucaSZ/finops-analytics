"""Add comparison-oriented observation index."""

import sqlalchemy as sa
from alembic import op

revision = "0009_collection_comparison_indexes"
down_revision = "0008_opportunity_api_indexes"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes("opportunity_observations")}
    name = "ix_opportunity_observations_run_opportunity"
    if name not in existing:
        op.create_index(
            name,
            "opportunity_observations",
            ["collection_run_id", "opportunity_id"],
        )


def downgrade():
    raise RuntimeError("Collection comparison index belongs to the active schema; do not downgrade")
