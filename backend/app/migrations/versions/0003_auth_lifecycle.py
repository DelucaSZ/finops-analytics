"""Add revocable sessions, one-time access links and persistent rate limits."""

import sqlalchemy as sa
from alembic import op

revision = "0003_auth_lifecycle"
down_revision = "0002_users"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_access_tokens_user_id"), "access_tokens", ["user_id"], unique=False)
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_login_sessions_user_id"), "login_sessions", ["user_id"], unique=False)
    op.add_column(
        "users",
        sa.Column("password_set", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Keep authentication data on application rollback; do not downgrade")
