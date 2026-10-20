"""generic administrative audit events

Revision ID: 0031_audit_events
Revises: 0030_billing_service_default
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_audit_events"
down_revision = "0030_billing_service_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(length=120), nullable=True),
        sa.Column("actor_email_snapshot", sa.String(length=254), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("entity_label", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_created_at",
        "audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor_created_at",
        "audit_events",
        ["actor_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_module_created_at",
        "audit_events",
        ["module", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_action",
        "audit_events",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_entity_created_at",
        "audit_events",
        ["entity_type", "entity_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_module_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
