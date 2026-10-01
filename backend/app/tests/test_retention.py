from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.api.routes.opportunities import _ensure_collection_history_available
from app.core.config import Settings
from app.db.base import Base
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.scan import Scan
from app.services.collection_comparison import compare_collection_runs
from app.services.collector_types import CollectedFinding
from app.services.dashboard_aggregation import rebuild_account_summary, summary_matches_source
from app.services.opportunity_fingerprint import build_opportunity_fingerprint
from app.services.retention import cleanup_observations, retention_cutoff, retention_preview

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ACCOUNT_ID = "123456789012"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _run(
    run_id: str,
    when: datetime,
    *,
    provider: str = "aws",
    account_id: str = ACCOUNT_ID,
    status: str = "SUCCESS",
    opportunities_found: int = 1,
    detailed: bool = True,
) -> CollectionRun:
    return CollectionRun(
        id=run_id,
        provider=provider,
        account_id=account_id,
        scope={"regions": ["sa-east-1"]} if provider == "aws" else {},
        started_at=when,
        finished_at=when + timedelta(minutes=1),
        status=status,
        opportunities_found=opportunities_found,
        detailed_observations_available=detailed,
    )


def _finding(
    finding_id: str,
    *,
    provider: str = "aws",
    account_id: str = ACCOUNT_ID,
    resource_id: str | None = None,
    status: str = "open",
    first_seen_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    total_occurrence_count: int = 1,
) -> Finding:
    resource = resource_id or finding_id
    first = first_seen_at or NOW
    last = last_seen_at or first
    fingerprint = build_opportunity_fingerprint(
        provider=provider,
        account_id=account_id,
        region="sa-east-1" if provider == "aws" else None,
        scope="EC2",
        resource_id=resource,
        rule_id="ec2_stopped",
    )
    return Finding(
        id=finding_id,
        fingerprint=fingerprint,
        provider=provider,
        account_id=account_id,
        rule_key="ec2_stopped",
        service="EC2",
        region="sa-east-1" if provider == "aws" else None,
        resource_id=resource,
        title="Test opportunity",
        description="Test",
        evidence={"summary": "current snapshot"},
        current_monthly_cost=Decimal("40"),
        estimated_monthly_savings=Decimal("20"),
        currency="USD",
        confidence="high",
        severity="medium",
        status=status,
        first_seen_at=first,
        last_seen_at=last,
        total_occurrence_count=total_occurrence_count,
    )


def _observation(
    finding: Finding,
    run: CollectionRun,
    when: datetime,
) -> OpportunityObservation:
    return OpportunityObservation(
        opportunity_id=finding.id,
        collection_run_id=run.id,
        observed_at=when,
        severity="medium",
        current_monthly_cost=Decimal("40"),
        estimated_monthly_savings=Decimal("20"),
        currency="USD",
        confidence="high",
        evidence={"summary": f"observed {run.id}"},
    )


def test_invalid_retention_settings_are_rejected():
    with pytest.raises(ValidationError):
        Settings(NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS=0)
    with pytest.raises(ValidationError):
        Settings(NUVEMIQ_RETENTION_BATCH_SIZE=0)
    with pytest.raises(ValidationError):
        Settings(NUVEMIQ_RETENTION_MAX_ROWS_PER_RUN=-1)


def test_cutoff_boundary_and_preview_are_non_destructive(db):
    cutoff = retention_cutoff(days=90, now=NOW)
    assert cutoff == NOW - timedelta(days=90)

    ages = [91, 90, 89]
    for age in ages:
        when = NOW - timedelta(days=age)
        run = _run(f"run-{age}", when, status="FAILED")
        finding = _finding(f"opp-{age}", first_seen_at=when, last_seen_at=when)
        db.add_all([run, finding])
        db.flush()
        db.add(_observation(finding, run, when))
    db.commit()

    preview = retention_preview(db, cutoff=cutoff)
    assert preview.total_observations == 3
    assert preview.observations_before_cutoff == 1
    assert preview.eligible_observations == 1
    assert preview.protected_observations == 0
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 3


def test_cleanup_batches_is_idempotent_and_keeps_occurrence_total(db):
    finding = _finding(
        "opp-batches",
        first_seen_at=NOW - timedelta(days=200),
        last_seen_at=NOW - timedelta(days=150),
        total_occurrence_count=12,
    )
    db.add(finding)
    for index in range(12):
        when = NOW - timedelta(days=200 - index)
        run = _run(f"batch-{index}", when, status="FAILED")
        db.add(run)
        db.flush()
        db.add(_observation(finding, run, when))
    db.commit()

    first = cleanup_observations(
        db,
        cutoff=NOW - timedelta(days=90),
        batch_size=5,
        max_rows=0,
    )
    assert first.eligible_at_start == 12
    assert first.deleted_observations == 12
    assert first.batches == 3
    assert first.collection_runs_marked_partial == 12
    assert first.max_rows_reached is False
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 0
    assert db.get(Finding, finding.id).total_occurrence_count == 12
    assert all(
        run.detailed_observations_available is False for run in db.scalars(select(CollectionRun))
    )

    second = cleanup_observations(
        db,
        cutoff=NOW - timedelta(days=90),
        batch_size=5,
        max_rows=0,
    )
    assert second.deleted_observations == 0
    assert second.batches == 0


@pytest.mark.parametrize("lifecycle_status", ["treated", "rejected"])
def test_cleanup_preserves_decision_identity_and_future_deduplication(
    db,
    lifecycle_status,
):
    account = AwsAccount(
        name="Retention",
        aws_account_id=ACCOUNT_ID,
        role_arn="role",
        external_id="test",
        regions=["sa-east-1"],
    )
    db.add(account)
    db.flush()

    old_time = NOW - timedelta(days=200)
    old_run = _run("old-run", old_time)
    newer_run = _run("newer-run", NOW - timedelta(days=2), opportunities_found=0)
    latest_run = _run("latest-run", NOW - timedelta(days=1), opportunities_found=0)
    finding = _finding(
        "decision-opp",
        resource_id="i-dedupe",
        status=lifecycle_status,
        first_seen_at=old_time,
        last_seen_at=old_time,
        total_occurrence_count=1,
    )
    decision_at = old_time + timedelta(days=1)
    if lifecycle_status == "treated":
        finding.treated_at = decision_at
        finding.treatment_note = "fixed"
        action = "treat"
    else:
        finding.rejected_at = decision_at
        finding.rejection_reason = "RISK_ACCEPTED"
        finding.rejection_note = "accepted"
        action = "reject"
    db.add_all([old_run, newer_run, latest_run, finding])
    db.flush()
    db.add_all(
        [
            _observation(finding, old_run, old_time),
            OpportunityStatusHistory(
                opportunity_id=finding.id,
                from_status="open",
                to_status=lifecycle_status,
                action=action,
                reason="RISK_ACCEPTED" if lifecycle_status == "rejected" else None,
                note="decision note",
                changed_at=decision_at,
            ),
        ]
    )
    db.commit()

    cleanup_observations(
        db,
        cutoff=NOW - timedelta(days=90),
        batch_size=10,
        max_rows=0,
    )
    preserved = db.get(Finding, finding.id)
    assert preserved.status == lifecycle_status
    assert preserved.fingerprint == finding.fingerprint
    assert preserved.first_seen_at.replace(tzinfo=UTC) == old_time
    assert preserved.last_seen_at.replace(tzinfo=UTC) == old_time
    assert preserved.total_occurrence_count == 1
    assert db.scalar(select(func.count()).select_from(OpportunityStatusHistory)) == 1
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 0

    scan = Scan(
        account_id=account.id,
        cloud_account_id=account.cloud_account_id,
        status="running",
        started_at=NOW,
    )
    db.add(scan)
    db.flush()
    new_run = CollectionRun(
        id="new-detection",
        scan_id=scan.id,
        provider="aws",
        account_id=ACCOUNT_ID,
        scope={"regions": ["sa-east-1"]},
        started_at=NOW,
        status="RUNNING",
    )
    db.add(new_run)
    db.flush()
    item = CollectedFinding(
        rule_key="ec2_stopped",
        service="EC2",
        region="sa-east-1",
        resource_id="i-dedupe",
        resource_name="dedupe",
        title="Test opportunity",
        description="Test",
        evidence={"summary": "new detection"},
        current_monthly_cost=Decimal("40"),
        estimated_monthly_savings=Decimal("20"),
        confidence="high",
        severity="medium",
    )
    worker.persist_findings(
        db,
        scan,
        new_run,
        [item],
        ["ec2_stopped"],
        observed_at=NOW,
    )
    db.commit()

    assert db.scalar(select(func.count()).select_from(Finding)) == 1
    preserved = db.get(Finding, finding.id)
    assert preserved.status == lifecycle_status
    assert preserved.total_occurrence_count == 2
    assert preserved.first_seen_at.replace(tzinfo=UTC) == old_time
    assert preserved.last_seen_at.replace(tzinfo=UTC) == NOW
    if lifecycle_status == "treated":
        assert preserved.needs_review is True


def test_expired_collection_detail_is_not_compared_or_listed_as_empty(db):
    baseline = _run(
        "expired-baseline",
        NOW - timedelta(days=200),
        detailed=False,
    )
    target = _run("target", NOW - timedelta(days=1))
    db.add_all([baseline, target])
    db.commit()

    comparison = compare_collection_runs(
        db,
        target,
        baseline=baseline,
        category="NO_LONGER_DETECTED",
        page=1,
        page_size=50,
    )
    assert comparison["available"] is False
    assert comparison["reason"] == "OBSERVATIONS_EXPIRED"
    assert comparison["summary"] is None
    assert comparison["items"] == []

    with pytest.raises(HTTPException) as exc:
        _ensure_collection_history_available(db, baseline.id)
    assert exc.value.status_code == 410
    assert "COLLECTION_OBSERVATIONS_EXPIRED" in str(exc.value.detail)


def test_latest_home_runs_are_protected_while_older_detail_expires(db):
    finding = _finding(
        "home-opp",
        first_seen_at=NOW - timedelta(days=200),
        last_seen_at=NOW - timedelta(days=1),
        total_occurrence_count=3,
    )
    runs = [
        _run("home-old", NOW - timedelta(days=200)),
        _run("home-baseline", NOW - timedelta(days=2)),
        _run("home-target", NOW - timedelta(days=1)),
    ]
    db.add_all([finding, *runs])
    db.flush()
    db.add_all(
        [
            _observation(finding, runs[0], runs[0].started_at),
            _observation(finding, runs[1], runs[1].started_at),
            _observation(finding, runs[2], runs[2].started_at),
        ]
    )
    db.commit()

    rebuild_account_summary(
        db,
        provider="aws",
        account_id=ACCOUNT_ID,
        collection_run_id="home-target",
    )
    db.commit()
    assert summary_matches_source(db, provider="aws", account_id=ACCOUNT_ID)

    result = cleanup_observations(
        db,
        cutoff=NOW - timedelta(days=90),
        batch_size=5,
        max_rows=0,
    )
    assert result.deleted_observations == 1
    assert {item.collection_run_id for item in db.scalars(select(OpportunityObservation))} == {
        "home-baseline",
        "home-target",
    }
    assert db.get(CollectionRun, "home-old").detailed_observations_available is False
    assert db.get(CollectionRun, "home-baseline").detailed_observations_available is True
    assert db.get(CollectionRun, "home-target").detailed_observations_available is True
    assert summary_matches_source(db, provider="aws", account_id=ACCOUNT_ID)


def test_provider_scoped_cleanup_does_not_cross_clouds(db):
    old = NOW - timedelta(days=180)
    aws_run = _run("aws-old", old, provider="aws", status="FAILED")
    oci_run = _run(
        "oci-old",
        old,
        provider="oci",
        account_id="ocid1.tenancy.example",
        status="FAILED",
    )
    aws_finding = _finding("aws-opp", provider="aws", first_seen_at=old, last_seen_at=old)
    oci_finding = _finding(
        "oci-opp",
        provider="oci",
        account_id="ocid1.tenancy.example",
        first_seen_at=old,
        last_seen_at=old,
    )
    db.add_all([aws_run, oci_run, aws_finding, oci_finding])
    db.flush()
    db.add_all(
        [
            _observation(aws_finding, aws_run, old),
            _observation(oci_finding, oci_run, old),
        ]
    )
    db.commit()

    result = cleanup_observations(
        db,
        cutoff=NOW - timedelta(days=90),
        batch_size=10,
        max_rows=0,
        provider="aws",
    )
    assert result.deleted_observations == 1
    remaining = list(db.scalars(select(OpportunityObservation)))
    assert len(remaining) == 1
    assert remaining[0].collection_run_id == "oci-old"
