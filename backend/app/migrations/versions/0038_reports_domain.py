"""Reports domain model and persistence foundation.

Revision ID: 0038_reports_domain
Revises: 0037_inventory_domain
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_reports_domain"
down_revision = "0037_inventory_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_created_by", "reports", ["created_by"])
    op.create_index(
        "ix_reports_created_by_created_at", "reports", ["created_by", "created_at"]
    )
    op.create_index(
        "ix_reports_type_created_at", "reports", ["report_type", "created_at"]
    )

    op.create_table(
        "report_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("parameters_snapshot", sa.JSON(), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "requested_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("execution_metadata", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED')",
            name="ck_report_executions_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_report_executions_attempt"),
    )
    op.create_index("ix_report_executions_report_id", "report_executions", ["report_id"])
    op.create_index("ix_report_executions_status", "report_executions", ["status"])
    op.create_index(
        "ix_report_executions_requested_by", "report_executions", ["requested_by"]
    )
    op.create_index(
        "ix_report_executions_report_created",
        "report_executions",
        ["report_id", "created_at"],
    )
    op.create_index(
        "ix_report_executions_status_created",
        "report_executions",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_report_executions_requested_by_created",
        "report_executions",
        ["requested_by", "created_at"],
    )

    op.create_table(
        "report_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_execution_id",
            sa.String(length=36),
            sa.ForeignKey("report_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=2048), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0", name="ck_report_artifacts_size"
        ),
    )
    op.create_index(
        "ix_report_artifacts_report_execution_id",
        "report_artifacts",
        ["report_execution_id"],
    )
    op.create_index("ix_report_artifacts_format", "report_artifacts", ["format"])
    op.create_index(
        "ix_report_artifacts_execution_created",
        "report_artifacts",
        ["report_execution_id", "created_at"],
    )
    op.create_index(
        "ix_report_artifacts_format_created",
        "report_artifacts",
        ["format", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("report_artifacts")
    op.drop_table("report_executions")
    op.drop_table("reports")
