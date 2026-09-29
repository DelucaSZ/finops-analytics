"""Introduce the provider-neutral administrative cloud account registry."""

import re

import sqlalchemy as sa
from alembic import op

revision = "0014_cloud_accounts"
down_revision = "0013_historical_retention"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def _validate_existing_aws_accounts() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, aws_account_id
            FROM aws_accounts
            ORDER BY id
            """
        )
    ).all()
    invalid = [
        (row.id, row.aws_account_id)
        for row in rows
        if not row.aws_account_id or not re.fullmatch(r"[0-9]{12}", row.aws_account_id)
    ]
    if invalid:
        raise RuntimeError(
            "Cannot create CloudAccount rows: invalid AWS account identifiers exist: "
            + ", ".join(f"id={row_id}" for row_id, _ in invalid[:10])
        )

    duplicates = bind.execute(
        sa.text(
            """
            SELECT aws_account_id, COUNT(*) AS total
            FROM aws_accounts
            GROUP BY aws_account_id
            HAVING COUNT(*) > 1
            """
        )
    ).all()
    if duplicates:
        raise RuntimeError(
            "Cannot create CloudAccount rows: duplicate AWS account identifiers exist"
        )


def _link_aws_accounts() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE aws_accounts SET cloud_account_id = id"))
    missing = bind.scalar(
        sa.text("SELECT COUNT(*) FROM aws_accounts WHERE cloud_account_id IS NULL")
    )
    if missing:
        raise RuntimeError(f"Cannot link {missing} AWS account(s) to CloudAccount")


def _constrain_aws_link() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(
            "aws_accounts",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch:
            batch.alter_column(
                "cloud_account_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch.create_unique_constraint(
                "uq_aws_accounts_cloud_account_id",
                ["cloud_account_id"],
            )
            batch.create_foreign_key(
                "fk_aws_accounts_cloud_account_id_cloud_accounts",
                "cloud_accounts",
                ["cloud_account_id"],
                ["id"],
                ondelete="CASCADE",
            )
        return

    op.alter_column(
        "aws_accounts",
        "cloud_account_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_aws_accounts_cloud_account_id",
        "aws_accounts",
        ["cloud_account_id"],
    )
    op.create_foreign_key(
        "fk_aws_accounts_cloud_account_id_cloud_accounts",
        "aws_accounts",
        "cloud_accounts",
        ["cloud_account_id"],
        ["id"],
        ondelete="CASCADE",
    )


def upgrade():
    _validate_existing_aws_accounts()

    op.create_table(
        "cloud_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("native_account_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("connection_status", sa.String(length=24), nullable=False),
        sa.Column("last_connection_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "native_account_id",
            name="uq_cloud_accounts_provider_native_account",
        ),
    )
    op.create_index("ix_cloud_accounts_provider", "cloud_accounts", ["provider"], unique=False)

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO cloud_accounts (
                id,
                provider,
                native_account_id,
                name,
                enabled,
                connection_status,
                last_connection_test_at,
                last_error,
                created_at,
                updated_at
            )
            SELECT
                id,
                'aws',
                aws_account_id,
                name,
                enabled,
                connection_status,
                last_connection_test_at,
                last_error,
                created_at,
                updated_at
            FROM aws_accounts
            """
        )
    )

    op.add_column("aws_accounts", sa.Column("cloud_account_id", sa.Integer(), nullable=True))
    _link_aws_accounts()
    _constrain_aws_link()

    account_count = bind.scalar(sa.text("SELECT COUNT(*) FROM aws_accounts")) or 0
    linked_count = bind.scalar(
        sa.text(
            """
            SELECT COUNT(*)
            FROM aws_accounts a
            JOIN cloud_accounts c ON c.id = a.cloud_account_id
            WHERE c.provider = 'aws' AND c.native_account_id = a.aws_account_id
            """
        )
    ) or 0
    if account_count != linked_count:
        raise RuntimeError(
            "CloudAccount migration did not produce exactly one matching row per AWS account"
        )


def downgrade():
    raise RuntimeError(
        "CloudAccount is the canonical administrative identity. "
        "Restore a verified pre-0014 backup instead of performing a lossy downgrade."
    )
