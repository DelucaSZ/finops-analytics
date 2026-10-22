from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.dashboard_new_opportunities import (
    DashboardComparisonContextError,
    dashboard_new_opportunity_stats,
    dashboard_new_since_previous,
    list_dashboard_new_opportunities,
)
from app.services.opportunity_query import OpportunityFilters

START = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    yield value
    value.dispose()


def _run(
    run_id: str,
    account_id: str,
    offset_days: int,
    *,
    status: CollectionRunStatus = CollectionRunStatus.SUCCESS,
) -> CollectionRun:
    started_at = START + timedelta(days=offset_days)
    return CollectionRun(
        id=run_id,
        provider="aws",
        account_id=account_id,
        scope={"regions": ["sa-east-1"]},
        started_at=started_at,
        finished_at=(
            started_at + timedelta(minutes=2) if status != CollectionRunStatus.RUNNING else None
        ),
        status=status,
        analyzer_version="v1",
    )


def _finding(
    opportunity_id: str,
    *,
    account_id: str = "111111111111",
    first_run: str,
    last_run: str,
    severity: str = "medium",
    status: str = "open",
    archived: bool = False,
) -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=f"{len(opportunity_id):02x}{opportunity_id.encode().hex():0<60}"[:64],
        provider="aws",
        account_id=account_id,
        rule_key="test_rule",
        service="EC2",
        region="sa-east-1",
        resource_id=opportunity_id,
        resource_name=opportunity_id,
        resource_type="EC2 Instance",
        provider_metadata={},
        title=opportunity_id,
        description=opportunity_id,
        evidence={},
        current_monthly_cost=Decimal("20"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        severity=severity,
        status=status,
        first_seen_at=START,
        last_seen_at=START + timedelta(days=2),
        first_seen_collection_run_id=first_run,
        last_seen_collection_run_id=last_run,
        total_occurrence_count=2,
        archived_at=START + timedelta(hours=1) if archived else None,
        archive_reason="MANUAL" if archived else None,
    )


def _observe(db: Session, opportunity_id: str, run: CollectionRun) -> None:
    db.add(
        OpportunityObservation(
            opportunity_id=opportunity_id,
            collection_run_id=run.id,
            observed_at=run.started_at,
            severity="medium",
            current_monthly_cost=Decimal("20"),
            estimated_monthly_savings=Decimal("10"),
            currency="USD",
            confidence="high",
            provider_metadata={},
            evidence={},
        )
    )


def _seed(db: Session) -> dict[str, CollectionRun]:
    runs = {
        "a1": _run("a1", "111111111111", 0),
        "a2": _run("a2", "111111111111", 1),
        "a3": _run("a3", "111111111111", 2),
        # A newer failed/running execution must not displace the latest comparable SUCCESS.
        "a4-failed": _run(
            "a4-failed",
            "111111111111",
            3,
            status=CollectionRunStatus.FAILED,
        ),
        "a5-running": _run(
            "a5-running",
            "111111111111",
            4,
            status=CollectionRunStatus.RUNNING,
        ),
        # First collection for account B: it must not inflate new_since_previous.
        "b1": _run("b1", "222222222222", 2),
    }
    db.add_all(runs.values())
    db.flush()

    findings = [
        _finding("continued", first_run="a1", last_run="a3"),
        _finding("reappeared", first_run="a1", last_run="a3", severity="high"),
        _finding("first-seen", first_run="a3", last_run="a3"),
        _finding(
            "rejected-reappeared",
            first_run="a1",
            last_run="a3",
            status="rejected",
        ),
        _finding(
            "archived-first-seen",
            first_run="a3",
            last_run="a3",
            archived=True,
        ),
        _finding(
            "first-collection-only",
            account_id="222222222222",
            first_run="b1",
            last_run="b1",
        ),
    ]
    db.add_all(findings)
    db.flush()

    for opportunity_id in ("continued", "reappeared", "rejected-reappeared"):
        _observe(db, opportunity_id, runs["a1"])
    _observe(db, "continued", runs["a2"])
    for opportunity_id in (
        "continued",
        "reappeared",
        "first-seen",
        "rejected-reappeared",
        "archived-first-seen",
    ):
        _observe(db, opportunity_id, runs["a3"])
    _observe(db, "first-collection-only", runs["b1"])
    db.commit()
    return runs


def _filters(**overrides) -> OpportunityFilters:
    return OpportunityFilters(archive_state="all", **overrides)


def test_dashboard_count_and_destination_use_the_exact_same_operational_set(engine):
    with Session(engine) as db:
        _seed(db)

        summary = dashboard_new_since_previous(db)
        assert summary["count"] == 2
        assert summary["first_seen_count"] == 1
        assert summary["reappeared_count"] == 1
        assert summary["comparable_accounts"] == 1
        assert summary["accounts_without_baseline"] == 1

        page = list_dashboard_new_opportunities(
            db,
            comparison_context=summary["comparison_context"],
            comparison_kind="new_vs_previous",
            filters=_filters(),
            page=1,
            page_size=50,
            sort="last_seen_at",
            order="desc",
        )
        assert page["total"] == summary["count"]
        assert {item["id"] for item in page["items"]} == {"first-seen", "reappeared"}

        stats = dashboard_new_opportunity_stats(
            db,
            comparison_context=summary["comparison_context"],
            comparison_kind="new_vs_previous",
            filters=_filters(),
        )
        assert stats == {"open": 2, "treated": 0, "rejected": 0}


def test_multi_account_aggregates_each_pair_and_skips_account_without_baseline(engine):
    with Session(engine) as db:
        runs = {
            "a1": _run("multi-a1", "333333333333", 0),
            "a2": _run("multi-a2", "333333333333", 1),
            "b1": _run("multi-b1", "444444444444", 0),
            "b2": _run("multi-b2", "444444444444", 2),
            "c1": _run("multi-c1", "555555555555", 2),
        }
        db.add_all(runs.values())
        db.flush()
        findings = [
            _finding(
                "multi-a-new",
                account_id="333333333333",
                first_run="multi-a2",
                last_run="multi-a2",
            ),
            _finding(
                "multi-b-new",
                account_id="444444444444",
                first_run="multi-b2",
                last_run="multi-b2",
            ),
            _finding(
                "multi-c-first-run",
                account_id="555555555555",
                first_run="multi-c1",
                last_run="multi-c1",
            ),
        ]
        db.add_all(findings)
        db.flush()
        _observe(db, "multi-a-new", runs["a2"])
        _observe(db, "multi-b-new", runs["b2"])
        _observe(db, "multi-c-first-run", runs["c1"])
        db.commit()

        summary = dashboard_new_since_previous(db)
        assert summary["count"] == 2
        assert summary["first_seen_count"] == 2
        assert summary["reappeared_count"] == 0
        assert summary["comparable_accounts"] == 2
        assert summary["accounts_without_baseline"] == 1

        page = list_dashboard_new_opportunities(
            db,
            comparison_context=summary["comparison_context"],
            comparison_kind="new_vs_previous",
            filters=_filters(),
            page=1,
            page_size=50,
            sort="last_seen_at",
            order="desc",
        )
        assert page["total"] == 2
        assert {item["id"] for item in page["items"]} == {"multi-a-new", "multi-b-new"}


def test_breakdown_and_additional_filters_stay_inside_the_frozen_set(engine):
    with Session(engine) as db:
        _seed(db)
        summary = dashboard_new_since_previous(db)
        token = summary["comparison_context"]

        first_seen = list_dashboard_new_opportunities(
            db,
            comparison_context=token,
            comparison_kind="first_seen",
            filters=_filters(),
            page=1,
            page_size=20,
            sort="last_seen_at",
            order="desc",
        )
        reappeared = list_dashboard_new_opportunities(
            db,
            comparison_context=token,
            comparison_kind="reappeared",
            filters=_filters(),
            page=1,
            page_size=20,
            sort="last_seen_at",
            order="desc",
        )
        high_only = list_dashboard_new_opportunities(
            db,
            comparison_context=token,
            comparison_kind="new_vs_previous",
            filters=_filters(severity="high"),
            page=1,
            page_size=20,
            sort="severity",
            order="desc",
        )

        assert [item["id"] for item in first_seen["items"]] == ["first-seen"]
        assert [item["id"] for item in reappeared["items"]] == ["reappeared"]
        assert high_only["total"] == 1
        assert high_only["items"][0]["id"] == "reappeared"


def test_old_context_remains_deterministic_after_a_new_success(engine):
    with Session(engine) as db:
        _seed(db)
        before = dashboard_new_since_previous(db)
        old_token = before["comparison_context"]

        a6 = _run("a6", "111111111111", 5)
        db.add(a6)
        db.flush()
        _observe(db, "continued", a6)
        db.commit()

        old_page = list_dashboard_new_opportunities(
            db,
            comparison_context=old_token,
            comparison_kind="new_vs_previous",
            filters=_filters(),
            page=1,
            page_size=50,
            sort="last_seen_at",
            order="desc",
        )
        after = dashboard_new_since_previous(db)

        assert old_page["total"] == 2
        assert {item["id"] for item in old_page["items"]} == {"first-seen", "reappeared"}
        assert after["comparison_context"] != old_token
        assert after["count"] == 0


def test_expired_and_tampered_contexts_fail_explicitly_instead_of_returning_zero(engine):
    with Session(engine) as db:
        runs = _seed(db)
        summary = dashboard_new_since_previous(db)
        token = summary["comparison_context"]

        runs["a2"].detailed_observations_available = False
        db.commit()
        with pytest.raises(DashboardComparisonContextError) as expired:
            list_dashboard_new_opportunities(
                db,
                comparison_context=token,
                comparison_kind="new_vs_previous",
                filters=_filters(),
                page=1,
                page_size=50,
                sort="last_seen_at",
                order="desc",
            )
        assert expired.value.status_code == 410
        assert expired.value.code == "COMPARISON_CONTEXT_EXPIRED"

        tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"
        with pytest.raises(DashboardComparisonContextError) as invalid:
            list_dashboard_new_opportunities(
                db,
                comparison_context=tampered,
                comparison_kind="new_vs_previous",
                filters=_filters(),
                page=1,
                page_size=50,
                sort="last_seen_at",
                order="desc",
            )
        assert invalid.value.status_code == 422
        assert invalid.value.code == "INVALID_COMPARISON_CONTEXT"
