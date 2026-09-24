from alembic import context

from app.db.base import Base

# The runner owns the connection, lock and transaction. No unguarded CLI path.
connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    version_table=context.config.attributes.get("version_table", "alembic_version"),
)
with context.begin_transaction():
    context.run_migrations()
