import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import worker
from app.db.base import Base
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.scan import Scan
from app.services.collector_types import CollectedFinding


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'collection-runs.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def account() -> AwsAccount:
    return AwsAccount(
        name="Test",
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/DeepOps",
        external_id="test",
        regions=["sa-east-1"],
    )


def queued_scan(db: Session) -> Scan:
    aws_account = account()
    db.add(aws_account)
    db.commit()
    scan = Scan(account_id=aws_account.id)
    db.add(scan)
    db.commit()
    return scan


def test_claim_creates_running_collection_run(db):
    scan = queued_scan(db)

    claimed = worker.claim_scan(db)

    assert claimed is not None and claimed.id == scan.id
    run = db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan.id))
    assert run is not None
    assert run.provider == "aws"
    assert run.account_id == "123456789012"
    assert run.status == CollectionRunStatus.RUNNING
    assert run.started_at is not None
    assert run.finished_at is None


def test_successful_scan_finishes_collection_run(db, monkeypatch):
    scan = queued_scan(db)
    claimed = worker.claim_scan(db)
    assert claimed is not None

    monkeypatch.setattr(worker, "assume_account_session", lambda _: object())
    monkeypatch.setattr(
        worker,
        "get_caller_identity",
        lambda _: type("Identity", (), {"account_id": "123456789012"})(),
    )
    monkeypatch.setattr(
        worker,
        "list_effective_policies",
        lambda *_: [{"rule_key": "test_rule", "enabled": True, "implemented": True}],
    )
    finding = CollectedFinding(
        rule_key="test_rule",
        service="EC2",
        region="sa-east-1",
        resource_id="i-123",
        resource_name="test",
        title="Test",
        description="Test",
        evidence={},
        current_monthly_cost=0,
        estimated_monthly_savings=0,
        confidence="high",
        severity="low",
    )
    monkeypatch.setattr(worker, "run_collectors", lambda *_: ([finding], [], set()))

    worker.execute_scan(db, claimed)

    run = db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan.id))
    assert run is not None
    assert run.status == CollectionRunStatus.SUCCESS
    assert run.finished_at is not None
    assert run.opportunities_found == 1
    assert run.resources_analyzed == 0
    assert db.get(Scan, scan.id).status == "completed"


def test_failed_scan_is_not_left_running(db):
    scan = queued_scan(db)
    claimed = worker.claim_scan(db)
    assert claimed is not None

    worker.fail_scan(db, claimed.id, RuntimeError("collector exploded"))

    run = db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan.id))
    assert run is not None
    assert run.status == CollectionRunStatus.FAILED
    assert run.finished_at is not None
    assert run.error_detail == "collector exploded"
    failed_scan = db.get(Scan, scan.id)
    assert failed_scan.status == "failed"
    assert failed_scan.completed_at is not None
