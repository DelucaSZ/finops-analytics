from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import CollectionScopeExecution
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.opportunity_run_comparison import (
    list_run_opportunities,
    opportunity_run_changes,
)

START = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


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


def _finding(opportunity_id: str, first_run: str, *, status: str = "open") -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=f"{len(opportunity_id):064x}",
        provider="aws",
        account_id="111111111111",
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
        severity="medium",
        status=status,
        first_seen_at=START,
        last_seen_at=START + timedelta(days=1),
        first_seen_collection_run_id=first_run,
        last_seen_collection_run_id="run-2",
        total_occurrence_count=2,
    )


def _observation(opportunity_id: str, run_id: str, observed_at: datetime) -> OpportunityObservation:
    return OpportunityObservation(
        opportunity_id=opportunity_id,
        collection_run_id=run_id,
        observed_at=observed_at,
        severity="medium",
        current_monthly_cost=Decimal("20"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        provider_metadata={},
        evidence={},
    )


def _seed(db: Session) -> tuple[CollectionRun, CollectionRun]:
    baseline = CollectionRun(
        id="run-1",
        provider="aws",
        account_id="111111111111",
        scope={"regions": ["sa-east-1"]},
        started_at=START,
        finished_at=START + timedelta(minutes=1),
        status=CollectionRunStatus.SUCCESS,
        analyzer_version="v1",
        opportunities_found=2,
    )
    target = CollectionRun(
        id="run-2",
        provider="aws",
        account_id="111111111111",
        scope={"regions": ["sa-east-1"]},
        started_at=START + timedelta(days=1),
        finished_at=START + timedelta(days=1, minutes=1),
        status=CollectionRunStatus.SUCCESS,
        analyzer_version="v2",
        opportunities_found=3,
    )
    db.add_all([baseline, target])
    db.flush()

    continued = _finding("continued", "run-1")
    gone = _finding("gone", "run-1")
    first_seen = _finding("first-seen", "run-2")
    rejected_reappeared = _finding("rejected-reappeared", "run-1", status="rejected")
    db.add_all([continued, gone, first_seen, rejected_reappeared])
    db.flush()

    db.add_all(
        [
            _observation("continued", "run-1", baseline.started_at),
            _observation("gone", "run-1", baseline.started_at),
            _observation("continued", "run-2", target.started_at),
            _observation("first-seen", "run-2", target.started_at),
            _observation("rejected-reappeared", "run-2", target.started_at),
        ]
    )
    db.add_all(
        [
            CollectionScopeExecution(
                id="scope-success",
                collection_run_id="run-2",
                provider="aws",
                account_id="111111111111",
                region="sa-east-1",
                service="EC2",
                rule_key="test_rule",
                status="SUCCESS",
                started_at=target.started_at,
                finished_at=target.finished_at,
                resources_examined=4,
            ),
            CollectionScopeExecution(
                id="scope-skipped",
                collection_run_id="run-2",
                provider="aws",
                account_id="111111111111",
                region="us-east-1",
                service="EC2",
                rule_key="other_rule",
                status="SKIPPED",
                started_at=target.started_at,
                finished_at=target.finished_at,
                resources_examined=0,
                error_detail="safe skipped detail",
            ),
        ]
    )
    db.commit()
    return baseline, target


def test_changes_expose_baseline_coverage_and_exact_semantics(engine):
    with Session(engine) as db:
        _, target = _seed(db)
        result = opportunity_run_changes(db, target)

        assert result["comparison_status"] == "PARTIAL"
        assert result["baseline"]["id"] == "run-1"
        assert result["rules_version_changed"] is True
        assert result["coverage"] == {
            "total_scopes": 2,
            "successful_scopes": 1,
            "failed_scopes": 0,
            "skipped_scopes": 1,
            "comparable_scopes": 1,
        }
        assert result["summary"]["observed"] == 3
        assert result["summary"]["first_seen"] == 1
        assert result["summary"]["new_vs_previous"] == 2
        assert result["summary"]["reappeared"] == 1
        assert result["summary"]["continued"] == 1
        assert result["summary"]["no_longer_detected"] == 1
        assert result["scope_issues"][0]["status"] == "SKIPPED"

        reappeared = list_run_opportunities(
            db,
            target,
            discovery_type="reappeared",
            page=1,
            page_size=50,
            include_archived=True,
        )
        assert reappeared["total"] == result["summary"]["reappeared"]
        assert {item["id"] for item in reappeared["items"]} == {"rejected-reappeared"}


def test_retention_expiry_preserves_known_aggregate_without_fake_detail(engine):
    with Session(engine) as db:
        _, target = _seed(db)
        target.detailed_observations_available = False
        target.opportunities_found = 37
        db.commit()

        changes = opportunity_run_changes(db, target)
        assert changes["comparison_status"] == "EXPIRED"
        assert changes["target_details_available"] is False
        assert changes["summary"]["observed"] == 37

        page = list_run_opportunities(
            db,
            target,
            discovery_type="observed",
            page=1,
            page_size=50,
            include_archived=True,
        )
        assert page["reason"] == "TARGET_OBSERVATIONS_EXPIRED"
        assert page["total"] == 0
