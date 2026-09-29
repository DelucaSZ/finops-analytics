"""Add encrypted OCI API-key configuration and cloud-account audit events."""

import sqlalchemy as sa
from alembic import op

revision = "0015_oci_api_keys"
down_revision = "0014_cloud_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oci_account_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cloud_account_id", sa.Integer(), nullable=False),
        sa.Column("user_ocid", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("scope_regions", sa.JSON(), nullable=False),
        sa.Column("compartment_ocids", sa.JSON(), nullable=False),
        sa.Column("include_root_compartment", sa.Boolean(), nullable=False),
        sa.Column("include_subcompartments", sa.Boolean(), nullable=False),
        sa.Column("private_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("private_key_password_ciphertext", sa.Text(), nullable=True),
        sa.Column("credential_key_version", sa.String(length=32), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cloud_account_id"],
            ["cloud_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cloud_account_id"),
    )

    op.create_table(
        "cloud_account_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("native_account_id", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=24), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cloud_account_audit_events_account_id",
        "cloud_account_audit_events",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_cloud_account_audit_events_actor_id",
        "cloud_account_audit_events",
        ["actor_id"],
        unique=False,
    )


def downgrade():
    raise RuntimeError(
        "OCI credential storage cannot be downgraded without losing encrypted credentials. "
        "Restore a verified pre-0015 backup instead."
    )
