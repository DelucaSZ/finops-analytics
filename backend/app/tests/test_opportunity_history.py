from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.opportunities import router
from app.db.base import Base
from app.db.session import get_db
from app.models.finding import Finding
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.opportunity_archiving import archive, archive_retention_locked

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _finding(
    opportunity_id: str,
    *,
    provider: str,
    account_id: str,
    status: str,
    presence_status: str,
    service: str,
    currency: str,
    saving: str,
) -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=(opportunity_id[-1] * 64)[:64],
        provider=provider,
        account_id=account_id,
        rule_key=f"{provider}_{service.lower()}_idle",
        service=service,
        region="sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        resource_id=f"resource-{opportunity_id}",
        resource_name=f"Resource {opportunity_id}",
        title=f"Opportunity {opportunity_id}",
        description="Historical query test",
        evidence={},
        current_monthly_cost=Decimal(saving),
        estimated_monthly_savings=Decimal(saving),
        currency=currency,
        confidence="high",
        severity="medium",
        status=status,
        presence_status=presence_status,
        first_seen_at=NOW - timedelta(days=120),
        last_seen_at=NOW - timedelta(days=90),
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
            email="admin-history@example.com",
            password_hash="unused",
            role="admin",
        )
        aws = _finding(
            "aws-1",
            provider="aws",
            account_id="111111111111",
            status="treated",
            presence_status="resolved_externally",
            service="EBS",
            currency="USD",
            saving="120",
        )
        oci = _finding(
            "oci-2",
            provider="oci",
            account_id="ocid1.tenancy.oc1..history",
            status="rejected",
            presence_status="active",
            service="BlockStorage",
            currency="BRL",
            saving="420",
        )
        active = _finding(
            "aws-3",
            provider="aws",
            account_id="111111111111",
            status="open",
            presence_status="active",
            service="EC2",
            currency="USD",
            saving="25",
        )
        db.add_all([admin, aws, oci, active])
        db.flush()
        archive(db, aws.id, admin)
        archive_retention_locked(
            db,
            oci,
            archived_at=NOW - timedelta(days=2),
            policy="rejected",
            threshold_days=60,
            reference_timestamp=NOW - timedelta(days=62),
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
        yield http, engine
    engine.dispose()


def test_history_mode_lists_only_archived_and_orders_by_archive_time(client):
    http, _ = client
    body = http.get(
        "/opportunities?archive_state=archived&sort=archived_at&order=desc&page=1&page_size=1"
    ).json()
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["archived"] is True

    operational = http.get("/opportunities?page_size=100").json()
    assert operational["total"] == 1
    assert operational["items"][0]["id"] == "aws-3"


def test_history_filters_human_and_technical_lifecycle_provider_account_and_service(client):
    http, _ = client
    aws = http.get(
        "/opportunities?archive_state=archived&provider=aws&account_id=111111111111"
        "&status=treated&presence_status=resolved_externally&service=EBS"
    ).json()
    assert aws["total"] == 1
    item = aws["items"][0]
    assert item["id"] == "aws-1"
    assert item["status"] == "treated"
    assert item["presence_status"] == "resolved_externally"
    assert item["currency"] == "USD"

    oci = http.get(
        "/opportunities?archive_state=archived&provider=oci&status=rejected"
        "&presence_status=active&service=BlockStorage&archive_reason=RETENTION_POLICY"
    ).json()
    assert oci["total"] == 1
    assert oci["items"][0]["id"] == "oci-2"
    assert oci["items"][0]["currency"] == "BRL"


def test_history_filters_archived_period(client):
    http, _ = client
    start = (NOW - timedelta(days=3)).isoformat()
    end = (NOW - timedelta(days=1)).isoformat()
    body = http.get(
        "/opportunities",
        params={
            "archive_state": "archived",
            "archived_from": start,
            "archived_to": end,
        },
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "oci-2"


def test_rejected_archived_detail_requires_reopen_and_is_auditable(client):
    http, _ = client
    detail = http.get("/opportunities/oci-2")
    assert detail.status_code == 200
    assert detail.json()["archived"] is True

    archive_history = http.get("/opportunities/oci-2/archive-history").json()
    assert archive_history["total"] == 1
    assert archive_history["items"][0]["reason"] == "RETENTION_POLICY"
    assert archive_history["items"][0]["context"]["threshold_days"] == 60

    blocked = http.post("/opportunities/oci-2/unarchive")
    assert blocked.status_code == 409
    assert "Reabra-a" in blocked.json()["detail"]

    response = http.post("/opportunities/oci-2/reopen", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is False
    assert body["status"] == "open"
    assert body["presence_status"] == "active"

    historical = http.get("/opportunities?archive_state=archived&page_size=100").json()
    assert {item["id"] for item in historical["items"]} == {"aws-1"}

    audit = http.get("/opportunities/oci-2/archive-history").json()
    assert [item["action"] for item in audit["items"]] == ["UNARCHIVE", "ARCHIVE"]
    assert audit["items"][0]["reason"] == "MANUAL"
    assert audit["items"][0]["context"]["trigger"] == "reopen"


def test_history_options_use_archived_scope(client):
    http, _ = client
    archived = http.get("/opportunities/options?archive_state=archived").json()
    assert set(archived["providers"]) == {"aws", "oci"}
    assert set(archived["services"]) == {"EBS", "BlockStorage"}

    active = http.get("/opportunities/options").json()
    assert active["providers"] == ["aws"]
    assert active["services"] == ["EC2"]
