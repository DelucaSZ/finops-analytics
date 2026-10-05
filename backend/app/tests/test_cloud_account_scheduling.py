from datetime import timedelta

from alembic import command
from sqlalchemy import MetaData, Table, create_engine, select

from app.db.base import utcnow
from app.db.migrations import migration_config


def _upgrade(connection, revision: str) -> None:
    cfg = migration_config()
    cfg.attributes["connection"] = connection
    cfg.attributes["version_table"] = "deepops_mfa_schema_version"
    command.upgrade(cfg, revision)


def _downgrade(connection, revision: str) -> None:
    cfg = migration_config()
    cfg.attributes["connection"] = connection
    cfg.attributes["version_table"] = "deepops_mfa_schema_version"
    command.downgrade(cfg, revision)


def _cloud_row(*, account_id: int, provider: str, native_id: str, now):
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


def _aws_row(
    *,
    account_id: int,
    cloud_account_id: int,
    native_id: str,
    schedule_enabled: bool,
    interval: int,
    next_scan_at,
    now,
):
    return {
        "id": account_id,
        "cloud_account_id": cloud_account_id,
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
        "schedule_enabled": schedule_enabled,
        "scan_interval_hours": interval,
        "next_scan_at": next_scan_at,
        "created_at": now,
        "updated_at": now,
    }


def test_cloud_account_schedule_migration_preserves_aws_and_defaults_other_providers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schedule-migration.db'}")
    try:
        with engine.begin() as connection:
            _upgrade(connection, "0017_oci_manual_collection")
            metadata = MetaData()
            cloud_accounts = Table("cloud_accounts", metadata, autoload_with=connection)
            aws_accounts = Table("aws_accounts", metadata, autoload_with=connection)
            now = utcnow()
            past = now - timedelta(hours=3)
            future = now + timedelta(hours=7)

            connection.execute(
                cloud_accounts.insert(),
                [
                    _cloud_row(
                        account_id=101,
                        provider="aws",
                        native_id="111111111111",
                        now=now,
                    ),
                    _cloud_row(
                        account_id=202,
                        provider="aws",
                        native_id="222222222222",
                        now=now,
                    ),
                    _cloud_row(
                        account_id=303,
                        provider="oci",
                        native_id="ocid1.tenancy.oc1..schedulemigration",
                        now=now,
                    ),
                    _cloud_row(
                        account_id=404,
                        provider="azure",
                        native_id="subscription-schedule-migration",
                        now=now,
                    ),
                ],
            )
            connection.execute(
                aws_accounts.insert(),
                [
                    _aws_row(
                        account_id=11,
                        cloud_account_id=101,
                        native_id="111111111111",
                        schedule_enabled=True,
                        interval=12,
                        next_scan_at=past,
                        now=now,
                    ),
                    _aws_row(
                        account_id=22,
                        cloud_account_id=202,
                        native_id="222222222222",
                        schedule_enabled=False,
                        interval=168,
                        next_scan_at=future,
                        now=now,
                    ),
                ],
            )
            original = {
                row.cloud_account_id: row
                for row in connection.execute(select(aws_accounts)).mappings()
            }

            _upgrade(connection, "0018_cloud_account_scheduling")

            migrated_cloud = Table("cloud_accounts", MetaData(), autoload_with=connection)
            rows = {
                row.id: row
                for row in connection.execute(select(migrated_cloud)).mappings()
            }
            assert rows[101].schedule_enabled is True
            assert rows[101].scan_interval_hours == 12
            assert rows[101].next_scan_at == original[101].next_scan_at
            assert rows[202].schedule_enabled is False
            assert rows[202].scan_interval_hours == 168
            assert rows[202].next_scan_at == original[202].next_scan_at

            for provider_id in (303, 404):
                assert rows[provider_id].schedule_enabled is False
                assert rows[provider_id].scan_interval_hours == 24
                assert rows[provider_id].next_scan_at is None
    finally:
        engine.dispose()


def test_cloud_account_schedule_downgrade_copies_authoritative_values_back_to_aws(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schedule-downgrade.db'}")
    try:
        with engine.begin() as connection:
            _upgrade(connection, "0017_oci_manual_collection")
            cloud_accounts = Table("cloud_accounts", MetaData(), autoload_with=connection)
            aws_accounts = Table("aws_accounts", MetaData(), autoload_with=connection)
            now = utcnow()
            connection.execute(
                cloud_accounts.insert().values(
                    **_cloud_row(
                        account_id=101,
                        provider="aws",
                        native_id="111111111111",
                        now=now,
                    )
                )
            )
            connection.execute(
                aws_accounts.insert().values(
                    **_aws_row(
                        account_id=11,
                        cloud_account_id=101,
                        native_id="111111111111",
                        schedule_enabled=False,
                        interval=24,
                        next_scan_at=None,
                        now=now,
                    )
                )
            )
            _upgrade(connection, "0018_cloud_account_scheduling")

            migrated_cloud = Table("cloud_accounts", MetaData(), autoload_with=connection)
            new_next = now + timedelta(hours=168)
            connection.execute(
                migrated_cloud.update()
                .where(migrated_cloud.c.id == 101)
                .values(
                    schedule_enabled=True,
                    scan_interval_hours=168,
                    next_scan_at=new_next,
                )
            )

            _downgrade(connection, "0017_oci_manual_collection")

            legacy_aws = Table("aws_accounts", MetaData(), autoload_with=connection)
            restored = connection.execute(
                select(legacy_aws).where(legacy_aws.c.id == 11)
            ).mappings().one()
            assert restored.schedule_enabled is True
            assert restored.scan_interval_hours == 168
            assert restored.next_scan_at == new_next
    finally:
        engine.dispose()
