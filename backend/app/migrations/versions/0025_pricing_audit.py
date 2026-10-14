"""pricing audit trail

Revision ID: 0025_pricing_audit
Revises: 0024_pricing_catalog
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_pricing_audit"
down_revision = "0024_pricing_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pricing_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pricing_item_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATED', 'PRICE_CHANGED', 'METADATA_CHANGED', 'DEACTIVATED', "
            "'REACTIVATED', 'FUTURE_VERSION_CREATED', 'VALIDITY_CHANGED', 'IMPORTED')",
            name="ck_pricing_audit_action",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM')",
            name="ck_pricing_audit_actor_type",
        ),
        sa.ForeignKeyConstraint(
            ["pricing_item_id"],
            ["pricing_catalog_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pricing_audit_key_occurred",
        "pricing_audit_events",
        ["provider", "service", "sku", "unit", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_pricing_audit_item_occurred",
        "pricing_audit_events",
        ["pricing_item_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_pricing_audit_actor", "pricing_audit_events", ["actor_id"], unique=False)
    op.create_index("ix_pricing_audit_action", "pricing_audit_events", ["action"], unique=False)

    # Deliberately no retroactive audit rows are fabricated for 23.7 seed data.
    # Those rows retain source=IMPORTED_OCI_CALCULATOR and auditing starts with
    # administrative mutations performed after this migration is deployed.


def downgrade() -> None:
    op.drop_index("ix_pricing_audit_action", table_name="pricing_audit_events")
    op.drop_index("ix_pricing_audit_actor", table_name="pricing_audit_events")
    op.drop_index("ix_pricing_audit_item_occurred", table_name="pricing_audit_events")
    op.drop_index("ix_pricing_audit_key_occurred", table_name="pricing_audit_events")
    op.drop_table("pricing_audit_events")
