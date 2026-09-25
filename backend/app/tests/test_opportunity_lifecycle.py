from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.findings import router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.finding import Finding
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AwsAccount(id=1, name="Account", aws_account_id="123456789012", role_arn="role", external_id="x"))
        db.add(Scan(id="scan", account_id=1))
        db.flush()
        db.add(Finding(id="opp", fingerprint="a" * 64, scan_id="scan", account_id=1, rule_key="ebs_unattached", service="EC2", region="sa-east-1", resource_id="vol-1", title="Volume", description="Test", evidence={}, severity="high", status="open", first_seen_at=datetime(2026, 1, 1, tzinfo=UTC), last_seen_at=datetime(2026, 1, 1, tzinfo=UTC)))
        admin = User(name="Admin", email="admin@example.com", password_hash="unused", role="admin")
        db.add(admin)
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
        http.headers.update({"Cookie": f"{COOKIE}={token}", "X-CSRF-Token": csrf_token(token), "X-DeepOps-Request": "1"})
        yield http, engine


def test_treat_reopen_and_history(client):
    http, engine = client
    response = http.post("/findings/opp/treat", json={"note": "removed"})
    assert response.status_code == 200
    assert response.json()["status"] == "treated"
    assert response.json()["treated_by"]
    response = http.post("/findings/opp/reopen", json={"note": "review again"})
    assert response.status_code == 200
    assert response.json()["status"] == "open"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(OpportunityStatusHistory)) == 2
        assert db.get(Finding, "opp").treatment_note == "removed"


def test_reject_requires_reason_and_preserves_decision(client):
    http, engine = client
    assert http.post("/findings/opp/reject", json={"reason": "OTHER"}).status_code == 422
    response = http.post("/findings/opp/reject", json={"reason": "RESOURCE_REQUIRED", "note": "contingency"})
    assert response.status_code == 200
    with Session(engine) as db:
        finding = db.get(Finding, "opp")
        assert finding.status == "rejected"
        assert finding.rejection_reason == "RESOURCE_REQUIRED"
        assert finding.rejected_by is not None


def test_invalid_transitions_are_conflicts(client):
    http, _ = client
    assert http.post("/findings/opp/reopen", json={}).status_code == 409
    assert http.post("/findings/opp/treat", json={}).status_code == 200
    assert http.post("/findings/opp/reject", json={"reason": "FALSE_POSITIVE"}).status_code == 409


def test_bulk_is_atomic_for_invalid_transition(client):
    http, engine = client
    response = http.post("/findings/bulk/action", json={"finding_ids": ["opp"], "action": "treat"})
    assert response.status_code == 200
    response = http.post("/findings/bulk/action", json={"finding_ids": ["opp"], "action": "treat"})
    assert response.status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(OpportunityStatusHistory)) == 1
