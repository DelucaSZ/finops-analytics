"""Add individual users and a persistent bootstrap/administration lock."""

import sqlalchemy as sa
from alembic import op

revision = "0002_users"
down_revision = "0001_legacy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bootstrap_complete", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_auth_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="ck_users_role"),
        sa.CheckConstraint("token_version >= 1", name="ck_users_token_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    state = sa.table(
        "auth_state", sa.column("id", sa.Integer), sa.column("bootstrap_complete", sa.Boolean)
    )
    op.bulk_insert(state, [{"id": 1, "bootstrap_complete": False}])


def downgrade():
    raise RuntimeError(
        "Users must be retained on application rollback; do not downgrade the schema"
    )
