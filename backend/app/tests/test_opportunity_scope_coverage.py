from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import AwsAccount, CloudAccount
from app.models.collection_run import CollectionRun
from app.models.collection_scope_execution import CollectionScopeExecutionStatus
from app.services.opportunity_reconciliation import build_collection_scope_executions

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine():
    database = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(database)
    yield database
    database.dispose()


def _run(
    db: Session,
    *,
    provider: str,
    account_id: str,
    regions: list[str],
    suffix: str,
) -> CollectionRun:
    run = CollectionRun(
        id=f"run-{suffix}",
        provider=provider,
        account_id=account_id,
        scope={"regions": regions},
        started_at=START,
        status="RUNNING",
    )
    db.add(run)
    db.flush()
    return run


def test_aws_zero_result_success_records_authoritative_rule_region_coverage(engine):
    with Session(engine) as db:
        aws = AwsAccount(
            name="Coverage AWS",
            aws_account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/DeepOps",
            external_id="coverage",
            regions=["us-east-1", "us-west-2"],
        )
        db.add(aws)
        db.flush()
        cloud = aws.cloud_account
        run = _run(
            db,
            provider="aws",
            account_id=aws.aws_account_id,
            regions=["us-east-1", "us-west-2"],
            suffix="aws-zero",
        )
        result = SimpleNamespace(
            findings=[],
            active_rule_keys=["ebs_unattached"],
            collector_errors=[],
            resources_analyzed=0,
        )

        rows = build_collection_scope_executions(
            db,
            cloud,
            run,
            result,
            finished_at=START + timedelta(minutes=1),
        )
        ebs_rows = [row for row in rows if row.rule_key == "ebs_unattached"]

        assert {(row.region, row.status) for row in ebs_rows} == {
            ("us-east-1", CollectionScopeExecutionStatus.SUCCESS.value),
            ("us-west-2", CollectionScopeExecutionStatus.SUCCESS.value),
        }


def test_aws_partial_rule_failure_only_invalidates_failed_region(engine):
    with Session(engine) as db:
        aws = AwsAccount(
            name="Coverage AWS partial",
            aws_account_id="234567890123",
            role_arn="arn:aws:iam::234567890123:role/DeepOps",
            external_id="coverage-partial",
            regions=["us-east-1", "us-west-2"],
        )
        db.add(aws)
        db.flush()
        cloud = aws.cloud_account
        run = _run(
            db,
            provider="aws",
            account_id=aws.aws_account_id,
            regions=["us-east-1", "us-west-2"],
            suffix="aws-partial",
        )
        result = SimpleNamespace(
            findings=[],
            active_rule_keys=[],
            collector_errors=["ebs_unattached@us-east-1: AccessDenied"],
            resources_analyzed=0,
        )

        rows = build_collection_scope_executions(
            db,
            cloud,
            run,
            result,
            finished_at=START + timedelta(minutes=1),
        )
        ebs = {row.region: row.status for row in rows if row.rule_key == "ebs_unattached"}

        assert ebs["us-east-1"] == CollectionScopeExecutionStatus.FAILED.value
        assert ebs["us-west-2"] == CollectionScopeExecutionStatus.SUCCESS.value


def test_oci_coverage_is_authoritative_only_without_partial_pipeline_issues(engine):
    with Session(engine) as db:
        cloud = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..coverage",
            name="Coverage OCI",
        )
        db.add(cloud)
        db.flush()
        run = _run(
            db,
            provider="oci",
            account_id=cloud.native_account_id,
            regions=["sa-saopaulo-1"],
            suffix="oci",
        )
        clean = SimpleNamespace(
            findings=[],
            active_rule_keys=["oci_block_volume_unattached"],
            collector_errors=[],
            resources_analyzed=0,
        )
        partial = SimpleNamespace(
            findings=[],
            active_rule_keys=["oci_block_volume_unattached"],
            collector_errors=["partial data coverage"],
            resources_analyzed=0,
        )

        clean_rows = build_collection_scope_executions(
            db,
            cloud,
            run,
            clean,
            finished_at=START + timedelta(minutes=1),
        )
        partial_rows = build_collection_scope_executions(
            db,
            cloud,
            run,
            partial,
            finished_at=START + timedelta(minutes=1),
        )

        assert {row.status for row in clean_rows} == {
            CollectionScopeExecutionStatus.SUCCESS.value
        }
        assert {row.status for row in partial_rows} == {
            CollectionScopeExecutionStatus.SKIPPED.value
        }
