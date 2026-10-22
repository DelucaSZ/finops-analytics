from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app import worker
from app.api.routes.opportunities import router as opportunities_router
from app.api.routes.opportunity_discovery import router as discovery_router
from app.core.security import require_user
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import CollectionScopeExecution
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.collector_types import CollectedFinding
from app.services.opportunity_query import OpportunityFilters, list_opportunities, opportunity_stats
from app.services.opportunity_run_comparison import opportunity_run_changes

START = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


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


def _collected(resource_id: str = "i-1") -> CollectedFinding:
    return CollectedFinding(
        rule_key="test_rule",
        service="EC2",
        region="sa-east-1",
        resource_id=resource_id,
        resource_name=resource_id,
        resource_type="EC2 Instance",
        title="Test opportunity",
        description="Test opportunity",
        evidence={"resource": resource_id},
        current_monthly_cost=Decimal("20"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        severity="medium",
    )


def _aws_account(db: Session) -> AwsAccount:
    account = AwsAccount(
        name="Production",
        aws_account_id="111111111111",
        role_arn="arn:aws:iam::111111111111:role/DeepOps",
        external_id="test",
        regions=["sa-east-1"],
    )
    db.add(account)
    db.commit()
    return account


def _scan_run(
    db: Session,
    account: AwsAccount,
    run_id: str,
    started_at: datetime,
) -> tuple[Scan, CollectionRun]:
    scan = Scan(
        id=f"scan-{run_id}",
        account_id=account.id,
        cloud_account_id=account.cloud_account_id,
        status="running",
        started_at=started_at,
    )
    db.add(scan)
    db.flush()
    run = CollectionRun(
        id=run_id,
        scan_id=scan.id,
        provider="aws",
        account_id=account.aws_account_id,
        scope={"regions": ["sa-east-1"]},
        started_at=started_at,
        status=CollectionRunStatus.RUNNING,
        analyzer_version="v1",
    )
    db.add(run)
    db.commit()
    return scan, run


def test_persistence_keeps_first_run_and_does_not_regress_last_run_out_of_order(engine):
    with Session(engine) as db:
        account = _aws_account(db)
        scan_a, run_a = _scan_run(db, account, "run-a", START)
        scan_c, run_c = _scan_run(db, account, "run-c", START + timedelta(days=2))
        scan_b, run_b = _scan_run(db, account, "run-b", START + timedelta(days=1))

        worker.persist_findings(
            db,
            scan_a,
            run_a,
            [_collected()],
            ["test_rule"],
            observed_at=START,
        )
        db.commit()
        finding = db.scalar(select(Finding))
        assert finding.first_seen_collection_run_id == run_a.id
        assert finding.last_seen_collection_run_id == run_a.id

        worker.persist_findings(
            db,
            scan_c,
            run_c,
            [_collected()],
            ["test_rule"],
            observed_at=START + timedelta(days=2),
        )
        db.commit()
        worker.persist_findings(
            db,
            scan_b,
            run_b,
            [_collected()],
            ["test_rule"],
            observed_at=START + timedelta(days=1),
        )
        db.commit()

        finding = db.scalar(select(Finding))
        assert finding.first_seen_collection_run_id == run_a.id
        assert finding.last_seen_collection_run_id == run_c.id
        assert finding.scan_id == scan_c.id
        assert finding.total_occurrence_count == 3
        assert finding.first_seen_at.replace(tzinfo=UTC) == START
        assert finding.last_seen_at.replace(tzinfo=UTC) == START + timedelta(days=2)


def _seed_comparison(db: Session) -> dict[str, CollectionRun]:
    runs = {
        "run-1": CollectionRun(
            id="run-1",
            provider="aws",
            account_id="111111111111",
            scope={"regions": ["sa-east-1"]},
            started_at=START,
            finished_at=START + timedelta(minutes=1),
            status=CollectionRunStatus.SUCCESS,
            analyzer_version="v1",
        ),
        "run-2": CollectionRun(
            id="run-2",
            provider="aws",
            account_id="111111111111",
            scope={"regions": ["sa-east-1"]},
            started_at=START + timedelta(days=1),
            finished_at=START + timedelta(days=1, minutes=1),
            status=CollectionRunStatus.SUCCESS,
            analyzer_version="v1",
        ),
        "run-3": CollectionRun(
            id="run-3",
            provider="aws",
            account_id="111111111111",
            scope={"regions": ["sa-east-1"]},
            started_at=START + timedelta(days=2),
            finished_at=START + timedelta(days=2, minutes=1),
            status=CollectionRunStatus.SUCCESS,
            analyzer_version="v2",
        ),
    }
    db.add_all(runs.values())
    db.flush()

    first_seen_run = {
        "continued": "run-1",
        "reappeared": "run-1",
        "gone": "run-2",
        "first-seen": "run-3",
        "rejected-reappeared": "run-1",
    }
    status = {
        "continued": "open",
        "reappeared": "open",
        "gone": "open",
        "first-seen": "open",
        "rejected-reappeared": "rejected",
    }
    first_seen_at = {
        "continued": START,
        "reappeared": START,
        "gone": START + timedelta(days=1),
        "first-seen": START + timedelta(days=2),
        "rejected-reappeared": START,
    }
    for index, opportunity_id in enumerate(first_seen_run, start=1):
        db.add(
            Finding(
                id=opportunity_id,
                fingerprint=f"{index:064x}",
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
                status=status[opportunity_id],
                first_seen_at=first_seen_at[opportunity_id],
                last_seen_at=START + timedelta(days=2),
                first_seen_collection_run_id=first_seen_run[opportunity_id],
                last_seen_collection_run_id=("run-2" if opportunity_id == "gone" else "run-3"),
                total_occurrence_count=2,
            )
        )
    db.flush()

    observed = {
        "run-1": ["continued", "reappeared", "rejected-reappeared"],
        "run-2": ["continued", "gone"],
        "run-3": ["continued", "reappeared", "first-seen", "rejected-reappeared"],
    }
    for run_id, opportunity_ids in observed.items():
        run = runs[run_id]
        for opportunity_id in opportunity_ids:
            db.add(
                OpportunityObservation(
                    opportunity_id=opportunity_id,
                    collection_run_id=run_id,
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

    db.add(
        CollectionScopeExecution(
            id="scope-run-3",
            collection_run_id="run-3",
            provider="aws",
            account_id="111111111111",
            region="sa-east-1",
            service="EC2",
            rule_key="test_rule",
            status="SUCCESS",
            started_at=runs["run-3"].started_at,
            finished_at=runs["run-3"].finished_at,
            resources_examined=5,
        )
    )
    db.commit()
    return runs


def test_run_comparison_separates_first_seen_reappeared_and_continued(engine):
    with Session(engine) as db:
        runs = _seed_comparison(db)
        result = opportunity_run_changes(db, runs["run-3"])

        assert result["comparable"] is True
        assert result["baseline_run_id"] == "run-2"
        assert result["rules_version_changed"] is True
        assert result["summary"] == {
            "observed": 4,
            "first_seen": 1,
            "new_vs_previous": 3,
            "reappeared": 2,
            "continued": 1,
            "no_longer_detected": 1,
            "operational_new_vs_previous": 2,
        }
        assert {warning["code"] for warning in result["warnings"]} == {"RULES_VERSION_CHANGED"}


def test_first_collection_is_not_classified_as_new_vs_previous(engine):
    with Session(engine) as db:
        runs = _seed_comparison(db)
        result = opportunity_run_changes(db, runs["run-1"])

        assert result["comparable"] is False
        assert result["reason"] == "NO_BASELINE"
        assert result["baseline_run_id"] is None
        assert result["summary"]["first_seen"] == 3
        assert result["summary"]["new_vs_previous"] == 0
        assert result["summary"]["reappeared"] == 0


def test_no_longer_detected_requires_authoritative_target_coverage(engine):
    with Session(engine) as db:
        runs = _seed_comparison(db)
        scope = db.get(CollectionScopeExecution, "scope-run-3")
        scope.status = "FAILED"
        db.commit()

        result = opportunity_run_changes(db, runs["run-3"])
        assert result["partial_coverage"] is True
        assert result["summary"]["no_longer_detected"] == 0
        assert "PARTIAL_COVERAGE" in {warning["code"] for warning in result["warnings"]}


def test_temporal_filters_are_semi_open_and_stats_share_the_same_semantics(engine):
    with Session(engine) as db:
        runs = _seed_comparison(db)
        result = list_opportunities(
            db,
            OpportunityFilters(
                first_seen_from=START + timedelta(days=1),
                first_seen_to=START + timedelta(days=2),
                archive_state="active",
            ),
            page=1,
            page_size=50,
            sort="first_seen_at",
            order="asc",
        )
        assert {item["id"] for item in result["items"]} == {"gone"}

        stats = opportunity_stats(
            db,
            OpportunityFilters(
                first_seen_from=START + timedelta(days=1),
                first_seen_to=START + timedelta(days=2),
                archive_state="active",
            ),
        )
        assert stats == {"open": 1, "treated": 0, "rejected": 0}

        current = list_opportunities(
            db,
            OpportunityFilters(
                first_seen_from=START + timedelta(days=2),
                current=True,
                archive_state="active",
            ),
            page=1,
            page_size=50,
            sort="first_seen_at",
            order="asc",
        )
        assert {item["id"] for item in current["items"]} == {"first-seen"}
        assert runs["run-3"].id == "run-3"


def test_http_discovery_and_normal_opportunity_filters_are_consistent(engine):
    with Session(engine) as db:
        _seed_comparison(db)

    app = FastAPI()
    app.include_router(opportunities_router)
    app.include_router(discovery_router)

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_user] = lambda: object()

    with TestClient(app) as client:
        changes = client.get("/collections/run-3/opportunity-changes")
        assert changes.status_code == 200
        assert changes.json()["summary"]["first_seen"] == 1
        assert changes.json()["summary"]["reappeared"] == 2

        relative = client.get(
            "/collections/run-3/opportunities",
            params={"discovery_type": "reappeared", "page_size": 50},
        )
        assert relative.status_code == 200
        assert {item["id"] for item in relative.json()["items"]} == {
            "reappeared",
            "rejected-reappeared",
        }

        normal = client.get(
            "/opportunities",
            params={
                "collection_run_id": "run-3",
                "discovery_type": "new_vs_previous",
                "page_size": 50,
            },
        )
        assert normal.status_code == 200
        assert {item["id"] for item in normal.json()["items"]} == {
            "reappeared",
            "first-seen",
            "rejected-reappeared",
        }

        historical_new = client.get(
            "/opportunities",
            params={"first_seen_collection_run_id": "run-3", "page_size": 50},
        )
        assert historical_new.status_code == 200
        assert {item["id"] for item in historical_new.json()["items"]} == {"first-seen"}

        invalid_range = client.get(
            "/opportunities",
            params={
                "first_seen_from": (START + timedelta(days=2)).isoformat(),
                "first_seen_to": (START + timedelta(days=1)).isoformat(),
            },
        )
        assert invalid_range.status_code == 422

        no_baseline = client.get(
            "/opportunities",
            params={
                "collection_run_id": "run-1",
                "discovery_type": "new_vs_previous",
                "page_size": 50,
            },
        )
        assert no_baseline.status_code == 200
        assert no_baseline.json()["total"] == 0
