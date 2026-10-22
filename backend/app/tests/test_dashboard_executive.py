from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.dashboard_aggregation import rebuild_account_summary
from app.tests.test_dashboard import START, dashboard  # noqa: F401


def test_executive_dashboard_preserves_currencies_in_every_financial_breakdown(
    dashboard,  # noqa: F811
):
    http, engine = dashboard

    with Session(engine) as db:
        observation = db.scalar(
            select(OpportunityObservation).where(
                OpportunityObservation.opportunity_id == "opp-003",
                OpportunityObservation.collection_run_id == "run-b1",
            )
        )
        assert observation is not None
        observation.currency = "BRL"
        rebuild_account_summary(
            db,
            provider="aws",
            account_id="222222222222",
        )
        db.commit()

    body = http.get("/dashboard/summary").json()
    assert body["financial"]["totals"] == [
        {"currency": "BRL", "amount": "13.00"},
        {"currency": "USD", "amount": "20.00"},
    ]
    assert body["by_provider"][0]["savings"] == [
        {"currency": "BRL", "amount": "13.00"},
        {"currency": "USD", "amount": "20.00"},
    ]
    assert {
        (total["currency"], total["amount"])
        for account in body["by_account"]
        for total in account["savings"]
    } == {("BRL", "13.00"), ("USD", "20.00")}
    assert {
        (total["currency"], total["amount"])
        for service in body["by_service"]
        for total in service["savings"]
    } == {("BRL", "13.00"), ("USD", "20.00")}
    assert {item["currency"] for item in body["top_opportunities"]} == {"BRL", "USD"}


def test_critical_severity_is_reported_as_first_class_executive_severity(
    dashboard,  # noqa: F811
):
    http, engine = dashboard

    with Session(engine) as db:
        observation = db.scalar(
            select(OpportunityObservation).where(
                OpportunityObservation.opportunity_id == "opp-000",
                OpportunityObservation.collection_run_id == "run-a2",
            )
        )
        assert observation is not None
        observation.severity = "critical"
        db.commit()

    body = http.get("/dashboard/summary").json()
    assert body["severity"] == {
        "critical": 1,
        "high": 0,
        "medium": 1,
        "low": 0,
        "other": 0,
    }
    critical = next(item for item in body["top_opportunities"] if item["id"] == "opp-000")
    assert critical["severity"] == "critical"


def test_archived_open_opportunity_is_excluded_from_current_executive_sections(
    dashboard,  # noqa: F811
):
    http, engine = dashboard

    with Session(engine) as db:
        finding = db.get(Finding, "opp-000")
        assert finding is not None
        finding.archived_at = START + timedelta(days=4)
        finding.archive_reason = "MANUAL"
        rebuild_account_summary(
            db,
            provider="aws",
            account_id="111111111111",
        )
        db.commit()

    body = http.get("/dashboard/summary").json()
    assert body["opportunities"]["open"] == 1
    assert body["financial"]["totals"] == [{"currency": "USD", "amount": "13.00"}]
    assert body["severity"] == {
        "critical": 0,
        "high": 0,
        "medium": 1,
        "low": 0,
        "other": 0,
    }
    assert {item["id"] for item in body["top_opportunities"]} == {"opp-003"}
    assert sum(item["open"] for item in body["by_provider"]) == 1
    assert sum(item["open"] for item in body["by_account"]) == 1
    assert sum(item["open"] for item in body["by_service"]) == 1
    assert sum(item["open"] for item in body["by_rule"]) == 1
