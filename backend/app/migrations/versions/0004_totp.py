"""Add TOTP credentials, login challenges, recovery codes and security audit."""

import sqlalchemy as sa
from alembic import op

revision = "0004_totp"
down_revision = "0003_auth_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "login_sessions",
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "mfa_credentials",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("secret", sa.String(512), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.Integer(), nullable=False),
        sa.Column("reset_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pending_secret", sa.String(512), nullable=True),
        sa.Column("pending_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "pending_session_id", sa.String(36), sa.ForeignKey("login_sessions.id"), nullable=True
        ),
    )
    op.create_table(
        "mfa_challenges",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mfa_challenges_user_id", "mfa_challenges", ["user_id"])
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])
    op.create_table(
        "security_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"])


def downgrade():
    raise RuntimeError("MFA credentials must be preserved; do not downgrade")
