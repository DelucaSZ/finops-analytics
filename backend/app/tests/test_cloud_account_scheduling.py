from datetime import timedelta

from alembic import command
from sqlalchemy import MetaData, Table, create_engine, select

from app.db.base import utcnow
from app.db.migrations import migration_config


def _migrate(connection, revision: str, *, downgrade: bool = False) -> None:
    cfg = migration_config()
    cfg.attributes["connection"] = connection
    cfg.attributes["version_table"] = "deepops_mfa_schema_version"
    action = command.downgrade if downgrade else command.upgrade
    action(cfg, revision)


def _cloud(account_id: int, provider: str, native_id: str, now):
    return {
        "id": account_id,
        "provider": provider,
        "native_account_id": native_id,
        "name": f"{provider.upper()} {account_id}",
        "enabled": True,
        "connection_status": "connected",
        "last_connection_test_at": now,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }


def _aws(
    account_id: int,
    cloud_id: int,
    native_id: str,
    enabled: bool,
    interval: int,
    next_at,
    now,
):
    return {
        "id": account_id,
        "cloud_account_id": cloud_id,
        "name": f"AWS {native_id}",
        "aws_account_id": native_id,
        "enabled": True,
        "connection_status": "connected",
        "last_connection_test_at": now,
        "last_error": None,
        "role_arn": f"arn:aws:iam::{native_id}:role/DeepOps",
        "external_id": f"schedule-migration-{account_id}",
        "regions": ["sa-east-1"],
        "is_management_account": False,
        "schedule_enabled": enabled,
        "scan_interval_hours": interval,
        "next_scan_at": next_at,
        "created_at": now,
        "updated_at": now,
    }


def test_schedule_migration_preserves_aws_and_defaults_other_providers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schedule-migration.db'}")
    try:
        with engine.begin() as connection:
            _migrate(connection, "0017_oci_manual_collection")
            cloud = Table("cloud_accounts", MetaData(), autoload_with=connection)
            aws = Table("aws_accounts", MetaData(), autoload_with=connection)
            now = utcnow()
            past = now - timedelta(hours=3)
            future = now + timedelta(hours=7)
            connection.execute(
                cloud.insert(),
                [
                    _cloud(101, "aws", "111111111111", now),
                    _cloud(202, "aws", "222222222222", now),
                    _cloud(303, "oci", "ocid1.tenancy.oc1..schedulemigration", now),
                    _cloud(404, "azure", "subscription-schedule-migration", now),
                ],
            )
            connection.execute(
                aws.insert(),
                [
                    _aws(11, 101, "111111111111", True, 12, past, now),
                    _aws(22, 202, "222222222222", False, 168, future, now),
                ],
            )
            original = {row.cloud_account_id: row for row in connection.execute(select(aws)).mappings()}

            _migrate(connection, "0018_cloud_account_scheduling")

            migrated = Table("cloud_accounts", MetaData(), autoload_with=connection)
            rows = {row.id: row for row in connection.execute(select(migrated)).mappings()}
            assert (rows[101].schedule_enabled, rows[101].scan_interval_hours) == (True, 12)
            assert rows[101].next_scan_at == original[101].next_scan_at
            assert (rows[202].schedule_enabled, rows[202].scan_interval_hours) == (False, 168)
            assert rows[202].next_scan_at == original[202].next_scan_at
            for account_id in (303, 404):
                schedule = (
                    rows[account_id].schedule_enabled,
                    rows[account_id].scan_interval_hours,
                )
                assert schedule == (False, 24)
                assert rows[account_id].next_scan_at is None
    finally:
        engine.dispose()


def test_schedule_downgrade_copies_authoritative_values_back_to_aws(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schedule-downgrade.db'}")
    try:
        with engine.begin() as connection:
            _migrate(connection, "0017_oci_manual_collection")
            cloud = Table("cloud_accounts", MetaData(), autoload_with=connection)
            aws = Table("aws_accounts", MetaData(), autoload_with=connection)
            now = utcnow()
            connection.execute(cloud.insert().values(**_cloud(101, "aws", "111111111111", now)))
            connection.execute(
                aws.insert().values(**_aws(11, 101, "111111111111", False, 24, None, now))
            )
            _migrate(connection, "0018_cloud_account_scheduling")
            migrated = Table("cloud_accounts", MetaData(), autoload_with=connection)
            new_next = now + timedelta(hours=168)
            connection.execute(
                migrated.update()
                .where(migrated.c.id == 101)
                .values(schedule_enabled=True, scan_interval_hours=168, next_scan_at=new_next)
            )

            _migrate(connection, "0017_oci_manual_collection", downgrade=True)

            legacy = Table("aws_accounts", MetaData(), autoload_with=connection)
            restored = connection.execute(select(legacy).where(legacy.c.id == 11)).mappings().one()
            assert (restored.schedule_enabled, restored.scan_interval_hours) == (True, 168)
            assert restored.next_scan_at == new_next
    finally:
        engine.dispose()
