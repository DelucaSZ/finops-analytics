from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.collections import router
from app.core.security import require_user
from app.db.base import Base
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.collection_comparison import (
    CollectionComparisonError,
    compare_collection_runs,
    previous_comparable_run,
)

START = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)


@pytest.fixture
def comparison_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                AwsAccount(
                    id=1,
                    name="Production",
                    aws_account_id="111111111111",
                    role_arn="role-prod",
                    external_id="test-prod",
                ),
                AwsAccount(
                    id=2,
                    name="Other",
                    aws_account_id="222222222222",
                    role_arn="role-other",
                    external_id="test-other",
                ),
            ]
        )
        db.add(Scan(id="scan-findings", account_id=1))
        db.flush()

        db.add_all(
            [
                CollectionRun(
                    id="baseline",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START,
                    finished_at=START + timedelta(minutes=3),
                    status="SUCCESS",
                    analyzer_version="v1",
                ),
                CollectionRun(
                    id="failed-between",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START + timedelta(days=1),
                    finished_at=START + timedelta(days=1, minutes=1),
                    status="FAILED",
                    analyzer_version="v2",
                ),
                CollectionRun(
                    id="other-account",
                    provider="aws",
                    account_id="222222222222",
                    started_at=START + timedelta(days=1, hours=12),
                    finished_at=START + timedelta(days=1, hours=12, minutes=1),
                    status="SUCCESS",
                    analyzer_version="v2",
                ),
                CollectionRun(
                    id="target",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START + timedelta(days=2),
                    finished_at=START + timedelta(days=2, minutes=4),
                    status="SUCCESS",
                    analyzer_version="v2",
                ),
                CollectionRun(
                    id="future-failed",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START + timedelta(days=3),
                    finished_at=START + timedelta(days=3, minutes=1),
                    status="FAILED",
                    analyzer_version="v2",
                ),
            ]
        )

        def finding(
            opportunity_id: str,
            fingerprint_char: str,
            *,
            rule_key: str = "test_rule",
            service: str = "EC2",
            status: str = "open",
            severity: str = "medium",
            savings: str = "10",
        ) -> Finding:
            return Finding(
                id=opportunity_id,
                fingerprint=fingerprint_char * 64,
                scan_id="scan-findings",
                account_id=1,
                rule_key=rule_key,
                service=service,
                region="sa-east-1",
                resource_id=opportunity_id,
                title=opportunity_id.upper(),
                description=f"{opportunity_id} description",
                evidence={},
                current_monthly_cost=Decimal(savings),
                estimated_monthly_savings=Decimal(savings),
                confidence="high",
                severity=severity,
                status=status,
                first_seen_at=START,
                last_seen_at=START + timedelta(days=2),
            )

        db.add_all(
            [
                finding("opp-a", "a"),
                finding(
                    "opp-b",
                    "b",
                    service="RDS",
                    status="rejected",
                    severity="high",
                    savings="180",
                ),
                finding(
                    "opp-c",
                    "c",
                    rule_key="ec2_stopped_with_ebs",
                    status="treated",
                    savings="20",
                ),
                finding("opp-d", "d", service="EBS", severity="low", savings="30"),
                finding("opp-e", "e", severity="high", savings="40"),
            ]
        )
        db.flush()

        def observation(
            opportunity_id: str,
            run_id: str,
            *,
            severity: str,
            savings: str,
            cost: str,
            evidence: dict | None = None,
        ) -> OpportunityObservation:
            run_time = START if run_id == "baseline" else START + timedelta(days=2)
            return OpportunityObservation(
                opportunity_id=opportunity_id,
                collection_run_id=run_id,
                observed_at=run_time,
                severity=severity,
                current_monthly_cost=Decimal(cost),
                estimated_monthly_savings=Decimal(savings),
                confidence="high",
                evidence=evidence or {},
            )

        stable_ec2 = {
            "instance_type": "m6i.large",
            "volumes": [{"volume_id": "vol-1", "size_gib": 100, "type": "gp3"}],
            "policy_config": {
                "minimum_stopped_days": 7,
                "minimum_monthly_savings_usd": 1,
            },
        }
        db.add_all(
            [
                observation("opp-a", "baseline", severity="medium", savings="10", cost="10"),
                observation("opp-b", "baseline", severity="medium", savings="100", cost="120"),
                observation(
                    "opp-c",
                    "baseline",
                    severity="medium",
                    savings="20",
                    cost="20",
                    evidence=stable_ec2 | {"stopped_days": 14},
                ),
                observation("opp-d", "baseline", severity="low", savings="30", cost="30"),
                observation("opp-a", "target", severity="medium", savings="10", cost="10"),
                observation("opp-b", "target", severity="high", savings="180", cost="200"),
                observation(
                    "opp-c",
                    "target",
                    severity="medium",
                    savings="20",
                    cost="20",
                    evidence=stable_ec2 | {"stopped_days": 15},
                ),
                observation("opp-e", "target", severity="high", savings="40", cost="40"),
            ]
        )
        db.commit()

    yield engine
    engine.dispose()


def compare(
    engine,
    *,
    category="NEW",
    baseline_id="baseline",
    target_id="target",
    page_size=50,
):
    with Session(engine) as db:
        baseline = db.get(CollectionRun, baseline_id) if baseline_id else None
        target = db.get(CollectionRun, target_id)
        return compare_collection_runs(
            db,
            target,
            baseline=baseline,
            category=category,
            page=1,
            page_size=page_size,
        )


def test_classifies_new_persistent_no_longer_and_changed(comparison_db):
    result = compare(comparison_db, category="CHANGED")
    assert result["summary"] == {
        "baseline_total": 4,
        "target_total": 4,
        "new": 1,
        "persistent": 2,
        "no_longer_detected": 1,
        "changed": 1,
    }
    item = result["items"][0]
    assert item["opportunity_id"] == "opp-b"
    assert item["lifecycle_status"] == "rejected"
    assert "severity" in item["change_types"]
    assert "financial_impact" in item["change_types"]


def test_natural_elapsed_duration_does_not_create_false_changed(comparison_db):
    result = compare(comparison_db, category="PERSISTENT")
    items = {item["opportunity_id"]: item for item in result["items"]}
    assert set(items) == {"opp-a", "opp-c"}
    assert items["opp-c"]["lifecycle_status"] == "treated"
    assert items["opp-c"]["change_types"] == []


def test_new_and_no_longer_detected_keep_lifecycle_separate(comparison_db):
    new_items = compare(comparison_db, category="NEW")["items"]
    assert [item["opportunity_id"] for item in new_items] == ["opp-e"]

    gone = compare(comparison_db, category="NO_LONGER_DETECTED")["items"]
    assert [item["opportunity_id"] for item in gone] == ["opp-d"]
    assert gone[0]["lifecycle_status"] == "open"

    with Session(comparison_db) as db:
        assert db.get(Finding, "opp-d").status == "open"
        assert db.get(Finding, "opp-b").status == "rejected"
        assert db.get(Finding, "opp-c").status == "treated"


def test_financial_summary_uses_monthly_savings_only(comparison_db):
    financial = compare(comparison_db)["financial_summary"]
    assert financial["metric"] == "estimated_monthly_savings"
    assert financial["currency"] == "USD"
    assert financial["period"] == "month"
    assert financial["baseline_total"] == Decimal("160")
    assert financial["target_total"] == Decimal("250")
    assert financial["delta"] == Decimal("90")
    assert financial["delta_percent"] == Decimal("56.3")


def test_rules_version_warning_does_not_change_classification(comparison_db):
    result = compare(comparison_db, category="PERSISTENT")
    assert result["rules_version_warning"]["code"] == "RULES_VERSION_CHANGED"
    assert result["summary"]["persistent"] == 2
    assert result["summary"]["changed"] == 1


def test_automatic_baseline_skips_failed_and_other_account_runs(comparison_db):
    with Session(comparison_db) as db:
        target = db.get(CollectionRun, "target")
        baseline = previous_comparable_run(db, target)
        assert baseline.id == "baseline"

        result = compare_collection_runs(
            db,
            target,
            baseline=None,
            category="NEW",
            page=1,
            page_size=50,
        )
        assert result["baseline"]["id"] == "baseline"


@pytest.mark.parametrize(
    ("baseline_id", "code"),
    [
        ("failed-between", "COLLECTION_NOT_SUCCESSFUL"),
        ("other-account", "DIFFERENT_ACCOUNT"),
    ],
)
def test_invalid_comparisons_are_business_errors(comparison_db, baseline_id, code):
    with pytest.raises(CollectionComparisonError) as exc:
        compare(comparison_db, baseline_id=baseline_id)
    assert exc.value.code == code


def test_failed_target_is_rejected(comparison_db):
    with pytest.raises(CollectionComparisonError) as exc:
        compare(comparison_db, target_id="future-failed")
    assert exc.value.code == "COLLECTION_NOT_SUCCESSFUL"


def test_detail_pagination_is_server_side(comparison_db):
    result = compare(comparison_db, category="PERSISTENT", page_size=1)
    assert result["total"] == 2
    assert result["total_pages"] == 2
    assert len(result["items"]) == 1


def test_comparison_uses_two_observation_queries_without_n_plus_one(comparison_db):
    statements: list[str] = []
    with Session(comparison_db) as db:
        baseline = db.get(CollectionRun, "baseline")
        target = db.get(CollectionRun, "target")

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            if "opportunity_observations" in statement.lower():
                statements.append(statement.lower())

        event.listen(comparison_db, "before_cursor_execute", capture)
        try:
            result = compare_collection_runs(
                db,
                target,
                baseline=baseline,
                category="CHANGED",
                page=1,
                page_size=50,
            )
        finally:
            event.remove(comparison_db, "before_cursor_execute", capture)

    assert result["summary"]["changed"] == 1
    assert len(statements) == 2
    assert all("collection_run_id" in statement for statement in statements)


def test_http_contract_and_clear_incompatible_error(comparison_db):
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(comparison_db) as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_user] = lambda: object()

    with TestClient(app) as client:
        response = client.get(
            "/collections/target/compare",
            params={"baseline_id": "baseline", "category": "CHANGED"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["new"] == 1
        assert body["items"][0]["lifecycle_status"] == "rejected"
        assert body["rules_version_warning"]["code"] == "RULES_VERSION_CHANGED"

        incompatible = client.get(
            "/collections/target/compare",
            params={"baseline_id": "other-account"},
        )
        assert incompatible.status_code == 409
        assert "DIFFERENT_ACCOUNT" in incompatible.json()["detail"]
        assert "contas diferentes" in incompatible.json()["detail"]


def test_no_baseline_is_not_an_error(comparison_db):
    with Session(comparison_db) as db:
        target = db.get(CollectionRun, "baseline")
        result = compare_collection_runs(
            db,
            target,
            baseline=None,
            category="NEW",
            page=1,
            page_size=50,
        )
    assert result["available"] is False
    assert result["reason"] == "NO_BASELINE"
    assert result["summary"] is None
    assert result["items"] == []
