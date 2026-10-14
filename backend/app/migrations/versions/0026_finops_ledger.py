"""FinOps financial ledger

Revision ID: 0026_finops_ledger
Revises: 0025_pricing_audit
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_finops_ledger"
down_revision = "0025_pricing_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finops_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entry_type", sa.String(length=24), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("cloud_account_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("source_event_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("periodicity", sa.String(length=16), server_default="ONE_TIME", nullable=False),
        sa.Column("reference_period_start", sa.Date(), nullable=True),
        sa.Column("reference_period_end", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversal_of_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "entry_type IN ('SAVING', 'REALLOCATION', 'ADJUSTMENT')",
            name="ck_finops_ledger_entry_type",
        ),
        sa.CheckConstraint(
            "direction IN ('CREDIT', 'DEBIT')",
            name="ck_finops_ledger_direction",
        ),
        sa.CheckConstraint("amount > 0", name="ck_finops_ledger_amount_positive"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_finops_ledger_currency_iso_code",
        ),
        sa.CheckConstraint(
            "source IN ('OPPORTUNITY', 'MANUAL', 'SYSTEM')",
            name="ck_finops_ledger_source",
        ),
        sa.CheckConstraint(
            "periodicity IN ('ONE_TIME', 'MONTHLY')",
            name="ck_finops_ledger_periodicity",
        ),
        sa.CheckConstraint(
            "reference_period_end IS NULL OR reference_period_start IS NOT NULL",
            name="ck_finops_ledger_reference_period_start_required",
        ),
        sa.CheckConstraint(
            "reference_period_end IS NULL OR reference_period_end >= reference_period_start",
            name="ck_finops_ledger_reference_period_order",
        ),
        sa.CheckConstraint(
            "source != 'OPPORTUNITY' OR "
            "(opportunity_id IS NOT NULL AND source_event_id IS NOT NULL "
            "AND idempotency_key IS NOT NULL)",
            name="ck_finops_ledger_opportunity_source_reference",
        ),
        sa.CheckConstraint(
            "source != 'MANUAL' OR created_by IS NOT NULL",
            name="ck_finops_ledger_manual_actor",
        ),
        sa.CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id != id",
            name="ck_finops_ledger_not_self_reversal",
        ),
        sa.ForeignKeyConstraint(["cloud_account_id"], ["cloud_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_event_id"], ["opportunity_status_history.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["finops_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_finops_ledger_idempotency_key"),
        sa.UniqueConstraint("reversal_of_id", name="uq_finops_ledger_reversal_of"),
    )

    for name, columns in (
        ("ix_finops_ledger_entries_provider", ["provider"]),
        ("ix_finops_ledger_entries_cloud_account_id", ["cloud_account_id"]),
        ("ix_finops_ledger_entries_account_id", ["account_id"]),
        ("ix_finops_ledger_entries_currency", ["currency"]),
        ("ix_finops_ledger_entries_effective_at", ["effective_at"]),
        ("ix_finops_ledger_entries_source", ["source"]),
        ("ix_finops_ledger_entries_opportunity_id", ["opportunity_id"]),
        ("ix_finops_ledger_entries_source_event_id", ["source_event_id"]),
        ("ix_finops_ledger_entries_created_by", ["created_by"]),
        ("ix_finops_ledger_entries_created_at", ["created_at"]),
        ("ix_finops_ledger_currency_effective_at", ["currency", "effective_at"]),
        ("ix_finops_ledger_account_effective_at", ["cloud_account_id", "effective_at"]),
        (
            "ix_finops_ledger_provider_account_effective_at",
            ["provider", "account_id", "effective_at"],
        ),
        ("ix_finops_ledger_type_effective_at", ["entry_type", "effective_at"]),
        ("ix_finops_ledger_source_reference", ["source", "source_reference"]),
    ):
        op.create_index(name, "finops_ledger_entries", columns, unique=False)

    # Financial history begins after deployment. Existing treated opportunities are
    # deliberately not inferred/backfilled as recognized savings.


def downgrade() -> None:
    op.drop_table("finops_ledger_entries")
