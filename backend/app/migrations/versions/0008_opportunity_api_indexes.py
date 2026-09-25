"""Add indexes for scalable opportunity filtering and ordering."""

import sqlalchemy as sa
from alembic import op

revision = "0008_opportunity_api_indexes"
down_revision = "0007_opportunity_lifecycle"
branch_labels = None
depends_on = None


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if name not in {item["name"] for item in inspector.get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade():
    _create_index_if_missing(
        "ix_findings_account_status_last_seen",
        "findings",
        ["account_id", "status", "last_seen_at"],
    )
    _create_index_if_missing(
        "ix_findings_status_severity",
        "findings",
        ["status", "severity"],
    )


def downgrade():
    raise RuntimeError("Opportunity query indexes belong to the active schema; do not downgrade")
