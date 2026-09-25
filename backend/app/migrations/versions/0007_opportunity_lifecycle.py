"""Redesign opportunity lifecycle with human decision audit history."""

import sqlalchemy as sa
from alembic import op

revision = "0007_opportunity_lifecycle"
down_revision = "0006_opportunity_observations"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("findings") as batch:
        batch.add_column(
            sa.Column("treated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("treated_by", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("treatment_note", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("rejected_by", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("rejection_reason", sa.String(length=32), nullable=True)
        )
        batch.add_column(sa.Column("rejection_note", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "needs_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_foreign_key(
            "fk_findings_treated_by_users",
            "users",
            ["treated_by"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_findings_rejected_by_users",
            "users",
            ["rejected_by"],
            ["id"],
        )
        batch.create_index("ix_findings_treated_at", ["treated_at"])
        batch.create_index("ix_findings_rejected_at", ["rejected_at"])

    bind = op.get_bind()
    findings = sa.table("findings", sa.column("status", sa.String()))
    bind.execute(
        findings.update().values(
            status=sa.case(
                (findings.c.status == "accepted", "treated"),
                (findings.c.status == "dismissed", "rejected"),
                (findings.c.status == "resolved", "open"),
                else_=findings.c.status,
            )
        )
    )

    op.create_table(
        "opportunity_status_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["findings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_status_history_opportunity_id",
        "opportunity_status_history",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_opportunity_status_history_changed_by",
        "opportunity_status_history",
        ["changed_by"],
    )
    op.create_index(
        "ix_opportunity_status_history_changed_at",
        "opportunity_status_history",
        ["changed_at"],
    )


def downgrade():
    raise RuntimeError("Opportunity decision history must be preserved; do not downgrade")
