import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from app.api.routes.users import update_user
from app.core.config import Settings
from app.core.passwords import hash_password, verify_password
from app.db.base import Base
from app.db.migrations import initialize_database, wait_for_database
from app.models.account import AwsAccount
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_users"
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    with Session(migration_engine) as db:
        user = db.scalar(select(User))
        assert user.role == "admin" and user.is_active
        assert verify_password(PASSWORD, user.password_hash)


def test_existing_data_survives_migration_and_restart(migration_engine):
    legacy_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in {"users", "auth_state"}
    ]
    Base.metadata.create_all(migration_engine, tables=legacy_tables)
    with Session(migration_engine) as db:
        db.add(
            AwsAccount(
                id=9,
                name="Existing account",
                aws_account_id="123456789012",
                role_arn="legacy-role",
                external_id="legacy-id",
            )
        )
        db.commit()
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
        assert db.get(AwsAccount, 9).external_id == "legacy-id"
        user = db.get(User, original_id)
        assert user.email == "admin@example.com" and user.name == "Edited name"
        assert verify_password("Changed-in-database-123", user.password_hash)
        # Retained tables are also compatible with the old worker's create_all.
    Base.metadata.create_all(migration_engine, tables=legacy_tables)


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
