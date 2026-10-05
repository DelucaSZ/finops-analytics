"""Allow provider-neutral scans without a legacy AWS account link."""

import sqlalchemy as sa
from alembic import op

revision = "0017_oci_manual_collection"
down_revision = "0016_provider_neutral_scan_queue"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(
            "scans",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch:
            batch.alter_column(
                "account_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
        return

    op.alter_column(
        "scans",
        "account_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    bind = op.get_bind()
    orphan_count = bind.scalar(sa.text("SELECT COUNT(*) FROM scans WHERE account_id IS NULL")) or 0
    if orphan_count:
        raise RuntimeError(
            "Cannot downgrade 0017 while provider-neutral scans with NULL account_id exist"
        )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            "scans",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch:
            batch.alter_column(
                "account_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
        return

    op.alter_column(
        "scans",
        "account_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
