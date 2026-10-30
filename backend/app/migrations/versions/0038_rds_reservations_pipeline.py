"""RDS Reservations pipeline operational state.

Revision ID: 0038_rds_reservations_pipeline
Revises: 0037_inventory_domain
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_rds_reservations_pipeline"
down_revision = "0037_inventory_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rds_reservation_coverage_runs",
        sa.Column(
            "pipeline_stage",
            sa.String(length=24),
            nullable=False,
            server_default="coverage",
        ),
    )
    op.add_column(
        "rds_reservation_coverage_runs",
        sa.Column(
            "inventory_status",
            sa.String(length=24),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "rds_reservation_coverage_runs",
        sa.Column(
            "opportunity_status",
            sa.String(length=24),
            nullable=False,
            server_default="NOT_RUN",
        ),
    )
    op.add_column(
        "rds_reservation_coverage_runs",
        sa.Column("inventory_error_detail", sa.Text(), nullable=True),
    )
    op.add_column(
        "rds_reservation_coverage_runs",
        sa.Column("opportunity_error_detail", sa.Text(), nullable=True),
    )

    # Historical completed coverage runs remain valid analytical snapshots. Their
    # pre-pipeline inventory/opportunity stage state is intentionally UNKNOWN.
    op.execute(
        "UPDATE rds_reservation_coverage_runs "
        "SET pipeline_stage = 'completed' "
        "WHERE status = 'COMPLETED'"
    )
    op.execute(
        "UPDATE rds_reservation_coverage_runs "
        "SET pipeline_stage = 'coverage' "
        "WHERE status = 'FAILED'"
    )


def downgrade() -> None:
    op.drop_column("rds_reservation_coverage_runs", "opportunity_error_detail")
    op.drop_column("rds_reservation_coverage_runs", "inventory_error_detail")
    op.drop_column("rds_reservation_coverage_runs", "opportunity_status")
    op.drop_column("rds_reservation_coverage_runs", "inventory_status")
    op.drop_column("rds_reservation_coverage_runs", "pipeline_stage")
