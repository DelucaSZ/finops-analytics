"""Synchronize the CloudAccount PostgreSQL sequence after the Stage 17 backfill."""

import sqlalchemy as sa
from alembic import op

revision = "0016_cloud_account_sequence"
down_revision = "0015_oci_api_keys"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Stage 17 inserted CloudAccount rows with explicit IDs copied from aws_accounts.
    # PostgreSQL sequences are not advanced by explicit INSERT values, so the first
    # post-upgrade registration could otherwise reuse an existing primary key.
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('cloud_accounts', 'id'),
                CASE WHEN COUNT(*) = 0 THEN 1 ELSE MAX(id) END,
                COUNT(*) > 0
            )
            FROM cloud_accounts
            """
        )
    )


def downgrade():
    # Sequence synchronization is data-preserving and does not change the schema.
    # Earlier revisions are already intentionally non-downgradable; no reverse
    # mutation is required here.
    pass
