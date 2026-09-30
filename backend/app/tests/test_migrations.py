import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from app.api.routes.users import update_user
from app.core.config import Settings
from app.core.passwords import hash_password, verify_password
from app.db.base import Base, utcnow
from app.db.migrations import initialize_database, migration_config, wait_for_database
from app.models.account import AwsAccount, CloudAccount, OciAccountConfiguration
from app.models.user import AuthState, User
from app.schemas.user import UserUpdate

PASSWORD = "Migration-test-password-42"


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(
            f"sqlite:///{tmp_path / 'migration.db'}",
            connect_args={"check_same_thread": False, "timeout": 20},
        )
        yield engine
        engine.dispose()
        return
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise real PostgreSQL transactions")
    schema = "test_" + uuid.uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def config(**changes):
    return Settings(
        NUVEMIQ_ADMIN_EMAIL="admin@example.com", NUVEMIQ_ADMIN_PASSWORD=PASSWORD, **changes
    )


def test_fresh_database_matches_models_and_worker_is_ready(migration_engine):
    initialize_database(migration_engine, config())
    wait_for_database(migration_engine, timeout=0)
    with migration_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM deepops_mfa_schema_version"))
            == "0016_cloud_account_sequence"
        )
        assert (
            compare_metadata(
                MigrationContext.configure(
                    connection,
                    opts={
                        "version_table": "deepops_mfa_schema_version",
                        "include_object": lambda obj, name, *args: (
                            name not in {"alembic_version", "deepops_schema_version"}
                        ),
                    },
                ),
                Base.metadata,
            )
            == []
        )
    with Session(migration_engine) as db:
        user = db.scalar(select(User))
        assert user.role == "admin" and user.is_active
        assert verify_password(PASSWORD, user.password_hash)


def test_existing_data_survives_migration_and_restart(migration_engine):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001_legacy")
        accounts = Table("aws_accounts", MetaData(), autoload_with=connection)
        now = utcnow()
        connection.execute(
            accounts.insert().values(
                id=9,
                name="Existing account",
                aws_account_id="123456789012",
                role_arn="legacy-role",
                external_id="legacy-id",
                regions=["sa-east-1"],
                enabled=True,
                is_management_account=False,
                schedule_enabled=False,
                scan_interval_hours=24,
                next_scan_at=None,
                connection_status="untested",
                last_connection_test_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )

    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        user = db.scalar(select(User))
        original_id = user.id
        user.name = "Edited name"
        user.password_hash = hash_password("Changed-in-database-123")
        db.commit()
    initialize_database(
        migration_engine,
        Settings(
            NUVEMIQ_ADMIN_EMAIL="new@example.com", NUVEMIQ_ADMIN_PASSWORD="Different-env-password"
        ),
    )
    with Session(migration_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        aws_account = db.get(AwsAccount, 9)
        assert aws_account.external_id == "legacy-id"
        assert aws_account.cloud_account_id == 9
        cloud_account = db.get(CloudAccount, 9)
        assert cloud_account is not None
        assert cloud_account.provider == "aws"
        assert cloud_account.native_account_id == "123456789012"
        assert cloud_account.name == "Existing account"
        user = db.get(User, original_id)
        assert user.email == "admin@example.com" and user.name == "Edited name"
        assert verify_password("Changed-in-database-123", user.password_hash)


def test_failed_bootstrap_rolls_back_and_can_be_retried(migration_engine):
    with pytest.raises(RuntimeError, match="NUVEMIQ_ADMIN_PASSWORD"):
        initialize_database(migration_engine, Settings(NUVEMIQ_ADMIN_PASSWORD="change-me"))
    assert "users" not in inspect(migration_engine).get_table_names()
    initialize_database(migration_engine, config())
    wait_for_database(migration_engine, timeout=0)


def test_completed_bootstrap_never_recreates_an_env_admin(migration_engine):
    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        db.delete(db.scalar(select(User)))
        db.commit()
    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        assert db.scalar(select(User)) is None
        assert db.get(AuthState, 1).bootstrap_complete


def test_worker_refuses_uninitialized_database(migration_engine):
    with pytest.raises(RuntimeError, match="initialization timed out"):
        wait_for_database(migration_engine, timeout=0)


def test_simultaneous_admin_changes_cannot_remove_all_admins(migration_engine):
    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        admin = db.scalar(select(User))
        second = User(
            name="Second",
            email="second@example.com",
            role="admin",
            password_hash=admin.password_hash,
        )
        db.add(second)
        db.commit()
        ids = [admin.id, second.id]
    barrier = threading.Barrier(2)

    def deactivate(actor_id):
        from fastapi import HTTPException

        with Session(migration_engine) as db:
            actor = db.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                update_user(actor_id, UserUpdate(is_active=False), db, actor)
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deactivate, ids))
    assert sorted(results) == [200, 409]
    with Session(migration_engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.is_active.is_(True))
            )
            == 1
        )


def test_stage_one_users_survive_and_old_image_checkpoint_still_works(migration_engine):
    from alembic import command
    from sqlalchemy import MetaData, Table

    from app.db.base import utcnow
    from app.db.migrations import migration_config

    existing_hash = hash_password(PASSWORD)
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0002_users")
        users = Table("users", MetaData(), autoload_with=connection)
        state = Table("auth_state", MetaData(), autoload_with=connection)
        connection.execute(
            users.insert().values(
                id="existing",
                name="Existing",
                email="old@example.com",
                password_hash=existing_hash,
                role="admin",
                is_active=True,
                token_version=7,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        connection.execute(state.update().values(bootstrap_complete=True))
    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        user = db.get(User, "existing")
        assert user.password_set and user.password_hash == existing_hash and user.token_version == 7
        assert db.scalar(select(func.count()).select_from(User)) == 1
    with migration_engine.begin() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0002_users"
        # Exact revision lookup + no-op upgrade used by the previous image.
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0002_users")
    initialize_database(migration_engine, config())
    wait_for_database(migration_engine, timeout=0)


def test_one_time_reset_is_atomic_under_concurrency(migration_engine):
    from fastapi import HTTPException, Request, Response

    from app.api.routes.auth import _complete_access
    from app.models.auth import AccessToken
    from app.schemas.auth import CompleteAccess
    from app.services.authentication import issue_token

    initialize_database(migration_engine, config())
    with Session(migration_engine) as db:
        user = db.scalar(select(User))
        raw, _ = issue_token(db, user, "reset")
        db.commit()
    barrier = threading.Barrier(2)

    def consume(_):
        with Session(migration_engine) as db:
            barrier.wait(timeout=10)
            request = Request({"type": "http", "method": "POST", "client": ("127.0.0.1", 1)})
            try:
                _complete_access(
                    CompleteAccess(token=raw, password="Another-password-987!"),
                    request,
                    Response(),
                    db,
                    "reset",
                )
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, [1, 2]))
    assert sorted(results) == [200, 400]
    with Session(migration_engine) as db:
        assert db.scalar(select(User)).token_version == 2
        assert db.scalar(select(AccessToken)).used_at is not None


@pytest.mark.parametrize("kind", ["totp", "recovery", "challenge"])
def test_mfa_proofs_are_atomic_under_concurrency(migration_engine, monkeypatch, kind):
    import pyotp
    from fastapi import HTTPException, Request, Response

    from app.api.routes.mfa import verify_login
    from app.core.config import settings
    from app.db.base import utcnow
    from app.models.mfa import MfaCredential, RecoveryCode
    from app.schemas.auth import MfaLogin
    from app.services import mfa
    from app.services.users import lock_user_changes

    monkeypatch.setattr(settings, "secret_key", "Test-only-concurrent-MFA-key-at-least-32-bytes")
    initialize_database(migration_engine, config())
    secret = pyotp.random_base32()
    with Session(migration_engine) as db:
        user = db.scalar(select(User))
        user_id = user.id
        db.add(
            MfaCredential(
                user_id=user.id,
                secret=mfa.cipher().encrypt(secret.encode()).decode(),
                enabled_at=utcnow(),
            )
        )
        codes = mfa.recovery_codes(db, user.id)
        pending = mfa.challenge(db, user)
        db.commit()
    code = codes[0] if kind == "recovery" else pyotp.TOTP(secret).now()
    barrier = threading.Barrier(2)

    def consume(_):
        with Session(migration_engine) as db:
            barrier.wait(timeout=10)
            if kind == "challenge":
                request = Request(
                    {"type": "http", "method": "POST", "client": ("127.0.0.1", 1), "headers": []}
                )
                try:
                    verify_login(MfaLogin(challenge=pending, code=code), request, Response(), db)
                    return 200
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code
            lock_user_changes(db)
            accepted = mfa.verify_factor(db, mfa.credential(db, user_id), code)
            db.commit()
            return 200 if accepted else 400

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, [1, 2]))
    assert sorted(results) == [200, 400]
    if kind == "recovery":
        with Session(migration_engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(RecoveryCode)
                    .where(RecoveryCode.used_at.is_not(None))
                )
                == 1
            )
    with migration_engine.connect() as connection:
        # Previous image reads this checkpoint, not the new MFA revision.
        assert (
            connection.scalar(text("SELECT version_num FROM deepops_schema_version"))
            == "0003_auth_lifecycle"
        )


def test_stage17_migration_preserves_history(migration_engine):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0013_historical_retention")

        metadata = MetaData()
        aws_table = Table("aws_accounts", metadata, autoload_with=connection)
        scans_table = Table("scans", metadata, autoload_with=connection)
        runs_table = Table("collection_runs", metadata, autoload_with=connection)
        findings_table = Table("findings", metadata, autoload_with=connection)
        observations_table = Table("opportunity_observations", metadata, autoload_with=connection)
        decisions_table = Table("opportunity_status_history", metadata, autoload_with=connection)
        now = utcnow()

        connection.execute(
            aws_table.insert().values(
                id=42,
                name="Preserved AWS",
                aws_account_id="444444444444",
                role_arn="arn:aws:iam::444444444444:role/DeepOps",
                external_id="migration-external-id",
                regions=["sa-east-1"],
                enabled=True,
                is_management_account=True,
                schedule_enabled=True,
                scan_interval_hours=24,
                next_scan_at=now,
                connection_status="connected",
                last_connection_test_at=now,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            scans_table.insert().values(
                id="stage17-scan",
                account_id=42,
                status="completed",
                trigger="manual",
                started_at=now,
                completed_at=now,
                findings_count=1,
                error=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            runs_table.insert().values(
                id="stage17-run",
                scan_id="stage17-scan",
                provider="aws",
                account_id="444444444444",
                scope={"regions": ["sa-east-1"]},
                started_at=now,
                finished_at=now,
                status="SUCCESS",
                resources_analyzed=0,
                opportunities_found=1,
                detailed_observations_available=True,
                analyzer_version="migration-test",
                error_detail=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            findings_table.insert().values(
                id="stage17-finding",
                fingerprint="4" * 64,
                scan_id="stage17-scan",
                provider="aws",
                account_id="444444444444",
                rule_key="ebs_unattached",
                service="EC2",
                region="sa-east-1",
                resource_id="vol-stage17",
                resource_name="volume",
                resource_type="EBS Volume",
                provider_metadata={},
                title="Preserved opportunity",
                description="Migration fixture",
                evidence={"state": "available"},
                current_monthly_cost=10,
                estimated_monthly_savings=10,
                currency="USD",
                confidence="high",
                severity="medium",
                status="rejected",
                total_occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                treated_at=None,
                treated_by=None,
                treatment_note=None,
                rejected_at=now,
                rejected_by=None,
                rejection_reason="not_applicable",
                rejection_note="Keep the human decision",
                needs_review=False,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            observations_table.insert().values(
                id="stage17-observation",
                opportunity_id="stage17-finding",
                collection_run_id="stage17-run",
                observed_at=now,
                severity="medium",
                current_monthly_cost=10,
                estimated_monthly_savings=10,
                currency="USD",
                confidence="high",
                provider_metadata={},
                evidence={"state": "available"},
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            decisions_table.insert().values(
                id="stage17-decision",
                opportunity_id="stage17-finding",
                from_status="open",
                to_status="rejected",
                action="reject",
                reason="not_applicable",
                note="Keep the human decision",
                changed_by=None,
                changed_at=now,
                created_at=now,
                updated_at=now,
            )
        )

        command.upgrade(cfg, "head")

        common_table = Table("cloud_accounts", MetaData(), autoload_with=connection)
        migrated_aws = Table("aws_accounts", MetaData(), autoload_with=connection)
        cloud = connection.execute(select(common_table).where(common_table.c.id == 42)).one()
        assert cloud.provider == "aws"
        assert cloud.native_account_id == "444444444444"
        assert cloud.name == "Preserved AWS"
        assert (
            connection.scalar(
                select(migrated_aws.c.cloud_account_id).where(migrated_aws.c.id == 42)
            )
            == 42
        )
        assert (
            connection.scalar(
                select(scans_table.c.account_id).where(scans_table.c.id == "stage17-scan")
            )
            == 42
        )

        run = connection.execute(select(runs_table).where(runs_table.c.id == "stage17-run")).one()
        assert run.provider == "aws"
        assert run.account_id == "444444444444"

        finding = connection.execute(
            select(findings_table).where(findings_table.c.id == "stage17-finding")
        ).one()
        assert finding.fingerprint == "4" * 64
        assert finding.status == "rejected"
        assert finding.rejection_note == "Keep the human decision"
        assert (
            connection.scalar(
                select(func.count())
                .select_from(observations_table)
                .where(observations_table.c.opportunity_id == "stage17-finding")
            )
            == 1
        )
        decision = connection.execute(
            select(decisions_table).where(decisions_table.c.id == "stage17-decision")
        ).one()
        assert decision.to_status == "rejected"
        assert decision.note == "Keep the human decision"


def test_stage17_migration_refuses_inconsistent_aws_identity(migration_engine):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0013_historical_retention")
        aws_table = Table("aws_accounts", MetaData(), autoload_with=connection)
        now = utcnow()
        connection.execute(
            aws_table.insert().values(
                id=99,
                name="Invalid legacy identity",
                aws_account_id="ABCDEFGHIJKL",
                role_arn="legacy",
                external_id="legacy",
                regions=["sa-east-1"],
                enabled=True,
                is_management_account=False,
                schedule_enabled=False,
                scan_interval_hours=24,
                next_scan_at=None,
                connection_status="untested",
                last_connection_test_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(RuntimeError, match="invalid AWS account identifiers"):
            command.upgrade(cfg, "0014_cloud_accounts")


def test_stage18_migration_adds_oci_storage_without_rewriting_aws(migration_engine):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0014_cloud_accounts")

        cloud_table = Table("cloud_accounts", MetaData(), autoload_with=connection)
        aws_table = Table("aws_accounts", MetaData(), autoload_with=connection)
        now = utcnow()
        connection.execute(
            cloud_table.insert().values(
                id=77,
                provider="aws",
                native_account_id="777777777777",
                name="Stage 18 preserved AWS",
                enabled=True,
                connection_status="connected",
                last_connection_test_at=now,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            aws_table.insert().values(
                id=77,
                cloud_account_id=77,
                name="Stage 18 preserved AWS",
                aws_account_id="777777777777",
                enabled=True,
                connection_status="connected",
                last_connection_test_at=now,
                last_error=None,
                role_arn="arn:aws:iam::777777777777:role/DeepOps",
                external_id="stage18-migration-test",
                regions=["sa-east-1"],
                is_management_account=False,
                schedule_enabled=False,
                scan_interval_hours=24,
                next_scan_at=None,
                created_at=now,
                updated_at=now,
            )
        )

        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        assert "oci_account_configurations" in inspector.get_table_names()
        assert "cloud_account_audit_events" in inspector.get_table_names()
        preserved = connection.execute(select(aws_table).where(aws_table.c.id == 77)).one()
        assert preserved.aws_account_id == "777777777777"
        assert preserved.cloud_account_id == 77

    with Session(migration_engine) as db:
        assert db.get(CloudAccount, 77).provider == "aws"
        assert db.scalar(select(func.count()).select_from(OciAccountConfiguration)) == 0


def test_stage21_cloud_account_sequence_continues_after_stage17_backfill(migration_engine):
    """A migrated PostgreSQL database must allocate a fresh CloudAccount id."""

    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0013_historical_retention")

        aws_table = Table("aws_accounts", MetaData(), autoload_with=connection)
        now = utcnow()
        connection.execute(
            aws_table.insert().values(
                id=50,
                name="Sequence preservation fixture",
                aws_account_id="505050505050",
                role_arn="arn:aws:iam::505050505050:role/DeepOps",
                external_id="stage21-sequence-external-id",
                regions=["sa-east-1"],
                enabled=True,
                is_management_account=False,
                schedule_enabled=False,
                scan_interval_hours=24,
                next_scan_at=None,
                connection_status="connected",
                last_connection_test_at=now,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        command.upgrade(cfg, "head")

    with Session(migration_engine) as db:
        migrated = db.get(CloudAccount, 50)
        assert migrated is not None
        assert migrated.native_account_id == "505050505050"

        created = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..stage21sequencefixture",
            name="Post-migration account",
            enabled=True,
        )
        db.add(created)
        db.commit()
        db.refresh(created)

        assert created.id > migrated.id
