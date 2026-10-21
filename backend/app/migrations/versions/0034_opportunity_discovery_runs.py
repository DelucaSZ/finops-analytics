"""opportunity discovery run markers and temporal indexes

Revision ID: 0034_opportunity_discovery_runs
Revises: 0033_opportunity_policy
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_opportunity_discovery_runs"
down_revision = "0033_opportunity_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "first_seen_collection_run_id",
                sa.String(length=36),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "last_seen_collection_run_id",
                sa.String(length=36),
                nullable=True,
            ),
        )
        batch_op.create_foreign_key(
            "fk_findings_first_seen_collection_run_id",
            "collection_runs",
            ["first_seen_collection_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_findings_last_seen_collection_run_id",
            "collection_runs",
            ["last_seen_collection_run_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            """
            UPDATE findings
            SET first_seen_collection_run_id = (
                SELECT oo.collection_run_id
                FROM opportunity_observations AS oo
                JOIN collection_runs AS cr ON cr.id = oo.collection_run_id
                WHERE oo.opportunity_id = findings.id
                ORDER BY oo.observed_at ASC, cr.started_at ASC, oo.id ASC
                LIMIT 1
            )
            WHERE first_seen_collection_run_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM opportunity_observations AS oo
                  WHERE oo.opportunity_id = findings.id
              )
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE findings
            SET last_seen_collection_run_id = (
                SELECT oo.collection_run_id
                FROM opportunity_observations AS oo
                JOIN collection_runs AS cr ON cr.id = oo.collection_run_id
                WHERE oo.opportunity_id = findings.id
                ORDER BY oo.observed_at DESC, cr.started_at DESC, oo.id DESC
                LIMIT 1
            )
            WHERE last_seen_collection_run_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM opportunity_observations AS oo
                  WHERE oo.opportunity_id = findings.id
              )
            """,
        ),
    )

    op.create_index(
        "ix_findings_first_seen_collection_run_id",
        "findings",
        ["first_seen_collection_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_findings_last_seen_collection_run_id",
        "findings",
        ["last_seen_collection_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_findings_provider_account_first_seen",
        "findings",
        ["provider", "account_id", "first_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_findings_status_archived_first_seen",
        "findings",
        ["status", "archived_at", "first_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_findings_status_archived_first_seen",
        table_name="findings",
    )
    op.drop_index(
        "ix_findings_provider_account_first_seen",
        table_name="findings",
    )
    op.drop_index(
        "ix_findings_last_seen_collection_run_id",
        table_name="findings",
    )
    op.drop_index(
        "ix_findings_first_seen_collection_run_id",
        table_name="findings",
    )

    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_constraint(
            "fk_findings_last_seen_collection_run_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_findings_first_seen_collection_run_id",
            type_="foreignkey",
        )
        batch_op.drop_column("last_seen_collection_run_id")
        batch_op.drop_column("first_seen_collection_run_id")
