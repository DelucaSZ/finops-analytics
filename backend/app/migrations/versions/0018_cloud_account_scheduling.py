"""Move schedule state from AWS configuration to CloudAccount."""

import sqlalchemy as sa
from alembic import op

revision = "0018_cloud_account_scheduling"
down_revision = "0017_oci_manual_collection"
branch_labels = None
depends_on = None


def _cloud_accounts_table():
    return sa.table(
        "cloud_accounts",
        sa.column("id", sa.Integer()),
        sa.column("provider", sa.String()),
        sa.column("schedule_enabled", sa.Boolean()),
        sa.column("scan_interval_hours", sa.Integer()),
        sa.column("next_scan_at", sa.DateTime(timezone=True)),
    )


def _aws_accounts_table():
    return sa.table(
        "aws_accounts",
        sa.column("id", sa.Integer()),
        sa.column("cloud_account_id", sa.Integer()),
        sa.column("schedule_enabled", sa.Boolean()),
        sa.column("scan_interval_hours", sa.Integer()),
        sa.column("next_scan_at", sa.DateTime(timezone=True)),
    )


def upgrade():
    op.add_column(
        "cloud_accounts",
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("scan_interval_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.add_column(
        "cloud_accounts",
        sa.Column("next_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cloud_accounts_schedule_due",
        "cloud_accounts",
        ["schedule_enabled", "next_scan_at"],
        unique=False,
    )

    bind = op.get_bind()
    cloud_accounts = _cloud_accounts_table()
    aws_accounts = _aws_accounts_table()

    orphan_aws = bind.scalar(
        sa.select(sa.func.count()).select_from(aws_accounts).where(
            aws_accounts.c.cloud_account_id.is_(None)
        )
    ) or 0
    if orphan_aws:
        raise RuntimeError(
            "Cannot migrate AWS schedules: aws_accounts rows without cloud_account_id exist"
        )

    aws_schedule_rows = list(
        bind.execute(
            sa.select(
                aws_accounts.c.id,
                aws_accounts.c.cloud_account_id,
                aws_accounts.c.schedule_enabled,
                aws_accounts.c.scan_interval_hours,
                aws_accounts.c.next_scan_at,
            )
        ).mappings()
    )

    for row in aws_schedule_rows:
        result = bind.execute(
            cloud_accounts.update()
            .where(cloud_accounts.c.id == row["cloud_account_id"])
            .values(
                schedule_enabled=row["schedule_enabled"],
                scan_interval_hours=row["scan_interval_hours"],
                next_scan_at=row["next_scan_at"],
            )
        )
        if result.rowcount != 1:
            raise RuntimeError(
                "Cannot migrate AWS schedule: referenced CloudAccount does not exist "
                f"for aws_account_id={row['id']}"
            )

    migrated_rows = {
        row["id"]: row
        for row in bind.execute(
            sa.select(
                cloud_accounts.c.id,
                cloud_accounts.c.schedule_enabled,
                cloud_accounts.c.scan_interval_hours,
                cloud_accounts.c.next_scan_at,
            ).where(cloud_accounts.c.provider == "aws")
        ).mappings()
    }
    for row in aws_schedule_rows:
        migrated = migrated_rows.get(row["cloud_account_id"])
        if migrated is None:
            raise RuntimeError(
                "Cannot validate AWS schedule backfill: CloudAccount missing "
                f"for aws_account_id={row['id']}"
            )
        if (
            bool(migrated["schedule_enabled"]) != bool(row["schedule_enabled"])
            or migrated["scan_interval_hours"] != row["scan_interval_hours"]
            or migrated["next_scan_at"] != row["next_scan_at"]
        ):
            raise RuntimeError(
                "AWS schedule backfill integrity check failed "
                f"for aws_account_id={row['id']}"
            )


def downgrade():
    bind = op.get_bind()
    cloud_accounts = _cloud_accounts_table()
    aws_accounts = _aws_accounts_table()

    rows = list(
        bind.execute(
            sa.select(
                aws_accounts.c.id,
                aws_accounts.c.cloud_account_id,
                cloud_accounts.c.schedule_enabled,
                cloud_accounts.c.scan_interval_hours,
                cloud_accounts.c.next_scan_at,
            ).select_from(
                aws_accounts.join(
                    cloud_accounts,
                    aws_accounts.c.cloud_account_id == cloud_accounts.c.id,
                )
            )
        ).mappings()
    )
    for row in rows:
        bind.execute(
            aws_accounts.update()
            .where(aws_accounts.c.id == row["id"])
            .values(
                schedule_enabled=row["schedule_enabled"],
                scan_interval_hours=row["scan_interval_hours"],
                next_scan_at=row["next_scan_at"],
            )
        )

    op.drop_index("ix_cloud_accounts_schedule_due", table_name="cloud_accounts")
    op.drop_column("cloud_accounts", "next_scan_at")
    op.drop_column("cloud_accounts", "scan_interval_hours")
    op.drop_column("cloud_accounts", "schedule_enabled")
