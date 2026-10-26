"""RDS Reserved DB Instance coverage engine persistence.

Revision ID: 0036_rds_reservation_coverage
Revises: 0035_rds_reservation_inventory
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_rds_reservation_coverage"
down_revision = "0035_rds_reservation_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "aws_rds_instances",
        sa.Column("deployment_topology", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "aws_rds_instances",
        sa.Column("cluster_storage_type", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "rds_reservation_coverage_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inventory_snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("accounts_analyzed", sa.Integer(), nullable=False),
        sa.Column("instances_analyzed", sa.Integer(), nullable=False),
        sa.Column("reservations_analyzed", sa.Integer(), nullable=False),
        sa.Column("fully_covered", sa.Integer(), nullable=False),
        sa.Column("partially_covered", sa.Integer(), nullable=False),
        sa.Column("uncovered", sa.Integer(), nullable=False),
        sa.Column("unknown", sa.Integer(), nullable=False),
        sa.Column("required_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("covered_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("uncovered_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("reserved_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("allocated_reserved_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("unused_reserved_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("calculated_coverage_percentage", sa.Numeric(12, 6), nullable=False),
        sa.Column("aws_observed_coverage_percentage", sa.Numeric(12, 6), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=24), nullable=False),
        sa.Column("reconciliation_detail", sa.Text(), nullable=True),
        sa.Column("billing_validation_status", sa.String(length=24), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rds_reservation_coverage_runs_status",
        "rds_reservation_coverage_runs",
        ["status"],
    )

    op.create_table(
        "rds_instance_reservation_coverage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "coverage_run_id",
            sa.Integer(),
            sa.ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rds_instance_id",
            sa.Integer(),
            sa.ForeignKey("aws_rds_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("required_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("covered_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("uncovered_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("coverage_percentage", sa.Numeric(12, 6), nullable=False),
        sa.Column("coverage_status", sa.String(length=24), nullable=False),
        sa.Column("coverage_scope", sa.String(length=32), nullable=False),
        sa.Column("calculation_method", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "coverage_run_id", "rds_instance_id", name="uq_rds_instance_coverage_run_instance"
        ),
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_coverage_run_id",
        "rds_instance_reservation_coverage",
        ["coverage_run_id"],
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_rds_instance_id",
        "rds_instance_reservation_coverage",
        ["rds_instance_id"],
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_account_id",
        "rds_instance_reservation_coverage",
        ["account_id"],
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_region",
        "rds_instance_reservation_coverage",
        ["region"],
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_coverage_status",
        "rds_instance_reservation_coverage",
        ["coverage_status"],
    )
    op.create_index(
        "ix_rds_instance_reservation_coverage_coverage_scope",
        "rds_instance_reservation_coverage",
        ["coverage_scope"],
    )
    op.create_index(
        "ix_rds_instance_coverage_run_status",
        "rds_instance_reservation_coverage",
        ["coverage_run_id", "coverage_status"],
    )
    op.create_index(
        "ix_rds_instance_coverage_account_region",
        "rds_instance_reservation_coverage",
        ["account_id", "region"],
    )

    op.create_table(
        "rds_reservation_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "coverage_run_id",
            sa.Integer(),
            sa.ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reservation_id",
            sa.Integer(),
            sa.ForeignKey("aws_rds_reserved_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rds_instance_id",
            sa.Integer(),
            sa.ForeignKey("aws_rds_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("allocated_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("allocation_percentage", sa.Numeric(12, 6), nullable=False),
        sa.Column("match_type", sa.String(length=24), nullable=False),
        sa.Column("allocation_scope", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "coverage_run_id",
            "reservation_id",
            "rds_instance_id",
            "match_type",
            name="uq_rds_reservation_allocation",
        ),
    )
    op.create_index(
        "ix_rds_reservation_allocations_coverage_run_id",
        "rds_reservation_allocations",
        ["coverage_run_id"],
    )
    op.create_index(
        "ix_rds_reservation_allocations_reservation_id",
        "rds_reservation_allocations",
        ["reservation_id"],
    )
    op.create_index(
        "ix_rds_reservation_allocations_rds_instance_id",
        "rds_reservation_allocations",
        ["rds_instance_id"],
    )
    op.create_index(
        "ix_rds_reservation_alloc_run_reservation",
        "rds_reservation_allocations",
        ["coverage_run_id", "reservation_id"],
    )
    op.create_index(
        "ix_rds_reservation_alloc_run_instance",
        "rds_reservation_allocations",
        ["coverage_run_id", "rds_instance_id"],
    )

    op.create_table(
        "rds_reservation_utilization",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "coverage_run_id",
            sa.Integer(),
            sa.ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reservation_id",
            sa.Integer(),
            sa.ForeignKey("aws_rds_reserved_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("total_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("allocated_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("unused_units", sa.Numeric(24, 6), nullable=False),
        sa.Column("utilization_percentage", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "coverage_run_id", "reservation_id", name="uq_rds_reservation_utilization_run"
        ),
    )
    op.create_index(
        "ix_rds_reservation_utilization_coverage_run_id",
        "rds_reservation_utilization",
        ["coverage_run_id"],
    )
    op.create_index(
        "ix_rds_reservation_utilization_reservation_id",
        "rds_reservation_utilization",
        ["reservation_id"],
    )
    op.create_index(
        "ix_rds_reservation_util_run_reservation",
        "rds_reservation_utilization",
        ["coverage_run_id", "reservation_id"],
    )


def downgrade() -> None:
    op.drop_table("rds_reservation_utilization")
    op.drop_table("rds_reservation_allocations")
    op.drop_table("rds_instance_reservation_coverage")
    op.drop_table("rds_reservation_coverage_runs")
    op.drop_column("aws_rds_instances", "cluster_storage_type")
    op.drop_column("aws_rds_instances", "deployment_topology")
