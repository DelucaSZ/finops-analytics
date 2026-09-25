from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.opportunities import router
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.opportunity_query import OpportunityFilters, list_opportunities

START = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        accounts = [
            AwsAccount(
                id=1,
                name="Production",
                aws_account_id="111111111111",
                role_arn="role-a",
                external_id="test-a",
            ),
            AwsAccount(
                id=2,
                name="Development",
                aws_account_id="222222222222",
                role_arn="role-b",
                external_id="test-b",
            ),
        ]
        db.add_all(accounts)
        scans = [
            Scan(id="scan-a1", account_id=1),
            Scan(id="scan-a2", account_id=1),
            Scan(id="scan-b1", account_id=2),
        ]
        db.add_all(scans)
        db.flush()
        runs = [
            CollectionRun(
                id="run-a1",
                scan_id="scan-a1",
                provider="aws",
                account_id="111111111111",
                started_at=START,
                finished_at=START + timedelta(minutes=2),
                status="SUCCESS",
            ),
            CollectionRun(
                id="run-a2",
                scan_id="scan-a2",
                provider="aws",
                account_id="111111111111",
                started_at=START + timedelta(days=1),
                finished_at=START + timedelta(days=1, minutes=2),
                status="SUCCESS",
            ),
            CollectionRun(
                id="run-b1",
                scan_id="scan-b1",
                provider="aws",
                account_id="222222222222",
                started_at=START,
                finished_at=START + timedelta(minutes=3),
                status="SUCCESS",
            ),
        ]
        db.add_all(runs)
        db.flush()
        for index in range(100):
            account_id = 1 if index % 2 == 0 else 2
            status = ("open", "treated", "rejected")[index % 3]
            severity = ("high", "medium", "low")[index % 3]
            finding = Finding(
                id=f"opp-{index:03d}",
                fingerprint=f"{index:064x}",
                scan_id="scan-a2" if account_id == 1 else "scan-b1",
                account_id=account_id,
                rule_key="missing_required_tags" if index % 2 == 0 else "ebs_unattached",
                service="EC2",
                region="sa-east-1" if account_id == 1 else "us-east-1",
                resource_id=f"resource-{index:03d}",
                resource_name=f"Resource {index:03d}",
                title=f"Opportunity {index:03d}",
                description=f"Description {index:03d}",
                evidence={"index": index},
                current_monthly_cost=Decimal(index),
                estimated_monthly_savings=Decimal(index + 1),
                confidence="high",
                severity=severity,
                status=status,
                first_seen_at=START,
                last_seen_at=START + timedelta(minutes=index),
            )
            db.add(finding)
        db.flush()
        for index in range(0, 10, 2):
            db.add(
                OpportunityObservation(
                    opportunity_id=f"opp-{index:03d}",
                    collection_run_id="run-a1",
                    observed_at=START + timedelta(minutes=index),
                    severity=("high", "medium", "low")[index % 3],
                    current_monthly_cost=Decimal(index),
                    estimated_monthly_savings=Decimal(index + 1),
                    confidence="high",
                    evidence={
                        "run": "a1",
                        "index": index,
                        "missing_tags": ["Owner"],
                        "current_tags": {"Environment": "Production"},
                        "policy_config": {"required_tags": ["Environment", "Owner"]},
                    },
                )
            )
        db.add(
            OpportunityObservation(
                opportunity_id="opp-000",
                collection_run_id="run-a2",
                observed_at=START + timedelta(days=1),
                severity="high",
                current_monthly_cost=Decimal("10"),
                estimated_monthly_savings=Decimal("20"),
                confidence="high",
                evidence={
                    "run": "a2",
                    "missing_tags": ["Owner", "CostCenter"],
                    "current_tags": {"Environment": "Production"},
                    "policy_config": {"required_tags": ["Environment", "Owner", "CostCenter"]},
                },
            )
        )
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


def test_server_side_pagination_has_five_pages(client):
    http, _ = client
    response = http.get("/opportunities?page=1&page_size=20")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 20
    assert body["total"] == 100
    assert body["total_pages"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert "evidence" not in body["items"][0]


def test_filters_by_status_account_provider_and_combination(client):
    http, _ = client
    status_items = http.get("/opportunities?status=open&page_size=100").json()["items"]
    assert status_items
    assert all(item["status"] == "open" for item in status_items)

    account_items = http.get("/opportunities?account_id=111111111111&page_size=100").json()["items"]
    assert len(account_items) == 50
    assert all(item["account_id"] == "111111111111" for item in account_items)

    provider_items = http.get("/opportunities?provider=aws&page_size=100").json()["items"]
    assert len(provider_items) == 100
    assert http.get("/opportunities?provider=oci").json()["total"] == 0

    combined = http.get(
        "/opportunities?provider=aws&account_id=111111111111"
        "&status=open&severity=high&page_size=100"
    ).json()["items"]
    assert combined
    assert all(
        item["provider"] == "aws"
        and item["account_id"] == "111111111111"
        and item["status"] == "open"
        and item["severity"] == "high"
        for item in combined
    )


def test_legacy_internal_account_id_remains_accepted(client):
    http, _ = client
    response = http.get("/opportunities?account_id=1&page_size=100")
    assert response.status_code == 200
    assert response.json()["total"] == 50


def test_collection_run_filter_uses_observations(client):
    http, _ = client
    body = http.get("/opportunities?collection_run_id=run-a1&page_size=100").json()
    assert body["total"] == 5
    assert {item["id"] for item in body["items"]} == {
        "opp-000",
        "opp-002",
        "opp-004",
        "opp-006",
        "opp-008",
    }


def test_search_and_ordering_are_server_side(client):
    http, _ = client
    search = http.get("/opportunities?search=resource-042").json()
    assert search["total"] == 1
    assert search["items"][0]["id"] == "opp-042"

    recent = http.get("/opportunities?page_size=5&sort=last_seen_at&order=desc").json()["items"]
    assert [item["id"] for item in recent] == [
        "opp-099",
        "opp-098",
        "opp-097",
        "opp-096",
        "opp-095",
    ]
    savings = http.get("/opportunities?page_size=3&sort=estimated_savings&order=asc").json()[
        "items"
    ]
    assert [item["id"] for item in savings] == ["opp-000", "opp-001", "opp-002"]
    assert http.get("/opportunities?sort=not_a_column").status_code == 422
    assert http.get("/opportunities?page_size=201").status_code == 422


def test_detail_exposes_latest_evidence_without_loading_full_history(client):
    http, _ = client
    response = http.get("/opportunities/opp-000")
    assert response.status_code == 200
    detail = response.json()
    assert detail["fingerprint"] == "0" * 64
    assert detail["account_id"] == "111111111111"
    assert detail["latest_observation"]["collection_run_id"] == "run-a2"
    assert detail["latest_evidence"]["schema_version"] == 1
    assert detail["latest_evidence"]["details"]["missing_tags"] == ["Owner", "CostCenter"]
    assert detail["latest_evidence"]["parameters"]["required_tags"] == [
        "Environment",
        "Owner",
        "CostCenter",
    ]
    assert detail["rule"]["key"] == "missing_required_tags"


def test_observation_history_returns_collection_specific_evidence(client):
    http, _ = client
    history = http.get("/opportunities/opp-000/history?page_size=10").json()
    assert history["total"] == 2
    assert [item["collection_run_id"] for item in history["items"]] == [
        "run-a2",
        "run-a1",
    ]
    assert [item["evidence"]["details"]["missing_tags"] for item in history["items"]] == [
        ["Owner", "CostCenter"],
        ["Owner"],
    ]
    assert all(item["evidence"]["schema_version"] == 1 for item in history["items"])


def test_individual_lifecycle_and_status_history(client):
    http, engine = client
    response = http.post("/opportunities/opp-000/treat", json={"note": "done"})
    assert response.status_code == 200
    history = http.get("/opportunities/opp-000/status-history").json()
    assert history["total"] == 1
    assert history["items"][0]["action"] == "treat"
    assert history["items"][0]["changed_by_name"] == "Admin"

    response = http.post(
        "/opportunities/opp-000/reopen",
        json={"note": "review"},
    )
    assert response.status_code == 200
    response = http.post(
        "/opportunities/opp-000/reject",
        json={"reason": "RESOURCE_REQUIRED", "note": "required"},
    )
    assert response.status_code == 200
    with Session(engine) as db:
        finding = db.get(Finding, "opp-000")
        assert finding.status == "rejected"
        rows = list(
            db.scalars(
                select(OpportunityStatusHistory).where(
                    OpportunityStatusHistory.opportunity_id == "opp-000"
                )
            )
        )
        assert len(rows) == 3


def test_bulk_actions_are_atomic(client):
    http, engine = client
    response = http.post(
        "/opportunities/bulk/treat",
        json={"opportunity_ids": ["opp-003", "opp-006"]},
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 2

    response = http.post(
        "/opportunities/bulk/reject",
        json={
            "opportunity_ids": ["opp-009", "missing"],
            "reason": "FALSE_POSITIVE",
        },
    )
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.get(Finding, "opp-009").status == "open"

    response = http.post(
        "/opportunities/bulk/reopen",
        json={"opportunity_ids": ["opp-003", "opp-006"]},
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 2


def test_stats_respect_non_status_filters(client):
    http, _ = client
    body = http.get("/opportunities/stats?account_id=111111111111").json()
    assert sum(body.values()) == 50
    filtered = http.get("/opportunities/stats?account_id=111111111111&severity=high").json()
    assert sum(filtered.values()) > 0
    assert sum(filtered.values()) < 50


def test_listing_executes_count_plus_bounded_page_query(client):
    _, engine = client
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if "findings" in statement.lower():
            statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            result = list_opportunities(
                db,
                OpportunityFilters(status="open"),
                page=1,
                page_size=20,
                sort="last_seen_at",
                order="desc",
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(result["items"]) == 20
    assert len(statements) == 2
    assert any("limit" in statement and "offset" in statement for statement in statements)
