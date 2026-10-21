from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.opportunities import router
from app.db.base import Base
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_archive_history import OpportunityArchiveHistory
from app.models.opportunity_history_cycle import (
    OpportunityHistoryCycle,
    OpportunityHistoryCycleStatus,
)
from app.models.opportunity_history_snapshot import OpportunityHistorySnapshot
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.opportunity_history import OpportunityHistoryCycleService

OCT_01 = datetime(2026, 10, 1, tzinfo=UTC)
NOV_01 = datetime(2026, 11, 1, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _finding(
    opportunity_id: str,
    *,
    provider: str = "aws",
    account_id: str = "111111111111",
    status: str = "open",
    severity: str = "medium",
    rule_key: str = "ec2_stopped",
    currency: str = "USD",
) -> Finding:
    fingerprint = (opportunity_id.encode("utf-8").hex() + ("f" * 64))[:64]
    return Finding(
        id=opportunity_id,
        fingerprint=fingerprint,
        provider=provider,
        account_id=account_id,
        rule_key=rule_key,
        service="EC2" if provider == "aws" else "Compute",
        region="sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        resource_type="instance",
        resource_id=f"resource-{opportunity_id}",
        resource_name=opportunity_id,
        title=f"Opportunity {opportunity_id}",
        description="Bulk archive test",
        evidence={},
        current_monthly_cost=Decimal("100"),
        estimated_monthly_savings=Decimal("40"),
        currency=currency,
        confidence="high",
        severity=severity,
        status=status,
        presence_status="active",
        first_seen_at=OCT_01,
        last_seen_at=OBSERVED_AT,
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
            name="Archive Admin",
            email="archive-bulk@example.com",
            password_hash="unused",
            role="admin",
        )
        db.add(admin)
        db.add_all(
            [
                _finding("aws-open-1"),
                _finding("aws-open-2", severity="low"),
                _finding("aws-treated", status="treated", severity="high"),
                _finding(
                    "oci-rejected",
                    provider="oci",
                    account_id="ocid1.tenancy.oc1..bulk",
                    status="rejected",
                    rule_key="oci_compute_idle",
                    currency="BRL",
                ),
            ]
        )
        db.flush()
        treated = db.get(Finding, "aws-treated")
        treated.treated_at = OBSERVED_AT
        treated.treated_by = admin.id
        rejected = db.get(Finding, "oci-rejected")
        rejected.rejected_at = OBSERVED_AT
        rejected.rejected_by = admin.id
        rejected.rejection_reason = "RESOURCE_REQUIRED"
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
        yield http, engine, app
    engine.dispose()


def test_bulk_archive_deduplicates_ids_is_idempotent_and_preserves_lifecycle(client):
    http, engine, _ = client
    assert http.post("/opportunities/aws-open-2/archive").status_code == 200

    response = http.post(
        "/opportunities/bulk/archive",
        json={
            "opportunity_ids": [
                "aws-open-1",
                "aws-open-1",
                "aws-open-2",
                "aws-treated",
                "oci-rejected",
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested"] == 4
    assert body["matched"] == 4
    assert body["archived"] == 3
    assert body["already_archived"] == 1
    assert body["failed"] == 0
    assert body["correlation_id"]

    with Session(engine) as db:
        findings = {item.id: item for item in db.scalars(select(Finding)).all()}
        assert findings["aws-open-1"].status == "open"
        assert findings["aws-treated"].status == "treated"
        assert findings["oci-rejected"].status == "rejected"
        assert all(item.presence_status == "active" for item in findings.values())
        assert findings["aws-treated"].treated_at is not None
        assert findings["oci-rejected"].rejected_at is not None

        bulk_history = list(
            db.scalars(
                select(OpportunityArchiveHistory).where(
                    OpportunityArchiveHistory.context["correlation_id"].as_string()
                    == body["correlation_id"]
                )
            )
        )
        assert len(bulk_history) == 3
        assert {event.context["operation"] for event in bulk_history} == {"bulk"}
        assert len({event.occurred_at for event in bulk_history}) == 1
        audit_count = int(
            db.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "opportunity.bulk_archive",
                    AuditEvent.correlation_id == body["correlation_id"],
                )
            )
            or 0
        )
        assert audit_count == 1


def test_bulk_archive_missing_id_rolls_back_and_limit_is_enforced(client):
    http, engine, _ = client

    response = http.post(
        "/opportunities/bulk/archive",
        json={"opportunity_ids": ["aws-open-1", "does-not-exist"]},
    )
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.get(Finding, "aws-open-1").archived_at is None

    response = http.post(
        "/opportunities/bulk/archive",
        json={"opportunity_ids": [f"id-{index}" for index in range(501)]},
    )
    assert response.status_code == 422


def test_archive_preview_and_execution_share_server_side_filter_semantics(client):
    http, engine, _ = client
    assert http.post("/opportunities/aws-open-2/archive").status_code == 200
    payload = {
        "filters": {
            "provider": "aws",
            "status": "open",
            "severity": "medium",
            "search": "aws-open",
        }
    }

    preview = http.post("/opportunities/archive-preview", json=payload)
    assert preview.status_code == 200
    data = preview.json()
    assert data["matched"] == 1
    assert data["to_archive"] == 1
    assert data["already_archived"] == 0
    assert data["by_status"] == {"open": 1}
    assert data["by_provider"] == {"aws": 1}
    assert data["currencies"][0]["currency"] == "USD"

    result = http.post("/opportunities/archive-by-filter", json=payload)
    assert result.status_code == 200
    body = result.json()
    assert body["archived"] == 1
    assert body["filter_hash"] == data["filter_hash"]

    with Session(engine) as db:
        assert db.get(Finding, "aws-open-1").archived_at is not None
        # A previously archived row is never targeted/mutated by archive-by-filter.
        previous = db.get(Finding, "aws-open-2").archived_at
    assert http.post("/opportunities/archive-by-filter", json=payload).status_code == 200
    with Session(engine) as db:
        assert db.get(Finding, "aws-open-2").archived_at == previous


def test_empty_filter_requires_explicit_archive_all_confirmation(client):
    http, engine, _ = client

    preview = http.post("/opportunities/archive-preview", json={"filters": {}})
    assert preview.status_code == 422
    assert "archive_all=true" in preview.json()["detail"]

    execution = http.post("/opportunities/archive-by-filter", json={"filters": {}})
    assert execution.status_code == 422

    confirmed = http.post(
        "/opportunities/archive-by-filter",
        json={"filters": {}, "archive_all": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["archived"] == 4
    with Session(engine) as db:
        active_count = int(
            db.scalar(select(func.count(Finding.id)).where(Finding.archived_at.is_(None))) or 0
        )
        assert active_count == 0


def _add_cycle_data(engine, *, running: bool = False) -> str:
    with Session(engine) as db:
        finding = db.get(Finding, "aws-open-1")
        success = CollectionRun(
            id="run-success",
            provider="aws",
            account_id=finding.account_id,
            started_at=OBSERVED_AT,
            finished_at=OBSERVED_AT,
            status=CollectionRunStatus.SUCCESS.value,
        )
        failed = CollectionRun(
            id="run-failed",
            provider="aws",
            account_id=finding.account_id,
            started_at=datetime(2026, 10, 19, tzinfo=UTC),
            finished_at=datetime(2026, 10, 19, tzinfo=UTC),
            status=CollectionRunStatus.FAILED.value,
        )
        db.add_all([success, failed])
        if running:
            db.add(
                CollectionRun(
                    id="run-running",
                    provider="aws",
                    account_id=finding.account_id,
                    started_at=datetime(2026, 10, 21, tzinfo=UTC),
                    status=CollectionRunStatus.RUNNING.value,
                )
            )
        db.flush()
        db.add(
            OpportunityObservation(
                opportunity_id=finding.id,
                collection_run_id=success.id,
                observed_at=success.started_at,
                severity=finding.severity,
                current_monthly_cost=finding.current_monthly_cost,
                estimated_monthly_savings=finding.estimated_monthly_savings,
                currency=finding.currency,
                confidence=finding.confidence,
                provider_metadata={},
                evidence={},
            )
        )
        cycle = OpportunityHistoryCycleService.create_cycle(
            db,
            period_start=OCT_01,
            period_end=NOV_01,
            label="10/2026",
        )
        db.commit()
        return cycle.id


def test_period_close_previews_failures_then_snapshots_and_archives_atomically(client):
    http, engine, _ = client
    cycle_id = _add_cycle_data(engine)
    payload = {"cycle_id": cycle_id, "filters": {}, "archive_all": True}

    preview = http.post("/opportunities/period-close/preview", json=payload)
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["snapshots_to_create"] == 1
    assert preview_body["collection_runs"] == 2
    assert preview_body["failed_collection_runs"] == 1
    assert preview_body["running_collection_runs"] == 0
    assert preview_body["archive"]["to_archive"] == 4

    response = http.post("/opportunities/period-close", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["cycle_closed"] is True
    assert body["snapshots_created"] == 1
    assert body["archived"] == 4
    assert body["failed_collection_runs"] == 1

    with Session(engine) as db:
        cycle = db.get(OpportunityHistoryCycle, cycle_id)
        assert cycle.status == OpportunityHistoryCycleStatus.CLOSED.value
        snapshot = db.scalar(
            select(OpportunityHistorySnapshot).where(
                OpportunityHistorySnapshot.cycle_id == cycle_id
            )
        )
        assert snapshot is not None
        assert snapshot.opportunity_id == "aws-open-1"
        # Snapshot captured the pre-archive operational state and remains independent.
        assert snapshot.archived is False
        assert db.get(Finding, "aws-open-1").archived_at is not None
        period_audit = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "opportunity.period_close",
                AuditEvent.correlation_id == body["correlation_id"],
            )
        )
        assert period_audit is not None
        histories = list(
            db.scalars(
                select(OpportunityArchiveHistory).where(
                    OpportunityArchiveHistory.context["correlation_id"].as_string()
                    == body["correlation_id"]
                )
            )
        )
        assert len(histories) == 4
        assert {event.context["cycle_id"] for event in histories} == {cycle_id}
        assert {event.context["operation"] for event in histories} == {"period_close"}


def test_period_close_is_blocked_by_running_collections_without_mutation(client):
    http, engine, _ = client
    cycle_id = _add_cycle_data(engine, running=True)
    payload = {"cycle_id": cycle_id, "filters": {}, "archive_all": True}

    preview = http.post("/opportunities/period-close/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["running_collection_runs"] == 1

    response = http.post("/opportunities/period-close", json=payload)
    assert response.status_code == 409
    with Session(engine) as db:
        cycle = db.get(OpportunityHistoryCycle, cycle_id)
        assert cycle.status == OpportunityHistoryCycleStatus.OPEN.value
        snapshot_count = int(db.scalar(select(func.count(OpportunityHistorySnapshot.id))) or 0)
        archived_count = int(
            db.scalar(select(func.count(Finding.id)).where(Finding.archived_at.is_not(None))) or 0
        )
        assert snapshot_count == 0
        assert archived_count == 0


def test_bulk_archive_requires_authentication(client):
    _, _, app = client
    with TestClient(app) as anonymous:
        response = anonymous.post(
            "/opportunities/bulk/archive",
            json={"opportunity_ids": ["aws-open-1"]},
        )
    assert response.status_code in {401, 403}
