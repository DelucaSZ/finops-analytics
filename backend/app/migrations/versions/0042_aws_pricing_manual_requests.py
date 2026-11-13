"""Durable manual AWS pricing synchronization requests.

Revision ID: 0042_aws_pricing_manual_requests
Revises: 0041_aws_pricing_sync_runs
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0042_aws_pricing_manual_requests"
down_revision = "0041_aws_pricing_sync_runs"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "aws_pricing_sync_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_code", sa.String(80), nullable=False),
        sa.Column("region_code", sa.String(40), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result", _JSON),
        sa.Column("error_code", sa.String(100)),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_aws_sync_request_status",
        ),
    )
    op.create_index(
        "ix_aws_sync_request_status",
        "aws_pricing_sync_requests",
        ["status", "requested_at"],
    )
    op.create_index(
        "uq_aws_sync_request_active_unit",
        "aws_pricing_sync_requests",
        ["service_code", "region_code"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
        sqlite_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_aws_sync_request_active_unit", table_name="aws_pricing_sync_requests")
    op.drop_index("ix_aws_sync_request_status", table_name="aws_pricing_sync_requests")
    op.drop_table("aws_pricing_sync_requests")
