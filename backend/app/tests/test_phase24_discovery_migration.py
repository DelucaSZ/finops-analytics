from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alembic import command
from sqlalchemy import MetaData, Table, select

from app.db.migrations import migration_config
from app.tests.test_migrations import migration_engine  # noqa: F401


NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _finding(opportunity_id: str) -> dict:
    return {
        "id": opportunity_id,
        "fingerprint": (opportunity_id.encode().hex() * 64)[:64],
        "scan_id": None,
        "provider": "aws",
        "account_id": "111111111111",
        "rule_key": "ebs_unattached",
        "service": "EC2",
        "region": "sa-east-1",
        "resource_id": f"vol-{opportunity_id}",
        "resource_name": opportunity_id,
        "resource_type": "Volume",
        "provider_metadata": {},
        "title": "Migration backfill",
        "description": "Migration backfill",
        "evidence": {},
        "current_monthly_cost": Decimal("10"),
        "estimated_monthly_savings": Decimal("5"),
        "currency": "USD",
        "confidence": "high",
        "severity": "medium",
        "status": "open",
        "presence_status": "active",
        "missing_count": 0,
        "total_occurrence_count": 3,
        "first_seen_at": NOW,
        "last_seen_at": NOW + timedelta(days=2),
        "needs_review": False,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _run(run_id: str, started_at: datetime) -> dict:
    return {
        "id": run_id,
        "scan_id": None,
        "provider": "aws",
        "account_id": "111111111111",
        "scope": {},
        "started_at": started_at,
        "finished_at": started_at + timedelta(minutes=1),
        "status": "SUCCESS",
        "resources_analyzed": 1,
        "opportunities_found": 1,
        "detailed_observations_available": True,
        "analyzer_version": "phase24-test",
        "error_detail": None,
        "created_at": started_at,
        "updated_at": started_at,
    }


def _observation(
    observation_id: str,
    opportunity_id: str,
    run_id: str,
    observed_at: datetime,
) -> dict:
    return {
        "id": observation_id,
        "opportunity_id": opportunity_id,
        "collection_run_id": run_id,
        "observed_at": observed_at,
        "severity": "medium",
        "current_monthly_cost": Decimal("10"),
        "estimated_monthly_savings": Decimal("5"),
        "currency": "USD",
        "confidence": "high",
        "provider_metadata": {},
        "evidence": {},
        "created_at": observed_at,
        "updated_at": observed_at,
    }


def test_discovery_run_backfill_is_deterministic_and_does_not_invent_history(
    migration_engine,  # noqa: F811
):
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0033_opportunity_policy")

        metadata = MetaData()
        findings = Table("findings", metadata, autoload_with=connection)
        runs = Table("collection_runs", metadata, autoload_with=connection)
        observations = Table("opportunity_observations", metadata, autoload_with=connection)

        connection.execute(
            findings.insert(),
            [_finding("with-history"), _finding("without-history")],
        )
        connection.execute(
            runs.insert(),
            [
                _run("run-started-first", NOW),
                _run("run-started-second", NOW + timedelta(hours=1)),
                _run("run-started-last", NOW + timedelta(hours=2)),
            ],
        )

        tied_observed_at = NOW + timedelta(days=1)
        connection.execute(
            observations.insert(),
            [
                _observation(
                    "obs-b",
                    "with-history",
                    "run-started-second",
                    tied_observed_at,
                ),
                _observation(
                    "obs-a",
                    "with-history",
                    "run-started-first",
                    tied_observed_at,
                ),
                _observation(
                    "obs-c",
                    "with-history",
                    "run-started-last",
                    NOW + timedelta(hours=12),
                ),
            ],
        )

        command.upgrade(cfg, "0034_opportunity_discovery_runs")

        refreshed = MetaData()
        migrated_findings = Table("findings", refreshed, autoload_with=connection)
        rows = {
            row.id: row
            for row in connection.execute(
                select(
                    migrated_findings.c.id,
                    migrated_findings.c.first_seen_collection_run_id,
                    migrated_findings.c.last_seen_collection_run_id,
                )
            )
        }

        assert rows["with-history"].first_seen_collection_run_id == "run-started-last"
        assert rows["with-history"].last_seen_collection_run_id == "run-started-second"
        assert rows["without-history"].first_seen_collection_run_id is None
        assert rows["without-history"].last_seen_collection_run_id is None
