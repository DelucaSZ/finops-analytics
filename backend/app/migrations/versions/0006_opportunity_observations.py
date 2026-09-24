"""Add deterministic opportunity identity and per-collection observations."""

import uuid

import sqlalchemy as sa
from alembic import op

from app.services.opportunity_fingerprint import build_opportunity_fingerprint_v1

revision = "0006_opportunity_observations"
down_revision = "0005_collection_runs"
branch_labels = None
depends_on = None


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if name not in {item["name"] for item in inspector.get_indexes(table)}:
        op.create_index(name, table, columns)


def _backfill_fingerprints() -> None:
    bind = op.get_bind()
    findings = sa.table(
        "findings",
        sa.column("id", sa.String()),
        sa.column("account_id", sa.Integer()),
        sa.column("rule_key", sa.String()),
        sa.column("service", sa.String()),
        sa.column("region", sa.String()),
        sa.column("resource_id", sa.String()),
        sa.column("fingerprint", sa.String()),
    )
    accounts = sa.table(
        "aws_accounts",
        sa.column("id", sa.Integer()),
        sa.column("aws_account_id", sa.String()),
    )
    rows = list(
        bind.execute(
            sa.select(
                findings.c.id,
                findings.c.rule_key,
                findings.c.service,
                findings.c.region,
                findings.c.resource_id,
                accounts.c.aws_account_id,
            ).select_from(findings.join(accounts, findings.c.account_id == accounts.c.id))
        ).mappings()
    )
    total = bind.scalar(sa.select(sa.func.count()).select_from(findings)) or 0
    if len(rows) != total:
        raise RuntimeError(
            "Cannot safely backfill opportunity fingerprints: one or more findings "
            "do not resolve to an AWS account"
        )

    generated: dict[str, str] = {}
    updates: list[dict[str, str]] = []
    for row in rows:
        fingerprint = build_opportunity_fingerprint_v1(
            provider="aws",
            account_id=row["aws_account_id"],
            region=row["region"],
            scope=row["service"],
            resource_id=row["resource_id"],
            rule_id=row["rule_key"],
        )
        previous = generated.get(fingerprint)
        if previous is not None and previous != row["id"]:
            raise RuntimeError(
                "Cannot safely backfill opportunity fingerprints: deterministic identity collision"
            )
        generated[fingerprint] = row["id"]
        updates.append({"finding_id": row["id"], "new_fingerprint": fingerprint})

    if updates:
        statement = (
            sa.update(findings)
            .where(findings.c.id == sa.bindparam("finding_id"))
            .values(fingerprint=sa.bindparam("new_fingerprint"))
        )
        bind.execute(statement, updates)


def _backfill_observations() -> None:
    bind = op.get_bind()
    findings = sa.table(
        "findings",
        sa.column("id", sa.String()),
        sa.column("scan_id", sa.String()),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("severity", sa.String()),
        sa.column("current_monthly_cost", sa.Numeric(14, 2)),
        sa.column("estimated_monthly_savings", sa.Numeric(14, 2)),
        sa.column("confidence", sa.String()),
        sa.column("evidence", sa.JSON()),
    )
    runs = sa.table(
        "collection_runs",
        sa.column("id", sa.String()),
        sa.column("scan_id", sa.String()),
    )
    observations = sa.table(
        "opportunity_observations",
        sa.column("id", sa.String()),
        sa.column("opportunity_id", sa.String()),
        sa.column("collection_run_id", sa.String()),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("severity", sa.String()),
        sa.column("current_monthly_cost", sa.Numeric(14, 2)),
        sa.column("estimated_monthly_savings", sa.Numeric(14, 2)),
        sa.column("confidence", sa.String()),
        sa.column("evidence", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = list(
        bind.execute(
            sa.select(
                findings.c.id.label("opportunity_id"),
                runs.c.id.label("collection_run_id"),
                findings.c.last_seen_at,
                findings.c.severity,
                findings.c.current_monthly_cost,
                findings.c.estimated_monthly_savings,
                findings.c.confidence,
                findings.c.evidence,
            ).select_from(findings.join(runs, findings.c.scan_id == runs.c.scan_id))
        ).mappings()
    )
    if not rows:
        return

    bind.execute(
        observations.insert(),
        [
            {
                "id": str(uuid.uuid4()),
                "opportunity_id": row["opportunity_id"],
                "collection_run_id": row["collection_run_id"],
                "observed_at": row["last_seen_at"],
                "severity": row["severity"],
                "current_monthly_cost": row["current_monthly_cost"],
                "estimated_monthly_savings": row["estimated_monthly_savings"],
                "confidence": row["confidence"],
                "evidence": row["evidence"],
                "created_at": row["last_seen_at"],
                "updated_at": row["last_seen_at"],
            }
            for row in rows
        ],
    )


def upgrade():
    op.create_table(
        "opportunity_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("collection_run_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("current_monthly_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estimated_monthly_savings", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["findings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id",
            "collection_run_id",
            name="uq_opportunity_observation_run",
        ),
    )
    op.create_index(
        "ix_opportunity_observations_collection_run_id",
        "opportunity_observations",
        ["collection_run_id"],
    )
    op.create_index(
        "ix_opportunity_observations_observed_at",
        "opportunity_observations",
        ["observed_at"],
    )
    _create_index_if_missing("ix_findings_last_seen_at", "findings", ["last_seen_at"])

    _backfill_fingerprints()
    _backfill_observations()


def downgrade():
    raise RuntimeError("Opportunity observation history must be preserved; do not downgrade")
