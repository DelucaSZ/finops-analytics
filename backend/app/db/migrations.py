"""Run versioned migrations and bootstrap atomically before the API starts serving."""

import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.user import AuthState
from app.services.users import bootstrap_admin


def migration_config() -> Config:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    return config


def initialize_database(engine: Engine, config: Settings = settings) -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(732091804)"))
        elif engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            raise RuntimeError("Only PostgreSQL and SQLite are supported")
        alembic_config = migration_config()
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
        with Session(bind=connection) as db:
            bootstrap_admin(db, config)
            db.flush()


def wait_for_database(engine: Engine, timeout: float = 120) -> None:
    """Workers never perform DDL; the API initializes the database first."""
    expected = ScriptDirectory.from_config(migration_config()).get_current_head()
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect() as connection:
                current = MigrationContext.configure(connection).get_current_revision()
                if current == expected and connection.scalar(
                    select(AuthState.bootstrap_complete).where(AuthState.id == 1)
                ):
                    return
        except SQLAlchemyError:
            pass  # API may still be connecting/migrating.
        if time.monotonic() >= deadline:
            raise RuntimeError("Database initialization timed out; inspect API startup logs")
        time.sleep(1)


if __name__ == "__main__":
    from app.db.session import engine

    initialize_database(engine)
