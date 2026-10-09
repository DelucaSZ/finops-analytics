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
from app.api.routes.opportunities import router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_archive_history import OpportunityArchiveHistory
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.collector_types import CollectedFinding
from app.services.opportunity_archiving import archive

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _finding(*, opportunity_id: str, provider: str, status: str = "open") -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=(opportunity_id[-1] * 64)[:64],
        provider=provider,
        account_id="111111111111" if provider == "aws" else "ocid1.tenancy.oc1..archive",
        rule_key="ec2_stopped" if provider == "aws" else "oci_compute_idle",
        service="EC2" if provider == "aws" else "Compute",
        region="sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        resource_id=f"resource-{opportunity_id}",
        resource_name=opportunity_id,
        title="Archive test",
        description="Archive lifecycle test",
        evidence={},
        current_monthly_cost=Decimal("10"),
        estimated_monthly_savings=Decimal("10"),
        confidence="high",
        severity="medium",
        status=status,
        first_seen_at=START,
        last_seen_at=START,
    )


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash="unused",
            role="admin",
        )
        db.add(admin)
        db.add_all(
            [
                _finding(opportunity_id="aws-1", provider="aws"),
                _finding(opportunity_id="oci-2", provider="oci", status="rejected"),
            ]
        )
        db.commit()
        _, token = new_session(db, admin)
        db.commit()

    app = FastAPI()
    app.include_router(router)

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
        yield http, engine, app
    engine.dispose()


def test_manual_archive_is_auditable_provider_neutral_and_hidden_by_default(client):
    http, engine, _ = client

    response = http.post("/opportunities/aws-1/archive")
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is True
    assert body["archived_at"] is not None
    assert body["archived_by"] is not None
    assert body["archive_reason"] == "MANUAL"
    assert body["status"] == "open"
    assert body["presence_status"] == "active"

    assert http.get("/opportunities?page_size=100").json()["total"] == 1
    archived = http.get("/opportunities?archive_state=archived&page_size=100").json()
    assert archived["total"] == 1
    assert archived["items"][0]["id"] == "aws-1"
    assert http.get("/opportunities?archive_state=all&page_size=100").json()["total"] == 2

    detail = http.get("/opportunities/aws-1")
    assert detail.status_code == 200
    assert detail.json()["archived"] is True

    history = http.get("/opportunities/aws-1/archive-history").json()
    assert history["total"] == 1
    assert history["items"][0]["action"] == "ARCHIVE"
    assert history["items"][0]["reason"] == "MANUAL"
    assert history["items"][0]["changed_by_name"] == "Admin"

    # OCI follows the same provider-neutral path and preserves human status.
    oci = http.post("/opportunities/oci-2/archive")
    assert oci.status_code == 200
    assert oci.json()["provider"] == "oci"
    assert oci.json()["status"] == "rejected"

    with Session(engine) as db:
        aws = db.get(Finding, "aws-1")
        oci_finding = db.get(Finding, "oci-2")
        assert aws.status == "open" and aws.presence_status == "active"
        assert oci_finding.status == "rejected" and oci_finding.presence_status == "active"


def test_archive_and_unarchive_are_idempotent_and_preserve_lifecycles(client):
    http, engine, _ = client

    assert http.post("/opportunities/oci-2/archive").status_code == 200
    assert http.post("/opportunities/oci-2/archive").status_code == 200
    response = http.post("/opportunities/oci-2/unarchive")
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is False
    assert body["archived_at"] is None
    assert body["archive_reason"] is None
    assert body["status"] == "rejected"
    assert body["presence_status"] == "active"
    assert http.post("/opportunities/oci-2/unarchive").status_code == 200

    with Session(engine) as db:
        history = list(
            db.scalars(
                select(OpportunityArchiveHistory)
                .where(OpportunityArchiveHistory.opportunity_id == "oci-2")
                .order_by(OpportunityArchiveHistory.occurred_at)
            )
        )
        assert [(item.action, item.reason) for item in history] == [
            ("ARCHIVE", "MANUAL"),
            ("UNARCHIVE", "MANUAL"),
        ]


def test_archive_mutation_requires_authentication(client):
    _, _, app = client
    with TestClient(app) as anonymous:
        response = anonymous.post("/opportunities/aws-1/archive")
    assert response.status_code in {401, 403}


def _collected(resource_id: str) -> CollectedFinding:
    return CollectedFinding(
        rule_key="ec2_stopped",
        service="EC2",
        region="sa-east-1",
        resource_id=resource_id,
        resource_name=resource_id,
        title="Reappeared opportunity",
        description="Test",
        evidence={"instance_state": "stopped", "stopped_days": 14},
        current_monthly_cost=Decimal("42"),
        estimated_monthly_savings=Decimal("20"),
        confidence="high",
        severity="medium",
    )


def _run(db: Session, account: AwsAccount, started_at: datetime) -> tuple[Scan, CollectionRun]:
    scan = Scan(
        account_id=account.id,
        cloud_account_id=account.cloud_account_id,
        status="running",
        started_at=started_at,
    )
    db.add(scan)
    db.flush()
    run = CollectionRun(
        scan_id=scan.id,
        provider="aws",
        account_id=account.aws_account_id,
        started_at=started_at,
        status=CollectionRunStatus.RUNNING,
    )
    db.add(run)
    db.flush()
    return scan, run


@pytest.mark.parametrize(
    ("human_status", "expected_review"),
    [("treated", True), ("rejected", False)],
)
def test_reappearance_reuses_fingerprint_unarchives_and_preserves_human_status(
    tmp_path,
    human_status,
    expected_review,
):
    engine = create_engine(f"sqlite:///{tmp_path / f'archive-{human_status}.db'}")
    Base.metadata.create_all(engine)
    first_seen = START - timedelta(days=3)
    reappeared_at = START - timedelta(days=1)
    try:
        with Session(engine) as db:
            account = AwsAccount(
                name="Test",
                aws_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/DeepOps",
                external_id="archive-test",
                regions=["sa-east-1"],
            )
            actor = User(
                name="Operator",
                email=f"{human_status}@example.com",
                password_hash="unused",
                role="admin",
            )
            db.add_all([account, actor])
            db.flush()

            first_scan, first_run = _run(db, account, first_seen)
            worker.persist_findings(
                db,
                first_scan,
                first_run,
                [_collected(f"i-{human_status}")],
                ["ec2_stopped"],
                observed_at=first_seen,
            )
            finding = db.scalar(select(Finding))
            finding.status = human_status
            if human_status == "treated":
                finding.treated_at = first_seen + timedelta(hours=1)
                finding.treated_by = actor.id
            else:
                finding.rejected_at = first_seen + timedelta(hours=1)
                finding.rejected_by = actor.id
                finding.rejection_reason = "RESOURCE_REQUIRED"
            finding.presence_status = OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
            finding.resolved_externally_at = first_seen + timedelta(days=1)
            archive(db, finding.id, actor)
            original_id = finding.id
            original_fingerprint = finding.fingerprint
            db.commit()

            second_scan, second_run = _run(db, account, reappeared_at)
            worker.persist_findings(
                db,
                second_scan,
                second_run,
                [_collected(f"i-{human_status}")],
                ["ec2_stopped"],
                observed_at=reappeared_at,
            )
            db.commit()

            assert db.scalar(select(func.count()).select_from(Finding)) == 1
            assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 2
            finding = db.get(Finding, original_id)
            assert finding.fingerprint == original_fingerprint
            assert finding.status == human_status
            assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
            assert finding.archived_at is None
            assert finding.archived_by is None
            assert finding.archive_reason is None
            assert finding.needs_review is expected_review

            history = list(
                db.scalars(
                    select(OpportunityArchiveHistory)
                    .where(OpportunityArchiveHistory.opportunity_id == original_id)
                    .order_by(OpportunityArchiveHistory.occurred_at)
                )
            )
            assert [(event.action, event.reason) for event in history] == [
                ("ARCHIVE", "MANUAL"),
                ("UNARCHIVE", "REAPPEARED"),
            ]
            assert history[-1].collection_run_id == second_run.id
    finally:
        engine.dispose()
