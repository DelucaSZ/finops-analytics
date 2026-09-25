from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.db.base import Base
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.collector_types import CollectedFinding
from app.services.opportunity_fingerprint import build_opportunity_fingerprint


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opportunities.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def account(db: Session) -> AwsAccount:
    value = AwsAccount(
        name="Test",
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/DeepOps",
        external_id="test",
        regions=["sa-east-1"],
    )
    db.add(value)
    db.commit()
    return value


def collection_run(
    db: Session, aws_account: AwsAccount, *, started_at: datetime
) -> tuple[Scan, CollectionRun]:
    scan = Scan(
        account_id=aws_account.id,
        status="running",
        started_at=started_at,
    )
    db.add(scan)
    db.flush()
    run = CollectionRun(
        scan_id=scan.id,
        provider="aws",
        account_id=aws_account.aws_account_id,
        started_at=started_at,
        status=CollectionRunStatus.RUNNING,
    )
    db.add(run)
    db.commit()
    return scan, run


def normalized_timestamp(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def collected_finding(
    *,
    resource_id: str = "i-abc",
    rule_key: str = "ec2_stopped",
    savings: str = "20.00",
    stopped_days: int = 14,
) -> CollectedFinding:
    return CollectedFinding(
        rule_key=rule_key,
        service="EC2",
        region="sa-east-1",
        resource_id=resource_id,
        resource_name="test",
        title="Test opportunity",
        description="Test",
        evidence={"instance_state": "stopped", "stopped_days": stopped_days},
        current_monthly_cost=Decimal("42.00"),
        estimated_monthly_savings=Decimal(savings),
        confidence="high",
        severity="medium",
    )


def test_fingerprint_is_deterministic_and_changes_with_logical_identity():
    base = {
        "provider": "aws",
        "account_id": "123456789012",
        "region": "sa-east-1",
        "scope": "EC2",
        "resource_id": "i-abc",
        "rule_id": "ec2_stopped",
    }
    first = build_opportunity_fingerprint(**base)
    assert build_opportunity_fingerprint(**base) == first

    for change in (
        {"rule_id": "different_rule"},
        {"resource_id": "i-def"},
        {"account_id": "999999999999"},
    ):
        assert build_opportunity_fingerprint(**(base | change)) != first


def test_two_collection_runs_reuse_opportunity_and_append_observations(db):
    aws_account = account(db)
    first_time = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
    second_time = first_time + timedelta(days=1)

    scan_a, run_a = collection_run(db, aws_account, started_at=first_time)
    worker.persist_findings(
        db,
        scan_a,
        run_a,
        [collected_finding(savings="20.00", stopped_days=14)],
        ["ec2_stopped"],
        observed_at=first_time,
    )
    db.commit()

    opportunity = db.scalar(select(Finding))
    opportunity_id = opportunity.id
    first_seen_at = opportunity.first_seen_at

    scan_b, run_b = collection_run(db, aws_account, started_at=second_time)
    worker.persist_findings(
        db,
        scan_b,
        run_b,
        [collected_finding(savings="35.00", stopped_days=15)],
        ["ec2_stopped"],
        observed_at=second_time,
    )
    db.commit()

    assert db.scalar(select(func.count()).select_from(Finding)) == 1
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 2

    opportunity = db.get(Finding, opportunity_id)
    assert normalized_timestamp(opportunity.first_seen_at) == normalized_timestamp(first_seen_at)
    assert normalized_timestamp(opportunity.last_seen_at) == second_time
    assert opportunity.estimated_monthly_savings == Decimal("35.00")

    observations = list(
        db.scalars(select(OpportunityObservation).order_by(OpportunityObservation.observed_at))
    )
    assert [item.collection_run_id for item in observations] == [run_a.id, run_b.id]
    assert [item.estimated_monthly_savings for item in observations] == [
        Decimal("20.00"),
        Decimal("35.00"),
    ]
    assert [item.evidence["stopped_days"] for item in observations] == [14, 15]


def test_retry_same_collection_run_is_idempotent(db):
    aws_account = account(db)
    first_time = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
    retry_time = first_time + timedelta(minutes=5)
    scan, run = collection_run(db, aws_account, started_at=first_time)

    worker.persist_findings(
        db,
        scan,
        run,
        [collected_finding(savings="20.00", stopped_days=14)],
        ["ec2_stopped"],
        observed_at=first_time,
    )
    db.commit()
    worker.persist_findings(
        db,
        scan,
        run,
        [collected_finding(savings="35.00", stopped_days=15)],
        ["ec2_stopped"],
        observed_at=retry_time,
    )
    db.commit()

    assert db.scalar(select(func.count()).select_from(Finding)) == 1
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 1

    opportunity = db.scalar(select(Finding))
    observation = db.scalar(select(OpportunityObservation))
    assert normalized_timestamp(opportunity.first_seen_at) == first_time
    assert normalized_timestamp(opportunity.last_seen_at) == first_time
    assert opportunity.estimated_monthly_savings == Decimal("35.00")
    assert normalized_timestamp(observation.observed_at) == first_time
    assert observation.estimated_monthly_savings == Decimal("35.00")
    assert observation.evidence["stopped_days"] == 15


def test_different_resource_or_rule_creates_new_opportunity(db):
    aws_account = account(db)
    observed_at = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
    scan, run = collection_run(db, aws_account, started_at=observed_at)

    count = worker.persist_findings(
        db,
        scan,
        run,
        [
            collected_finding(resource_id="i-abc", rule_key="ec2_stopped"),
            collected_finding(resource_id="i-def", rule_key="ec2_stopped"),
            collected_finding(resource_id="i-abc", rule_key="missing_required_tags"),
        ],
        ["ec2_stopped", "missing_required_tags"],
        observed_at=observed_at,
    )
    db.commit()

    assert count == 3
    assert db.scalar(select(func.count()).select_from(Finding)) == 3
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 3


def test_execute_scan_twice_keeps_one_opportunity_and_two_observations(db, monkeypatch):
    aws_account = account(db)
    current_finding = {"value": collected_finding(savings="20.00", stopped_days=14)}

    monkeypatch.setattr(worker, "assume_account_session", lambda _: object())
    monkeypatch.setattr(
        worker,
        "get_caller_identity",
        lambda _: type("Identity", (), {"account_id": aws_account.aws_account_id})(),
    )
    monkeypatch.setattr(
        worker,
        "list_effective_policies",
        lambda *_: [{"rule_key": "ec2_stopped", "enabled": True, "implemented": True}],
    )
    monkeypatch.setattr(
        worker,
        "run_collectors",
        lambda *_: ([current_finding["value"]], [], set()),
    )

    scan_a = Scan(account_id=aws_account.id)
    db.add(scan_a)
    db.commit()
    claimed_a = worker.claim_scan(db)
    assert claimed_a is not None and claimed_a.id == scan_a.id
    worker.execute_scan(db, claimed_a)

    opportunity = db.scalar(select(Finding))
    assert opportunity is not None
    opportunity_id = opportunity.id
    first_seen_at = normalized_timestamp(opportunity.first_seen_at)

    current_finding["value"] = collected_finding(savings="35.00", stopped_days=15)
    scan_b = Scan(account_id=aws_account.id)
    db.add(scan_b)
    db.commit()
    claimed_b = worker.claim_scan(db)
    assert claimed_b is not None and claimed_b.id == scan_b.id
    worker.execute_scan(db, claimed_b)

    assert db.scalar(select(func.count()).select_from(CollectionRun)) == 2
    assert db.scalar(select(func.count()).select_from(Finding)) == 1
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 2

    opportunity = db.get(Finding, opportunity_id)
    assert normalized_timestamp(opportunity.first_seen_at) == first_seen_at
    assert normalized_timestamp(opportunity.last_seen_at) >= first_seen_at
    assert opportunity.scan_id == scan_b.id
    assert opportunity.estimated_monthly_savings == Decimal("35.00")

    runs = list(db.scalars(select(CollectionRun)))
    observations = list(db.scalars(select(OpportunityObservation)))
    assert {item.collection_run_id for item in observations} == {item.id for item in runs}
    assert {item.estimated_monthly_savings for item in observations} == {
        Decimal("20.00"),
        Decimal("35.00"),
    }
    assert all(item.status == CollectionRunStatus.SUCCESS for item in runs)


def test_structured_evidence_is_preserved_independently_per_collection_run(db):
    aws_account = account(db)
    first_time = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
    second_time = first_time + timedelta(days=1)
    scan_a, run_a = collection_run(db, aws_account, started_at=first_time)
    scan_b, run_b = collection_run(db, aws_account, started_at=second_time)

    item_a = collected_finding(savings="20.00", stopped_days=14)
    item_a.evidence = {
        "schema_version": 1,
        "summary": "Parada há 14 dias.",
        "metrics": [
            {
                "key": "stopped_days",
                "label": "Tempo parada",
                "value": 14,
                "unit": "days",
                "kind": "observed",
            }
        ],
        "criteria": [],
        "details": {"state": "stopped"},
        "parameters": {"minimum_stopped_days": 7},
        "rule": {"key": "ec2_stopped", "name": "EC2 parada", "description": "Teste"},
        "source": "AWS inventory",
        "notes": [],
        "contributors": [],
        "evaluated_at": first_time.isoformat(),
    }
    worker.persist_findings(
        db,
        scan_a,
        run_a,
        [item_a],
        ["ec2_stopped"],
        observed_at=first_time,
    )
    db.commit()

    item_b = collected_finding(savings="35.00", stopped_days=15)
    item_b.evidence = {
        **item_a.evidence,
        "summary": "Parada há 15 dias.",
        "metrics": [{**item_a.evidence["metrics"][0], "value": 15}],
        "evaluated_at": second_time.isoformat(),
    }
    worker.persist_findings(
        db,
        scan_b,
        run_b,
        [item_b],
        ["ec2_stopped"],
        observed_at=second_time,
    )
    db.commit()

    observations = list(
        db.scalars(select(OpportunityObservation).order_by(OpportunityObservation.observed_at))
    )
    assert len(observations) == 2
    assert observations[0].collection_run_id == run_a.id
    assert observations[1].collection_run_id == run_b.id
    assert observations[0].evidence["summary"] == "Parada há 14 dias."
    assert observations[0].evidence["metrics"][0]["value"] == 14
    assert observations[1].evidence["summary"] == "Parada há 15 dias."
    assert observations[1].evidence["metrics"][0]["value"] == 15
