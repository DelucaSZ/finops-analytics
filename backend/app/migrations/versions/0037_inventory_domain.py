"""Inventory current state and immutable observation history.

Revision ID: 0037_inventory_domain
Revises: 0036_rds_reservation_coverage
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_inventory_domain"
down_revision = "0036_rds_reservation_coverage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column(
            "cloud_account_id",
            sa.Integer(),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("native_account_id", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.String(length=2048), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("native_resource_type", sa.String(length=255), nullable=True),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("availability_zone", sa.String(length=160), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=64), nullable=False),
        sa.Column("native_status", sa.String(length=120), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("presence_status", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "first_seen_collection_run_id",
            sa.String(length=36),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_seen_collection_run_id",
            sa.String(length=36),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "cloud_account_id",
            "resource_type",
            "resource_id",
            name="uq_inventory_resources_identity",
        ),
    )
    op.create_index("ix_inventory_resources_provider", "inventory_resources", ["provider"])
    op.create_index(
        "ix_inventory_resources_cloud_account_id", "inventory_resources", ["cloud_account_id"]
    )
    op.create_index(
        "ix_inventory_resources_native_account_id", "inventory_resources", ["native_account_id"]
    )
    op.create_index(
        "ix_inventory_resources_resource_type", "inventory_resources", ["resource_type"]
    )
    op.create_index(
        "ix_inventory_resources_last_seen_at", "inventory_resources", ["last_seen_at"]
    )
    op.create_index(
        "ix_inventory_resources_account_presence_type",
        "inventory_resources",
        ["cloud_account_id", "presence_status", "resource_type"],
    )
    op.create_index(
        "ix_inventory_resources_provider_account_region",
        "inventory_resources",
        ["provider", "cloud_account_id", "region"],
    )
    op.create_index(
        "ix_inventory_resources_account_lifecycle",
        "inventory_resources",
        ["cloud_account_id", "lifecycle_status"],
    )

    op.create_table(
        "inventory_resource_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "inventory_resource_id",
            sa.Integer(),
            sa.ForeignKey("inventory_resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_run_id",
            sa.String(length=36),
            sa.ForeignKey("collection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("native_resource_type", sa.String(length=255), nullable=True),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("availability_zone", sa.String(length=160), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=64), nullable=False),
        sa.Column("native_status", sa.String(length=120), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "inventory_resource_id",
            "collection_run_id",
            name="uq_inventory_resource_observation_run",
        ),
    )
    op.create_index(
        "ix_inventory_resource_observations_inventory_resource_id",
        "inventory_resource_observations",
        ["inventory_resource_id"],
    )
    op.create_index(
        "ix_inventory_resource_observations_collection_run_id",
        "inventory_resource_observations",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_inventory_observations_resource_observed",
        "inventory_resource_observations",
        ["inventory_resource_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("inventory_resource_observations")
    op.drop_table("inventory_resources")
