"""Add controlled historical-retention metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0013_historical_retention"
down_revision = "0012_dashboard_summaries"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "findings",
        sa.Column(
            "total_occurrence_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "collection_runs",
        sa.Column(
            "detailed_observations_available",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE findings
            SET total_occurrence_count = (
                SELECT COUNT(*)
                FROM opportunity_observations
                WHERE opportunity_observations.opportunity_id = findings.id
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE collection_runs
            SET detailed_observations_available = CASE
                WHEN opportunities_found = (
                    SELECT COUNT(*)
                    FROM opportunity_observations
                    WHERE opportunity_observations.collection_run_id = collection_runs.id
                )
                THEN TRUE
                ELSE FALSE
            END
            """
        )
    )


def downgrade():
    raise RuntimeError(
        "Retention metadata preserves historical semantics; do not downgrade"
    )
