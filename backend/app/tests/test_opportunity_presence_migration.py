import os
import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

from app.db.migrations import migration_config


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'presence-migration.db'}")
        yield engine
        engine.dispose()
        return

    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise real PostgreSQL transactions")
    schema = "presence_" + uuid.uuid4().hex
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


def test_presence_migration_backfills_active_without_external_resolution(
    migration_engine,
):
    now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0018_cloud_account_scheduling")

        metadata = MetaData()
        findings = Table("findings", metadata, autoload_with=connection)
        runs = Table("collection_runs", metadata, autoload_with=connection)
        observations = Table("opportunity_observations", metadata, autoload_with=connection)

        connection.execute(
            runs.insert().values(
                id="presence-run",
                scan_id=None,
                provider="aws",
                account_id="123456789012",
                scope={"regions": ["sa-east-1"]},
                started_at=now,
                finished_at=now,
                status="SUCCESS",
                resources_analyzed=1,
                opportunities_found=2,
                detailed_observations_available=True,
                analyzer_version="migration-test",
                error_detail=None,
                created_at=now,
                updated_at=now,
            )
        )

        common = {
            "scan_id": None,
            "provider": "aws",
            "account_id": "123456789012",
            "rule_key": "ebs_unattached",
            "service": "EC2",
            "region": "sa-east-1",
            "resource_name": "legacy-volume",
            "resource_type": "EBS Volume",
            "provider_metadata": {"legacy": True},
            "title": "Legacy opportunity",
            "description": "Must survive the presence migration",
            "evidence": {"state": "available"},
            "current_monthly_cost": 10,
            "estimated_monthly_savings": 10,
            "currency": "USD",
            "confidence": "high",
            "severity": "medium",
            "total_occurrence_count": 1,
            "first_seen_at": now,
            "last_seen_at": now,
            "needs_review": False,
            "created_at": now,
            "updated_at": now,
        }
        connection.execute(
            findings.insert(),
            [
                {
                    **common,
                    "id": "legacy-treated",
                    "fingerprint": "a" * 64,
                    "resource_id": "vol-treated",
                    "status": "treated",
                    "treated_at": now,
                    "treated_by": None,
                    "treatment_note": "preserve treatment",
                    "rejected_at": None,
                    "rejected_by": None,
                    "rejection_reason": None,
                    "rejection_note": None,
                },
                {
                    **common,
                    "id": "legacy-rejected",
                    "fingerprint": "b" * 64,
                    "resource_id": "vol-rejected",
                    "status": "rejected",
                    "treated_at": None,
                    "treated_by": None,
                    "treatment_note": None,
                    "rejected_at": now,
                    "rejected_by": None,
                    "rejection_reason": "RESOURCE_REQUIRED",
                    "rejection_note": "preserve rejection",
                },
            ],
        )
        connection.execute(
            observations.insert().values(
                id="legacy-observation",
                opportunity_id="legacy-treated",
                collection_run_id="presence-run",
                observed_at=now,
                severity="medium",
                current_monthly_cost=10,
                estimated_monthly_savings=10,
                currency="USD",
                confidence="high",
                provider_metadata={"legacy": True},
                evidence={"state": "available"},
                created_at=now,
                updated_at=now,
            )
        )

        command.upgrade(cfg, "0019_opportunity_presence")

        migrated = Table("findings", MetaData(), autoload_with=connection)
        migrated_observations = Table(
            "opportunity_observations", MetaData(), autoload_with=connection
        )
        rows = {
            row.id: row
            for row in connection.execute(
                select(migrated).where(migrated.c.id.in_(["legacy-treated", "legacy-rejected"]))
            )
        }

        assert rows["legacy-treated"].status == "treated"
        assert rows["legacy-treated"].treated_at is not None
        assert rows["legacy-treated"].treatment_note == "preserve treatment"
        assert rows["legacy-rejected"].status == "rejected"
        assert rows["legacy-rejected"].rejected_at is not None
        assert rows["legacy-rejected"].rejection_reason == "RESOURCE_REQUIRED"
        assert rows["legacy-rejected"].rejection_note == "preserve rejection"
        assert {row.presence_status for row in rows.values()} == {"active"}
        assert all(row.missing_since_at is None for row in rows.values())
        assert all(row.resolved_externally_at is None for row in rows.values())
        assert all(
            row.first_seen_at is not None and row.last_seen_at is not None
            for row in rows.values()
        )

        observation = connection.execute(select(migrated_observations)).one()
        assert observation.id == "legacy-observation"
        assert observation.opportunity_id == "legacy-treated"
        assert observation.evidence == {"state": "available"}

        column_names = {
            column["name"] for column in inspect(connection).get_columns("findings")
        }
        assert "presence_status" in column_names
        assert connection.scalar(text("SELECT version_num FROM deepops_mfa_schema_version")) == (
            "0019_opportunity_presence"
        )
