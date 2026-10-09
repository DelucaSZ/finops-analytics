from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app import worker
from app.api.routes.findings import router as findings_router
from app.api.routes.opportunities import router as opportunities_router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.collector_types import CollectedFinding

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def environment():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        account = AwsAccount(
            id=1,
            name="Presence test",
            aws_account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/DeepOps",
            external_id="presence-test",
            regions=["sa-east-1"],
        )
        db.add(account)
        db.flush()
        admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash="unused",
            role="admin",
        )
        db.add(admin)
        db.commit()
        _, token = new_session(db, admin)
        db.commit()

    app = FastAPI()
    app.include_router(findings_router)
    app.include_router(opportunities_router)

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as http:
        http.headers.update(
            {
                "Cookie": f"{COOKIE}={token}",
                "X-CSRF-Token": csrf_token(token),
                "X-DeepOps-Request": "1",
            }
        )
        yield http, engine
    engine.dispose()


def _run(db: Session, suffix: str, started_at: datetime) -> tuple[Scan, CollectionRun]:
    account = db.get(AwsAccount, 1)
    scan = Scan(
        id=f"scan-{suffix}",
        account_id=account.id,
        cloud_account_id=account.cloud_account_id,
        status="running",
        started_at=started_at,
    )
    db.add(scan)
    db.flush()
    run = CollectionRun(
        id=f"run-{suffix}",
        scan_id=scan.id,
        provider="aws",
        account_id=account.aws_account_id,
        scope={"regions": ["sa-east-1"]},
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
        status="SUCCESS",
    )
    db.add(run)
    db.flush()
    return scan, run


def _collected() -> CollectedFinding:
    return CollectedFinding(
        rule_key="ebs_unattached",
        service="EC2",
        region="sa-east-1",
        resource_id="vol-presence",
        resource_name="Presence volume",
        resource_type="EBS Volume",
        title="Unattached volume",
        description="Presence lifecycle test",
        evidence={"state": "available"},
        current_monthly_cost=Decimal("25.00"),
        estimated_monthly_savings=Decimal("25.00"),
        currency="USD",
        confidence="high",
        severity="medium",
    )


def _persist(db: Session, suffix: str, observed_at: datetime) -> Finding:
    scan, run = _run(db, suffix, observed_at)
    worker.persist_findings(
        db,
        scan,
        run,
        [_collected()],
        ["ebs_unattached"],
        observed_at=observed_at,
    )
    db.commit()
    return db.scalar(select(Finding))


def test_new_opportunity_starts_open_and_active_with_positive_observation(environment):
    _, engine = environment
    with Session(engine) as db:
        finding = _persist(db, "first", START)
        assert finding.status == "open"
        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_since_at is None
        assert finding.resolved_externally_at is None
        assert finding.total_occurrence_count == 1
        assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 1


def test_real_new_observation_reactivates_presence_without_reopening_human_status(environment):
    _, engine = environment
    with Session(engine) as db:
        finding = _persist(db, "first", START)
        treated_at = START + timedelta(hours=1)
        externally_resolved_at = START + timedelta(hours=2)
        finding.status = "treated"
        finding.treated_at = treated_at
        finding.treatment_note = "handled outside this test"
        finding.presence_status = OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
        finding.resolved_externally_at = externally_resolved_at
        db.commit()

        scan, run = _run(db, "second", START + timedelta(days=1))
        worker.persist_findings(
            db,
            scan,
            run,
            [_collected()],
            ["ebs_unattached"],
            observed_at=START + timedelta(days=1),
        )
        db.commit()

        finding = db.get(Finding, finding.id)
        assert finding.status == "treated"
        treated_at_from_db = finding.treated_at
        assert treated_at_from_db is not None
        if treated_at_from_db.tzinfo is None:
            treated_at_from_db = treated_at_from_db.replace(tzinfo=UTC)
        assert treated_at_from_db == treated_at
        assert finding.treatment_note == "handled outside this test"
        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_since_at is None
        assert finding.resolved_externally_at is None
        assert finding.needs_review is True
        assert finding.total_occurrence_count == 2
        assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 2


def test_human_lifecycle_is_independent_from_presence_lifecycle(environment):
    http, engine = environment
    with Session(engine) as db:
        finding = _persist(db, "first", START)
        finding_id = finding.id

    response = http.post(f"/findings/{finding_id}/treat", json={"note": "done"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "treated"
    assert body["presence_status"] == "active"
    assert body["resolved_externally_at"] is None

    response = http.post(f"/findings/{finding_id}/reopen", json={"note": "review"})
    assert response.status_code == 200
    assert response.json()["status"] == "open"
    assert response.json()["presence_status"] == "active"

    missing_at = START + timedelta(days=2)
    with Session(engine) as db:
        finding = db.get(Finding, finding_id)
        finding.presence_status = OpportunityPresenceStatus.MISSING.value
        finding.missing_since_at = missing_at
        db.commit()

    response = http.post(
        f"/findings/{finding_id}/reject",
        json={"reason": "RESOURCE_REQUIRED", "note": "still required"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["presence_status"] == "missing"
    assert body["missing_since_at"] is not None
    assert body["resolved_externally_at"] is None


def test_read_apis_expose_presence_without_synthetic_absence_observations(environment):
    http, engine = environment
    missing_at = START + timedelta(hours=6)
    with Session(engine) as db:
        finding = _persist(db, "first", START)
        finding.presence_status = OpportunityPresenceStatus.MISSING.value
        finding.missing_since_at = missing_at
        db.commit()
        finding_id = finding.id
        observation_count = db.scalar(select(func.count()).select_from(OpportunityObservation))

    detail = http.get(f"/opportunities/{finding_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "open"
    assert body["presence_status"] == "missing"
    assert body["missing_since_at"] is not None
    assert body["resolved_externally_at"] is None

    legacy = http.get("/findings")
    assert legacy.status_code == 200
    assert legacy.json()[0]["presence_status"] == "missing"

    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(OpportunityObservation)) == observation_count
        )
