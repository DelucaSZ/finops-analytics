from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes.opportunities import router as opportunities_router
from app.db.base import Base
from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_presence_history import (
    OpportunityPresenceHistory,
    OpportunityPresenceReason,
)
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session
from app.services.opportunity_reconciliation import (
    reactivate_presence_from_observation,
    reconcile_opportunity_presence,
)

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine():
    database = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(database)
    yield database
    database.dispose()


@pytest.fixture
def api(engine):
    with Session(engine) as db:
        admin = User(
            name="Admin",
            email="presence-history@example.com",
            password_hash="unused",
            role="admin",
        )
        db.add(admin)
        db.commit()
        _, token = new_session(db, admin)
        db.commit()

    app = FastAPI()
    app.include_router(opportunities_router)

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
        yield http


def _run(
    db: Session,
    suffix: str,
    when: datetime,
    *,
    provider: str = "aws",
    account_id: str = "account-1",
    status: str = "SUCCESS",
) -> CollectionRun:
    run = CollectionRun(
        id=f"run-{suffix}",
        provider=provider,
        account_id=account_id,
        scope={"regions": ["sa-east-1"]},
        started_at=when,
        finished_at=when + timedelta(minutes=1),
        status=status,
    )
    db.add(run)
    db.flush()
    return run


def _scope(
    db: Session,
    run: CollectionRun,
    *,
    rule_key: str = "ebs_unattached",
    region: str = "sa-east-1",
    status: str = CollectionScopeExecutionStatus.SUCCESS.value,
) -> CollectionScopeExecution:
    scope = CollectionScopeExecution(
        id=f"scope-{run.id}-{rule_key}-{region}",
        collection_run_id=run.id,
        provider=run.provider,
        account_id=run.account_id,
        region=region,
        service="EC2",
        rule_key=rule_key,
        status=status,
        started_at=run.started_at,
        finished_at=run.finished_at or run.started_at,
    )
    db.add(scope)
    db.flush()
    return scope


def _finding(
    db: Session,
    suffix: str,
    *,
    provider: str = "aws",
    account_id: str = "account-1",
    status: str = "open",
    presence_status: str = OpportunityPresenceStatus.ACTIVE.value,
) -> Finding:
    finding = Finding(
        id=f"finding-{suffix}",
        fingerprint=(suffix * 64)[:64].ljust(64, "0"),
        provider=provider,
        account_id=account_id,
        rule_key="ebs_unattached",
        service="EC2",
        region="sa-east-1",
        resource_id=f"resource-{suffix}",
        title=f"Finding {suffix}",
        description="presence history test",
        evidence={},
        status=status,
        presence_status=presence_status,
        first_seen_at=START,
        last_seen_at=START,
    )
    db.add(finding)
    db.flush()
    return finding


def _observation(db: Session, finding: Finding, run: CollectionRun) -> None:
    db.add(
        OpportunityObservation(
            opportunity_id=finding.id,
            collection_run_id=run.id,
            observed_at=run.started_at,
            severity="medium",
            confidence="high",
            evidence={},
        )
    )
    db.flush()


def _reconcile(
    db: Session,
    run: CollectionRun,
    scope: CollectionScopeExecution,
    *,
    threshold: int = 3,
):
    return reconcile_opportunity_presence(
        db,
        run,
        [scope],
        missing_threshold=threshold,
    )


def _events(db: Session, finding: Finding) -> list[OpportunityPresenceHistory]:
    return list(
        db.scalars(
            select(OpportunityPresenceHistory)
            .where(OpportunityPresenceHistory.opportunity_id == finding.id)
            .order_by(OpportunityPresenceHistory.occurred_at, OpportunityPresenceHistory.id)
        )
    )


def test_each_valid_absence_is_auditable_through_threshold(engine):
    with Session(engine) as db:
        finding = _finding(db, "threshold")
        for index in range(1, 4):
            run = _run(db, f"threshold-{index}", START + timedelta(hours=index))
            scope = _scope(db, run)
            _reconcile(db, run, scope, threshold=3)

        events = _events(db, finding)
        assert [(event.from_status, event.to_status) for event in events] == [
            ("active", "missing"),
            ("missing", "missing"),
            ("missing", "resolved_externally"),
        ]
        assert [event.missing_count for event in events] == [1, 2, 3]
        assert [event.reason for event in events] == [
            OpportunityPresenceReason.NOT_OBSERVED_IN_SUCCESSFUL_SCOPE.value,
            OpportunityPresenceReason.NOT_OBSERVED_IN_SUCCESSFUL_SCOPE.value,
            OpportunityPresenceReason.MISSING_THRESHOLD_REACHED.value,
        ]
        assert all(event.missing_threshold == 3 for event in events)
        assert all(event.collection_run_id is not None for event in events)
        assert all(event.collection_scope_execution_id is not None for event in events)
        assert finding.presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
        assert db.scalar(select(func.count()).select_from(OpportunityStatusHistory)) == 0


def test_retry_failed_skipped_and_old_runs_do_not_create_false_history(engine):
    with Session(engine) as db:
        finding = _finding(db, "guards")
        current = _run(db, "guards-current", START + timedelta(hours=2))
        current_scope = _scope(db, current)
        _reconcile(db, current, current_scope)
        _reconcile(db, current, current_scope)

        failed = _run(db, "guards-failed", START + timedelta(hours=3), status="FAILED")
        failed_scope = _scope(db, failed)
        _reconcile(db, failed, failed_scope)

        skipped = _run(db, "guards-skipped", START + timedelta(hours=4))
        skipped_scope = _scope(
            db,
            skipped,
            status=CollectionScopeExecutionStatus.SKIPPED.value,
        )
        _reconcile(db, skipped, skipped_scope)

        older = _run(db, "guards-old", START + timedelta(hours=1))
        older_scope = _scope(db, older)
        result = _reconcile(db, older, older_scope)

        events = _events(db, finding)
        assert len(events) == 1
        assert events[0].collection_run_id == current.id
        assert finding.missing_count == 1
        assert result.skipped_out_of_order == 1


@pytest.mark.parametrize(
    ("presence_status", "missing_count", "human_status"),
    [
        (OpportunityPresenceStatus.MISSING.value, 2, "rejected"),
        (OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value, 3, "treated"),
    ],
)
def test_reappearance_is_audited_without_reopening_human_lifecycle(
    engine, presence_status, missing_count, human_status
):
    with Session(engine) as db:
        finding = _finding(
            db,
            f"reappear-{human_status}",
            status=human_status,
            presence_status=presence_status,
        )
        finding.missing_count = missing_count
        finding.missing_since_at = START + timedelta(minutes=10)
        if presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value:
            finding.resolved_externally_at = START + timedelta(minutes=30)
        run = _run(db, f"reappear-{human_status}", START + timedelta(hours=5))

        changed = reactivate_presence_from_observation(finding, run)
        db.flush()

        event = _events(db, finding)[0]
        assert changed is True
        assert finding.status == human_status
        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0
        assert event.from_status == presence_status
        assert event.to_status == OpportunityPresenceStatus.ACTIVE.value
        assert event.reason == OpportunityPresenceReason.OBSERVED_AGAIN.value
        assert event.missing_count == 0
        assert event.context["previous_missing_count"] == missing_count
        assert event.collection_run_id == run.id
        assert event.collection_scope_execution_id is None


@pytest.mark.parametrize("provider", ["aws", "oci"])
def test_presence_history_is_provider_neutral(engine, provider):
    with Session(engine) as db:
        finding = _finding(
            db,
            f"provider-{provider}",
            provider=provider,
            account_id=f"{provider}-account",
        )
        run = _run(
            db,
            f"provider-{provider}",
            START + timedelta(hours=1),
            provider=provider,
            account_id=f"{provider}-account",
        )
        scope = _scope(db, run)

        _reconcile(db, run, scope)

        event = _events(db, finding)[0]
        assert event.context["provider"] == provider
        assert event.context["account_id"] == f"{provider}-account"
        assert event.reason == OpportunityPresenceReason.NOT_OBSERVED_IN_SUCCESSFUL_SCOPE.value


def test_observed_run_does_not_create_absence_history(engine):
    with Session(engine) as db:
        finding = _finding(db, "observed")
        run = _run(db, "observed", START + timedelta(hours=1))
        scope = _scope(db, run)
        _observation(db, finding, run)

        _reconcile(db, run, scope)

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert _events(db, finding) == []


def test_state_and_history_roll_back_together(engine):
    with Session(engine) as db:
        finding = _finding(db, "transaction")
        finding_id = finding.id
        db.commit()

        run = _run(db, "transaction", START + timedelta(hours=1))
        scope = _scope(db, run)
        _reconcile(db, run, scope)
        assert finding.presence_status == OpportunityPresenceStatus.MISSING.value
        assert len(_events(db, finding)) == 1
        db.rollback()

    with Session(engine) as db:
        persisted = db.get(Finding, finding_id)
        assert persisted is not None
        assert persisted.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert persisted.missing_count == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(OpportunityPresenceHistory)
                .where(OpportunityPresenceHistory.opportunity_id == finding_id)
            )
            == 0
        )


def test_database_constraint_rejects_duplicate_run_reason(engine):
    with Session(engine) as db:
        finding = _finding(db, "unique")
        run = _run(db, "unique", START + timedelta(hours=1))
        scope = _scope(db, run)
        _reconcile(db, run, scope)
        db.flush()

        db.add(
            OpportunityPresenceHistory(
                opportunity_id=finding.id,
                collection_run_id=run.id,
                collection_scope_execution_id=scope.id,
                from_status="active",
                to_status="missing",
                reason=OpportunityPresenceReason.NOT_OBSERVED_IN_SUCCESSFUL_SCOPE.value,
                missing_count=1,
                missing_threshold=3,
                occurred_at=run.started_at,
                context={},
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_api_returns_presence_history_paginated_and_newest_first(engine, api):
    with Session(engine) as db:
        finding = _finding(db, "api")
        finding_id = finding.id
        run_ids = []
        for index in range(1, 4):
            run = _run(db, f"api-{index}", START + timedelta(hours=index))
            run_ids.append(run.id)
            scope = _scope(db, run)
            _reconcile(db, run, scope, threshold=3)
        db.commit()

    response = api.get(f"/opportunities/{finding_id}/presence-history?page=1&page_size=2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["collection_run_id"] == run_ids[2]
    assert payload["items"][0]["reason"] == "MISSING_THRESHOLD_REACHED"
    assert payload["items"][0]["scope_rule_key"] == "ebs_unattached"
    assert payload["items"][1]["collection_run_id"] == run_ids[1]

    missing = api.get("/opportunities/not-found/presence-history")
    assert missing.status_code == 404


def test_legacy_findings_do_not_receive_invented_history(engine, api):
    with Session(engine) as db:
        finding = _finding(
            db,
            "legacy",
            presence_status=OpportunityPresenceStatus.MISSING.value,
        )
        finding.missing_count = 2
        finding_id = finding.id
        db.commit()

    response = api.get(f"/opportunities/{finding_id}/presence-history")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "page_size": 50,
        "total": 0,
        "total_pages": 0,
    }
