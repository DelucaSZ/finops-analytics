"""Prepare the central opportunity domain for multiple cloud providers."""

import sqlalchemy as sa
from alembic import op

revision = "0011_multicloud_core"
down_revision = "0010_collection_workspace"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _drop_index_if_present(name: str, table: str) -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name in indexes:
        op.drop_index(name, table_name=table)


def _foreign_key_name(table: str, column: str) -> str | None:
    for item in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if item.get("constrained_columns") == [column]:
            return item.get("name")
    return None


def _backfill_native_account_identity() -> None:
    bind = op.get_bind()
    findings = sa.table(
        "findings",
        sa.column("id", sa.String()),
        sa.column("account_id", sa.Integer()),
        sa.column("provider", sa.String()),
        sa.column("provider_account_id", sa.String()),
    )
    accounts = sa.table(
        "aws_accounts",
        sa.column("id", sa.Integer()),
        sa.column("aws_account_id", sa.String()),
    )
    external_account_id = (
        sa.select(accounts.c.aws_account_id)
        .where(accounts.c.id == findings.c.account_id)
        .scalar_subquery()
    )
    bind.execute(
        sa.update(findings).values(
            provider="aws",
            provider_account_id=external_account_id,
        )
    )
    unresolved = bind.scalar(
        sa.select(sa.func.count())
        .select_from(findings)
        .where(findings.c.provider_account_id.is_(None))
    )
    if unresolved:
        raise RuntimeError(
            "Cannot migrate findings to provider-native account identity: "
            f"{unresolved} finding(s) do not resolve to aws_accounts."
        )


def _alter_findings_sqlite() -> None:
    with op.batch_alter_table(
        "findings",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint(
            "fk_findings_account_id_aws_accounts",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_findings_scan_id_scans",
            type_="foreignkey",
        )
        batch.drop_column("account_id")
        batch.alter_column(
            "provider_account_id",
            new_column_name="account_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch.alter_column(
            "provider",
            existing_type=sa.String(length=16),
            nullable=False,
        )
        batch.alter_column(
            "scan_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.alter_column(
            "service",
            existing_type=sa.String(length=40),
            type_=sa.String(length=120),
            nullable=False,
        )
        batch.alter_column(
            "region",
            existing_type=sa.String(length=40),
            type_=sa.String(length=120),
            nullable=True,
        )
        batch.create_foreign_key(
            "fk_findings_scan_id_scans",
            "scans",
            ["scan_id"],
            ["id"],
            ondelete="SET NULL",
        )


def _alter_findings_postgresql() -> None:
    account_fk = _foreign_key_name("findings", "account_id")
    scan_fk = _foreign_key_name("findings", "scan_id")
    if account_fk:
        op.drop_constraint(account_fk, "findings", type_="foreignkey")
    if scan_fk:
        op.drop_constraint(scan_fk, "findings", type_="foreignkey")

    op.drop_column("findings", "account_id")
    op.alter_column(
        "findings",
        "provider_account_id",
        new_column_name="account_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "findings",
        "provider",
        existing_type=sa.String(length=16),
        nullable=False,
    )
    op.alter_column(
        "findings",
        "scan_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.alter_column(
        "findings",
        "service",
        existing_type=sa.String(length=40),
        type_=sa.String(length=120),
        existing_nullable=False,
    )
    op.alter_column(
        "findings",
        "region",
        existing_type=sa.String(length=40),
        type_=sa.String(length=120),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_findings_scan_id_scans",
        "findings",
        "scans",
        ["scan_id"],
        ["id"],
        ondelete="SET NULL",
    )


def upgrade():
    op.add_column(
        "collection_runs",
        sa.Column(
            "scope",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "opportunity_observations",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
    )
    op.add_column(
        "opportunity_observations",
        sa.Column(
            "provider_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    op.add_column("findings", sa.Column("provider", sa.String(length=16), nullable=True))
    op.add_column(
        "findings",
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("resource_type", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column(
            "provider_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "findings",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
    )

    _backfill_native_account_identity()
    _drop_index_if_present("ix_findings_account_status_last_seen", "findings")
    _drop_index_if_present("ix_findings_account_id", "findings")

    if op.get_bind().dialect.name == "sqlite":
        _alter_findings_sqlite()
    else:
        _alter_findings_postgresql()

    op.create_index("ix_findings_provider", "findings", ["provider"])
    op.create_index("ix_findings_account_id", "findings", ["account_id"])
    op.create_index(
        "ix_findings_provider_account_status_last_seen",
        "findings",
        ["provider", "account_id", "status", "last_seen_at"],
    )


def downgrade():
    raise RuntimeError(
        "The multi-cloud identity migration changes the meaning of findings.account_id. "
        "Restore a verified pre-0011 backup rather than performing a lossy downgrade."
    )
