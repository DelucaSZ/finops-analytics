from datetime import UTC, datetime
from decimal import Decimal

from alembic import command
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, create_engine, select

from app.db.migrations import migration_config
from app.services.opportunity_fingerprint import build_opportunity_fingerprint


def test_stage_one_data_is_backfilled_without_inventing_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stage-one.db'}")
    observed_at = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)

    with engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0005_collection_runs")

        metadata = MetaData()
        metadata.reflect(bind=connection)
        accounts = metadata.tables["aws_accounts"]
        scans = metadata.tables["scans"]
        findings = metadata.tables["findings"]
        runs = metadata.tables["collection_runs"]

        connection.execute(
            accounts.insert().values(
                id=1,
                name="Existing",
                aws_account_id="123456789012",
                role_arn="legacy-role",
                external_id="legacy",
                regions=["sa-east-1"],
                enabled=True,
                is_management_account=False,
                schedule_enabled=False,
                scan_interval_hours=24,
                next_scan_at=None,
                connection_status="connected",
                last_connection_test_at=None,
                last_error=None,
                created_at=observed_at,
                updated_at=observed_at,
            )
        )
        connection.execute(
            scans.insert(),
            [
                {
                    "id": "scan-with-run",
                    "account_id": 1,
                    "status": "completed",
                    "trigger": "manual",
                    "started_at": observed_at,
                    "completed_at": observed_at,
                    "findings_count": 1,
                    "error": None,
                    "created_at": observed_at,
                    "updated_at": observed_at,
                },
                {
                    "id": "scan-before-runs",
                    "account_id": 1,
                    "status": "completed",
                    "trigger": "manual",
                    "started_at": observed_at,
                    "completed_at": observed_at,
                    "findings_count": 1,
                    "error": None,
                    "created_at": observed_at,
                    "updated_at": observed_at,
                },
            ],
        )
        connection.execute(
            runs.insert().values(
                id="run-existing",
                scan_id="scan-with-run",
                provider="aws",
                account_id="123456789012",
                started_at=observed_at,
                finished_at=observed_at,
                status="SUCCESS",
                resources_analyzed=0,
                opportunities_found=1,
                analyzer_version=None,
                error_detail=None,
                created_at=observed_at,
                updated_at=observed_at,
            )
        )
        common = {
            "account_id": 1,
            "rule_key": "ec2_stopped_with_ebs",
            "service": "EC2",
            "region": "sa-east-1",
            "resource_name": "test",
            "title": "Existing opportunity",
            "description": "Existing",
            "evidence": {"stopped_days": 14},
            "current_monthly_cost": Decimal("42.00"),
            "estimated_monthly_savings": Decimal("20.00"),
            "confidence": "high",
            "severity": "medium",
            "status": "open",
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "created_at": observed_at,
            "updated_at": observed_at,
        }
        connection.execute(
            findings.insert(),
            [
                {
                    **common,
                    "id": "finding-with-run",
                    "fingerprint": "1" * 64,
                    "scan_id": "scan-with-run",
                    "resource_id": "i-abc",
                },
                {
                    **common,
                    "id": "finding-before-runs",
                    "fingerprint": "2" * 64,
                    "scan_id": "scan-before-runs",
                    "resource_id": "i-def",
                },
            ],
        )

        command.upgrade(cfg, "head")

        refreshed = MetaData()
        refreshed.reflect(bind=connection)
        findings = refreshed.tables["findings"]
        observations = refreshed.tables["opportunity_observations"]

        rows = {
            row.id: row for row in connection.execute(select(findings.c.id, findings.c.fingerprint))
        }
        assert rows["finding-with-run"].fingerprint == build_opportunity_fingerprint(
            provider="aws",
            account_id="123456789012",
            region="sa-east-1",
            scope="EC2",
            resource_id="i-abc",
            rule_id="ec2_stopped_with_ebs",
        )
        assert rows["finding-before-runs"].fingerprint == build_opportunity_fingerprint(
            provider="aws",
            account_id="123456789012",
            region="sa-east-1",
            scope="EC2",
            resource_id="i-def",
            rule_id="ec2_stopped_with_ebs",
        )

        observation_rows = list(connection.execute(select(observations)))
        assert len(observation_rows) == 1
        assert observation_rows[0].opportunity_id == "finding-with-run"
        assert observation_rows[0].collection_run_id == "run-existing"
        assert observation_rows[0].estimated_monthly_savings == Decimal("20.00")
        assert (
            MigrationContext.configure(
                connection,
                opts={"version_table": "deepops_mfa_schema_version"},
            ).get_current_revision()
            == "0006_opportunity_observations"
        )

    engine.dispose()
