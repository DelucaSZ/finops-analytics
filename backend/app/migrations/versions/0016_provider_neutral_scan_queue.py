"""Prepare the scan queue for provider-neutral CloudAccount identity."""

import sqlalchemy as sa
from alembic import op

revision = "0016_provider_neutral_scan_queue"
down_revision = "0015_oci_api_keys"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def _invalid_scan_links() -> list[str]:
    bind = op.get_bind()
    return list(
        bind.scalars(
            sa.text(
                """
                SELECT s.id
                FROM scans s
                LEFT JOIN aws_accounts a ON a.id = s.account_id
                LEFT JOIN cloud_accounts c ON c.id = a.cloud_account_id
                WHERE a.id IS NULL
                   OR a.cloud_account_id IS NULL
                   OR c.id IS NULL
                   OR c.provider <> 'aws'
                ORDER BY s.id
                """
            )
        )
    )


def _validate_existing_scan_links() -> None:
    invalid = _invalid_scan_links()
    if invalid:
        sample = ", ".join(invalid[:10])
        raise RuntimeError(
            "Cannot migrate scans to CloudAccount: scan(s) do not resolve to a valid "
            f"AWS CloudAccount: {sample}"
        )


def _backfill_scan_cloud_accounts() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE scans
            SET cloud_account_id = (
                SELECT a.cloud_account_id
                FROM aws_accounts a
                WHERE a.id = scans.account_id
            )
            """
        )
    )

    inconsistent = list(
        bind.scalars(
            sa.text(
                """
                SELECT s.id
                FROM scans s
                JOIN aws_accounts a ON a.id = s.account_id
                WHERE s.cloud_account_id IS NULL
                   OR a.cloud_account_id IS NULL
                   OR s.cloud_account_id <> a.cloud_account_id
                ORDER BY s.id
                """
            )
        )
    )
    if inconsistent:
        sample = ", ".join(inconsistent[:10])
        raise RuntimeError(
            "Scan CloudAccount backfill failed its account identity invariant for scan(s): "
            + sample
        )


def _constrain_cloud_account_link() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(
            "scans",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch:
            batch.alter_column(
                "cloud_account_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch.create_foreign_key(
                "fk_scans_cloud_account_id_cloud_accounts",
                "cloud_accounts",
                ["cloud_account_id"],
                ["id"],
                ondelete="CASCADE",
            )
    else:
        op.alter_column(
            "scans",
            "cloud_account_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.create_foreign_key(
            "fk_scans_cloud_account_id_cloud_accounts",
            "scans",
            "cloud_accounts",
            ["cloud_account_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_index(
        "ix_scans_cloud_account_id",
        "scans",
        ["cloud_account_id"],
        unique=False,
    )


def upgrade():
    bind = op.get_bind()
    scan_count_before = bind.scalar(sa.text("SELECT COUNT(*) FROM scans")) or 0

    op.add_column(
        "scans",
        sa.Column("cloud_account_id", sa.Integer(), nullable=True),
    )
    _validate_existing_scan_links()
    _backfill_scan_cloud_accounts()
    _constrain_cloud_account_link()

    scan_count_after = bind.scalar(sa.text("SELECT COUNT(*) FROM scans")) or 0
    if scan_count_before != scan_count_after:
        raise RuntimeError("Scan CloudAccount migration changed the number of scans unexpectedly")


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.drop_index("ix_scans_cloud_account_id", table_name="scans")
        with op.batch_alter_table(
            "scans",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch:
            batch.drop_constraint(
                "fk_scans_cloud_account_id_cloud_accounts",
                type_="foreignkey",
            )
            batch.drop_column("cloud_account_id")
        return

    op.drop_index("ix_scans_cloud_account_id", table_name="scans")
    op.drop_constraint(
        "fk_scans_cloud_account_id_cloud_accounts",
        "scans",
        type_="foreignkey",
    )
    op.drop_column("scans", "cloud_account_id")
