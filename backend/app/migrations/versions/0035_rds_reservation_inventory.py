"""RDS DB Instance and reservation inventory

Revision ID: 0035_rds_reservation_inventory
Revises: 0034_opportunity_discovery_runs
"""

import sqlalchemy as sa
from alembic import op

revision = "0035_rds_reservation_inventory"
down_revision = "0034_opportunity_discovery_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aws_rds_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "cloud_account_id",
            sa.Integer(),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("db_instance_identifier", sa.String(length=255), nullable=False),
        sa.Column("db_instance_arn", sa.String(length=512), nullable=False),
        sa.Column("db_instance_class", sa.String(length=64), nullable=False),
        sa.Column("class_prefix", sa.String(length=16), nullable=True),
        sa.Column("instance_family", sa.String(length=32), nullable=True),
        sa.Column("instance_size", sa.String(length=32), nullable=True),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("engine_normalized", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=True),
        sa.Column("license_model", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("coverage_eligible", sa.Boolean(), nullable=False),
        sa.Column("multi_az", sa.Boolean(), nullable=False),
        sa.Column("availability_zone", sa.String(length=32), nullable=True),
        sa.Column("secondary_availability_zone", sa.String(length=32), nullable=True),
        sa.Column("storage_type", sa.String(length=32), nullable=True),
        sa.Column("allocated_storage", sa.Integer(), nullable=True),
        sa.Column("iops", sa.Integer(), nullable=True),
        sa.Column("storage_throughput", sa.Integer(), nullable=True),
        sa.Column("publicly_accessible", sa.Boolean(), nullable=True),
        sa.Column("cluster_identifier", sa.String(length=255), nullable=True),
        sa.Column("vpc_id", sa.String(length=64), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("processor_features", sa.JSON(), nullable=False),
        sa.Column("option_group_memberships", sa.JSON(), nullable=False),
        sa.Column("parameter_groups", sa.JSON(), nullable=False),
        sa.Column("aws_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "cloud_account_id",
            "region",
            "db_instance_arn",
            name="uq_aws_rds_instances_account_region_arn",
        ),
    )
    op.create_index(
        "ix_aws_rds_instances_cloud_account_id",
        "aws_rds_instances",
        ["cloud_account_id"],
    )
    op.create_index("ix_aws_rds_instances_account_id", "aws_rds_instances", ["account_id"])
    op.create_index("ix_aws_rds_instances_region", "aws_rds_instances", ["region"])
    op.create_index(
        "ix_aws_rds_instances_engine_normalized", "aws_rds_instances", ["engine_normalized"]
    )
    op.create_index("ix_aws_rds_instances_status", "aws_rds_instances", ["status"])
    op.create_index("ix_aws_rds_instances_is_active", "aws_rds_instances", ["is_active"])
    op.create_index(
        "ix_aws_rds_instances_account_region_active",
        "aws_rds_instances",
        ["cloud_account_id", "region", "is_active"],
    )
    op.create_index(
        "ix_aws_rds_instances_engine_class",
        "aws_rds_instances",
        ["engine_normalized", "db_instance_class"],
    )

    op.create_table(
        "aws_rds_reserved_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "cloud_account_id",
            sa.Integer(),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("reserved_db_instance_id", sa.String(length=255), nullable=False),
        sa.Column("offering_id", sa.String(length=255), nullable=True),
        sa.Column("db_instance_class", sa.String(length=64), nullable=False),
        sa.Column("class_prefix", sa.String(length=16), nullable=True),
        sa.Column("instance_family", sa.String(length=32), nullable=True),
        sa.Column("instance_size", sa.String(length=32), nullable=True),
        sa.Column("product_description", sa.String(length=255), nullable=False),
        sa.Column("engine_normalized", sa.String(length=64), nullable=False),
        sa.Column("instance_count", sa.Integer(), nullable=False),
        sa.Column("multi_az", sa.Boolean(), nullable=False),
        sa.Column("offering_type", sa.String(length=64), nullable=True),
        sa.Column("offering_class", sa.String(length=64), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("fixed_price", sa.String(length=64), nullable=True),
        sa.Column("usage_price", sa.String(length=64), nullable=True),
        sa.Column("recurring_charges", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("lease_id", sa.String(length=255), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("expiration_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "cloud_account_id",
            "region",
            "reserved_db_instance_id",
            name="uq_aws_rds_reserved_account_region_id",
        ),
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_cloud_account_id",
        "aws_rds_reserved_instances",
        ["cloud_account_id"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_account_id",
        "aws_rds_reserved_instances",
        ["account_id"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_region",
        "aws_rds_reserved_instances",
        ["region"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_engine_normalized",
        "aws_rds_reserved_instances",
        ["engine_normalized"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_state",
        "aws_rds_reserved_instances",
        ["state"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_expiration_at",
        "aws_rds_reserved_instances",
        ["expiration_at"],
    )
    op.create_index(
        "ix_aws_rds_reserved_instances_is_active",
        "aws_rds_reserved_instances",
        ["is_active"],
    )
    op.create_index(
        "ix_aws_rds_reserved_account_region_active",
        "aws_rds_reserved_instances",
        ["cloud_account_id", "region", "is_active"],
    )
    op.create_index(
        "ix_aws_rds_reserved_engine_class",
        "aws_rds_reserved_instances",
        ["engine_normalized", "db_instance_class"],
    )


def downgrade() -> None:
    op.drop_table("aws_rds_reserved_instances")
    op.drop_table("aws_rds_instances")
