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
        engine = create_engine(f"sqlite:///{tmp_path / 'archive-migration.db'}")
        yield engine
        engine.dispose()
        return

    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise real PostgreSQL transactions")
    schema = "archive_" + uuid.uuid4().hex
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


def test_archiving_migration_preserves_existing_findings_as_not_archived(migration_engine):
    now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    with migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0021_opportunity_presence_audit")

        findings = Table("findings", MetaData(), autoload_with=connection)
        connection.execute(
            findings.insert().values(
                id="archive-migration-finding",
                fingerprint="a" * 64,
                scan_id=None,
                provider="aws",
                account_id="123456789012",
                rule_key="ebs_unattached",
                service="EC2",
                region="sa-east-1",
                resource_id="vol-archive-migration",
                resource_name="volume",
                resource_type="EBS Volume",
                provider_metadata={},
                title="Preserved opportunity",
                description="Must survive archive migration",
                evidence={"state": "available"},
                current_monthly_cost=10,
                estimated_monthly_savings=10,
                currency="USD",
                confidence="high",
                severity="medium",
                status="treated",
                presence_status="resolved_externally",
                missing_count=2,
                missing_since_at=now,
                resolved_externally_at=now,
                presence_reconciled_run_id=None,
                presence_reconciled_at=now,
                total_occurrence_count=3,
                first_seen_at=now,
                last_seen_at=now,
                treated_at=now,
                treated_by=None,
                treatment_note="preserve treatment",
                rejected_at=None,
                rejected_by=None,
                rejection_reason=None,
                rejection_note=None,
                needs_review=False,
                created_at=now,
                updated_at=now,
            )
        )

        command.upgrade(cfg, "0022_opportunity_archiving")

        migrated = Table("findings", MetaData(), autoload_with=connection)
        row = connection.execute(
            select(migrated).where(migrated.c.id == "archive-migration-finding")
        ).one()
        assert row.status == "treated"
        assert row.presence_status == "resolved_externally"
        assert row.total_occurrence_count == 3
        assert row.treatment_note == "preserve treatment"
        assert row.archived_at is None
        assert row.archived_by is None
        assert row.archive_reason is None

        inspector = inspect(connection)
        assert "opportunity_archive_history" in inspector.get_table_names()
        indexes = {item["name"] for item in inspector.get_indexes("findings")}
        assert "ix_findings_archived_at" in indexes
        assert "ix_findings_status_archived_last_seen" in indexes
        assert connection.scalar(text("SELECT version_num FROM deepops_mfa_schema_version")) == (
            "0022_opportunity_archiving"
        )
