from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, select, text

from app.db.migrations import migration_config

BASE = datetime(2026, 10, 1, 12, tzinfo=UTC)


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'discovery-backfill.db'}")
        yield engine
        engine.dispose()
        return

    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise the PostgreSQL migration backfill")

    schema = "test_discovery_" + uuid.uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def _upgrade(connection, revision: str) -> None:
    cfg = migration_config()
    cfg.attributes["connection"] = connection
    cfg.attributes["version_table"] = "deepops_mfa_schema_version"
    command.upgrade(cfg, revision)


def _tables(connection) -> tuple[Table, Table, Table]:
    metadata = MetaData()
    metadata.reflect(bind=connection)
    return (
        metadata.tables["findings"],
        metadata.tables["collection_runs"],
        metadata.tables["opportunity_observations"],
    )


def _run(run_id: str, started_at: datetime) -> dict:
    return {
        "id": run_id,
        "scan_id": None,
        "provider": "aws",
        "account_id": "111111111111",
        "scope": {"regions": ["sa-east-1"]},
        "started_at": started_at,
        "finished_at": started_at + timedelta(minutes=5),
        "status": "SUCCESS",
        "resources_analyzed": 1,
        "opportunities_found": 1,
        "detailed_observations_available": True,
        "analyzer_version": "migration-test",
        "error_detail": None,
        "created_at": started_at,
        "updated_at": started_at,
    }


def _finding(finding_id: str, *, fingerprint: str) -> dict:
    return {
        "id": finding_id,
        "fingerprint": fingerprint,
        "scan_id": None,
        "provider": "aws",
        "account_id": "111111111111",
        "rule_key": "ec2_stopped",
        "service": "EC2",
        "region": "sa-east-1",
        "resource_id": f"i-{finding_id}",
        "resource_name": finding_id,
        "resource_type": "instance",
        "provider_metadata": {},
        "title": finding_id,
        "description": "Task 24.13 migration fixture",
        "evidence": {},
        "current_monthly_cost": Decimal("20.00"),
        "estimated_monthly_savings": Decimal("10.00"),
        "currency": "USD",
        "confidence": "high",
        "severity": "medium",
        "status": "open",
        "presence_status": "active",
        "missing_count": 0,
        "missing_since_at": None,
        "resolved_externally_at": None,
        "presence_reconciled_run_id": None,
        "presence_reconciled_at": None,
        "total_occurrence_count": 1,
        "first_seen_at": BASE,
        "last_seen_at": BASE + timedelta(days=3),
        "treated_at": None,
        "treated_by": None,
        "treatment_note": None,
        "rejected_at": None,
        "rejected_by": None,
        "rejection_reason": None,
        "rejection_note": None,
        "needs_review": False,
        "archived_at": None,
        "archived_by": None,
        "archive_reason": None,
        "created_at": BASE,
        "updated_at": BASE,
    }


def _observation(
    observation_id: str,
    finding_id: str,
    run_id: str,
    observed_at: datetime,
) -> dict:
    return {
        "id": observation_id,
        "opportunity_id": finding_id,
        "collection_run_id": run_id,
        "observed_at": observed_at,
        "severity": "medium",
        "current_monthly_cost": Decimal("20.00"),
        "estimated_monthly_savings": Decimal("10.00"),
        "currency": "USD",
        "confidence": "high",
        "provider_metadata": {},
        "evidence": {},
        "created_at": observed_at,
        "updated_at": observed_at,
    }


def test_0034_backfill_is_deterministic_and_does_not_invent_run_markers(migration_engine):
    with migration_engine.begin() as connection:
        _upgrade(connection, "0033_opportunity_policy")
        findings, runs, observations = _tables(connection)

        connection.execute(
            runs.insert(),
            [
                _run("run-started-first", BASE),
                _run("run-started-second", BASE + timedelta(hours=1)),
                _run("run-started-third", BASE + timedelta(hours=2)),
            ],
        )
        connection.execute(
            findings.insert(),
            [
                _finding("out-of-order", fingerprint="1" * 64),
                _finding("same-timestamp", fingerprint="2" * 64),
                _finding("without-observation", fingerprint="3" * 64),
            ],
        )

        connection.execute(
            observations.insert(),
            [
                # CollectionRun.started_at order intentionally differs from observed_at order.
                _observation(
                    "obs-out-late",
                    "out-of-order",
                    "run-started-first",
                    BASE + timedelta(days=2),
                ),
                _observation(
                    "obs-out-early",
                    "out-of-order",
                    "run-started-third",
                    BASE + timedelta(days=1),
                ),
                # Equal observation timestamps use CollectionRun.started_at
                # as the deterministic tie-break.
                _observation(
                    "obs-same-later-run",
                    "same-timestamp",
                    "run-started-second",
                    BASE + timedelta(days=3),
                ),
                _observation(
                    "obs-same-earlier-run",
                    "same-timestamp",
                    "run-started-first",
                    BASE + timedelta(days=3),
                ),
            ],
        )

        _upgrade(connection, "0034_opportunity_discovery_runs")

        refreshed = MetaData()
        refreshed.reflect(bind=connection)
        migrated_findings = refreshed.tables["findings"]
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

        assert rows["out-of-order"].first_seen_collection_run_id == "run-started-third"
        assert rows["out-of-order"].last_seen_collection_run_id == "run-started-first"
        assert rows["same-timestamp"].first_seen_collection_run_id == "run-started-first"
        assert rows["same-timestamp"].last_seen_collection_run_id == "run-started-second"
        assert rows["without-observation"].first_seen_collection_run_id is None
        assert rows["without-observation"].last_seen_collection_run_id is None


def test_0034_sqlite_legacy_orphan_observation_does_not_invent_run_marker(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-orphan.db'}")
    try:
        with engine.begin() as connection:
            _upgrade(connection, "0033_opportunity_policy")
            findings, _, observations = _tables(connection)
            connection.execute(
                findings.insert(),
                [_finding("legacy-orphan", fingerprint="4" * 64)],
            )
            connection.execute(text("PRAGMA foreign_keys = OFF"))
            connection.execute(
                observations.insert(),
                [
                    _observation(
                        "obs-orphan",
                        "legacy-orphan",
                        "missing-run",
                        BASE,
                    )
                ],
            )

            _upgrade(connection, "0034_opportunity_discovery_runs")

            refreshed = MetaData()
            refreshed.reflect(bind=connection)
            migrated_findings = refreshed.tables["findings"]
            row = connection.execute(
                select(
                    migrated_findings.c.first_seen_collection_run_id,
                    migrated_findings.c.last_seen_collection_run_id,
                ).where(migrated_findings.c.id == "legacy-orphan")
            ).one()
            assert row.first_seen_collection_run_id is None
            assert row.last_seen_collection_run_id is None
    finally:
        engine.dispose()
