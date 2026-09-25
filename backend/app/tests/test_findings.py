from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.findings import router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                AwsAccount(
                    id=i,
                    name=f"Account {i}",
                    aws_account_id=str(i).zfill(12),
                    role_arn="test-role",
                    external_id="test",
                )
                for i in (1, 2)
            ]
        )
        db.flush()
        db.add(Scan(id="scan", account_id=1))
        db.flush()
        for i in range(505):
            db.add(
                Finding(
                    id=str(i).zfill(4),
                    fingerprint=str(i).zfill(64),
                    scan_id="scan",
                    account_id=1 if i % 2 == 0 else 2,
                    rule_key="missing_required_tags" if i % 2 == 0 else "ebs_unattached",
                    service="EC2",
                    region="sa-east-1",
                    resource_id=f"resource-{i}",
                    title="Test finding",
                    description="Test",
                    evidence={},
                    severity="high",
                    status="open",
                    first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                    last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
        db.commit()
    with Session(engine) as db:
        admin = User(
            name="Test admin", email="test@example.com", password_hash="unused", role="admin"
        )
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
    with TestClient(app) as test_client:
        test_client.headers.update(
            {
                "Cookie": f"{COOKIE}={token}",
                "X-CSRF-Token": csrf_token(token),
                "X-DeepOps-Request": "1",
            }
        )
        yield test_client, engine
    engine.dispose()


def test_pagination_and_account_rule_filters(client):
    http, _ = client
    first = http.get("/findings?limit=500").json()
    second = http.get("/findings?limit=500&offset=500").json()
    assert len(first) == 500
    assert len(second) == 5
    assert len({item["id"] for item in first + second}) == 505
    filtered = http.get("/findings?account_id=1&rule_key=missing_required_tags&limit=500").json()
    assert len(filtered) == 253
    assert all(item["account_id"] == 1 for item in filtered)
    assert http.get("/findings?offset=-1").status_code == 422


@pytest.mark.parametrize("status", ["treated", "rejected"])
def test_bulk_only_changes_selected_findings(client, status):
    http, engine = client
    response = http.post(
        "/findings/bulk/action",
        json={
            "finding_ids": ["0000", "0002", "0002"],
            "action": "treat" if status == "treated" else "reject",
            "reason": None if status == "treated" else "FALSE_POSITIVE",
        },
    )
    assert response.status_code == 200
    assert response.json()["updated_count"] == 2
    with Session(engine) as db:
        changed = list(db.scalars(select(Finding).where(Finding.status == status)))
        assert {finding.id for finding in changed} == {"0000", "0002"}
        assert db.get(Finding, "0001").status == "open"


def test_missing_finding_does_not_partially_apply(client):
    http, engine = client
    response = http.patch(
        "/findings/bulk/action",
        json={
            "finding_ids": ["0000", "missing"],
            "action": "reject", "reason": "FALSE_POSITIVE",
        },
    )
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.get(Finding, "0000").status == "open"


def test_stale_selection_does_not_overwrite_status(client):
    http, engine = client
    http.post("/findings/0000/treat", json={})
    response = http.patch(
        "/findings/bulk/status",
        json={
            "finding_ids": ["0000", "0002"],
            "action": "reject",
            "reason": "FALSE_POSITIVE",
        },
    )
    assert response.status_code == 409
    with Session(engine) as db:
        assert db.get(Finding, "0000").status == "treated"
        assert db.get(Finding, "0002").status == "open"


@pytest.mark.parametrize(
    "payload",
    [
        {"finding_ids": [], "action": "reject", "reason": "FALSE_POSITIVE"},
        {"finding_ids": ["0000"], "action": "invalid"},
    ],
)
def test_invalid_bulk_request(client, payload):
    http, _ = client
    assert http.patch("/findings/bulk/status", json=payload).status_code == 422


def test_bulk_requires_authentication(client):
    http, _ = client
    del http.headers["Cookie"]
    assert (
        http.patch(
            "/findings/bulk/status",
            json={
                "finding_ids": ["0000"],
                "status": "dismissed",
            },
        ).status_code
        == 401
    )
