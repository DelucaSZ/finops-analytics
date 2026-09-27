from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.routes.dashboard import router
from app.models.collection_run import CollectionRun
from app.models.opportunity_observation import OpportunityObservation
from app.services.dashboard import collection_health, dashboard_summary
from app.tests.test_opportunities_api import START, client  # noqa: F401


def _observation(opportunity_id: str, run_id: str, *, savings: str, severity: str):
    return OpportunityObservation(
        opportunity_id=opportunity_id,
        collection_run_id=run_id,
        observed_at=START + timedelta(days=1, minutes=int(opportunity_id[-3:])),
        severity=severity,
        current_monthly_cost=Decimal(savings),
        estimated_monthly_savings=Decimal(savings),
        confidence="high",
        evidence={"dashboard": True, "opportunity": opportunity_id},
    )


@pytest.fixture
def dashboard(client):  # noqa: F811
    http, engine = client
    http.app.include_router(router)
    with Session(engine) as db:
        db.get(CollectionRun, "run-a1").analyzer_version = "rules-v1"
        db.get(CollectionRun, "run-a2").analyzer_version = "rules-v2"
        db.add_all(
            [
                _observation("opp-002", "run-a2", savings="30", severity="low"),
                _observation("opp-004", "run-a2", savings="40", severity="medium"),
                _observation("opp-010", "run-a2", savings="100", severity="medium"),
                _observation("opp-001", "run-b1", savings="11", severity="low"),
                _observation("opp-003", "run-b1", savings="13", severity="medium"),
                CollectionRun(
                    id="run-a3-failed",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START + timedelta(days=2),
                    finished_at=START + timedelta(days=2, minutes=1),
                    status="FAILED",
                    error_detail="AccessDenied",
                ),
                CollectionRun(
                    id="run-oci-1",
                    provider="oci",
                    account_id="ocid1.tenancy.dashboard",
                    started_at=START + timedelta(days=3),
                    finished_at=START + timedelta(days=3, minutes=1),
                    status="SUCCESS",
                ),
            ]
        )
        db.commit()
    return http, engine


def test_current_state_uses_latest_success_per_account_and_counts_opportunities_once(dashboard):
    http, _ = dashboard
    response = http.get("/dashboard/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["scope"]["valid_scope_count"] == 3
    assert body["scope"]["has_current_data"] is True
    # Current observations: A=run-a2, B=run-b1, OCI has no observations.
    assert body["opportunities"] == {
        "open": 2,
        "treated": 3,
        "rejected": 1,
        "new_since_previous": 1,
    }
    assert body["severity"] == {"high": 1, "medium": 1, "low": 0, "other": 0}
    assert body["financial"]["totals"] == [{"currency": "USD", "amount": "33.00"}]

    # opp-000 has observations in run-a1 and run-a2 but is still one logical opportunity.
    assert {item["id"] for item in body["top_opportunities"]} == {"opp-000", "opp-003"}

    drill_down = http.get(
        "/opportunities?current=true&status=open&page_size=100"
    ).json()
    assert drill_down["total"] == body["opportunities"]["open"]
    assert {item["id"] for item in drill_down["items"]} == {"opp-000", "opp-003"}


def test_recent_changes_are_account_local_and_first_collection_is_not_counted_as_new(dashboard):
    body = dashboard[0].get("/dashboard/summary").json()
    recent = body["recent_changes"]
    assert recent["new"] == 1  # opp-010 only in A target versus A baseline
    assert recent["no_longer_detected"] == 2  # opp-006 and opp-008 disappeared from A
    assert recent["comparable_scopes"] == 1
    assert recent["scopes_without_baseline"] == 2  # B and OCI only have one SUCCESS
    assert recent["rules_version_changed_scopes"] == 1
    assert recent["changed"] is None
    assert recent["changed_available"] is False


def test_latest_failed_execution_does_not_replace_latest_valid_collection(dashboard):
    health = dashboard[0].get("/dashboard/collection-health").json()
    assert health["total_scopes"] == 3
    assert health["valid_scopes"] == 3
    assert health["latest_execution"]["failed"] == 1

    account = next(item for item in health["items"] if item["account_id"] == "111111111111")
    assert account["latest_execution"]["id"] == "run-a3-failed"
    assert account["latest_execution"]["status"] == "FAILED"
    assert account["latest_valid"]["id"] == "run-a2"
    assert account["latest_valid"]["status"] == "SUCCESS"
    assert health["stale_policy_configured"] is False


def test_provider_and_account_filters_are_applied_to_current_state_and_health(dashboard):
    http, _ = dashboard
    aws = http.get("/dashboard/summary?provider=aws").json()
    assert aws["scope"]["valid_scope_count"] == 2
    assert aws["opportunities"]["open"] == 2
    assert {row["provider"] for row in aws["by_provider"]} == {"aws"}

    oci = http.get("/dashboard/summary?provider=oci").json()
    assert oci["scope"]["valid_scope_count"] == 1
    assert oci["opportunities"]["open"] == 0
    assert oci["by_provider"] == []

    account = http.get(
        "/dashboard/summary?provider=aws&account_id=111111111111"
    ).json()
    assert account["scope"]["valid_scope_count"] == 1
    assert account["opportunities"] == {
        "open": 1,
        "treated": 2,
        "rejected": 1,
        "new_since_previous": 1,
    }
    assert {
        row["account_id"] for row in account["by_account"]
    } == {"111111111111"}

    health = http.get(
        "/dashboard/collection-health?provider=aws&account_id=111111111111"
    ).json()
    assert health["total_scopes"] == 1
    assert health["latest_execution"]["failed"] == 1


def test_dashboard_uses_bounded_aggregate_queries_not_frontend_sized_reads(dashboard):
    _, engine = dashboard
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    with Session(engine) as db:
        event.listen(engine, "before_cursor_execute", record)
        try:
            summary = dashboard_summary(db)
            assert summary["opportunities"]["open"] == 2
            assert len(statements) == 9

            statements.clear()
            health = collection_health(db)
            assert health["latest_execution"]["failed"] == 1
            assert len(statements) == 3
        finally:
            event.remove(engine, "before_cursor_execute", record)


def test_dashboard_requires_authentication(dashboard):
    http, _ = dashboard
    http.headers.pop("Cookie")
    http.cookies.clear()
    assert http.get("/dashboard/summary").status_code == 401
    assert http.get("/dashboard/collection-health").status_code == 401
