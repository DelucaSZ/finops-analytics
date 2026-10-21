import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.audit_event import AuditEvent
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_archive_history import OpportunityArchiveHistory
from app.models.opportunity_history_snapshot import OpportunityHistorySnapshot
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.services.opportunity_bulk_archiving import (
    archive_by_filter,
    archive_preview,
    bulk_archive,
    close_period_and_archive,
)
from app.services.opportunity_history import OpportunityHistoryCycleService
from app.services.opportunity_query import OpportunityFilters

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bulk-archive.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _actor(db: Session) -> User:
    actor = User(
        name="Archive Admin",
        email="archive-admin@example.com",
        password_hash="unused",
        role="admin",
    )
    db.add(actor)
    db.flush()
    return actor


def _finding(
    db: Session,
    opportunity_id: str,
    *,
    provider: str = "aws",
    account_id: str = "111111111111",
    status: str = "open",
    severity: str = "medium",
    service: str = "EC2",
    rule_key: str = "ec2_stopped",
) -> Finding:
    finding = Finding(
        id=opportunity_id,
        fingerprint=hashlib.sha256(opportunity_id.encode()).hexdigest(),
        provider=provider,
        account_id=account_id,
        rule_key=rule_key,
        service=service,
        region="sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        resource_type="instance",
        resource_id=f"resource-{opportunity_id}",
        resource_name=f"name-{opportunity_id}",
        title=f"Opportunity {opportunity_id}",
        description="Bulk archive test",
        evidence={},
        current_monthly_cost=Decimal("100"),
        estimated_monthly_savings=Decimal("25"),
        currency="USD" if provider == "aws" else "BRL",
        confidence="high",
        severity=severity,
        status=status,
        presence_status="active",
        first_seen_at=NOW,
        last_seen_at=NOW,
        total_occurrence_count=1,
        needs_review=False,
    )
    db.add(finding)
    db.flush()
    return finding


def test_bulk_archive_deduplicates_preserves_lifecycle_and_correlates_history(db):
    actor = _actor(db)
    open_item = _finding(db, "bulk-open")
    treated = _finding(db, "bulk-treated", status="treated")
    treated.treated_at = NOW
    rejected = _finding(db, "bulk-rejected", status="rejected")
    rejected.rejected_at = NOW
    rejected.rejection_reason = "RISK_ACCEPTED"
    db.flush()

    result = bulk_archive(
        db,
        [open_item.id, treated.id, rejected.id, open_item.id],
        actor,
    )
    db.commit()

    assert result["requested"] == 3
    assert result["archived"] == 3
    assert result["already_archived"] == 0
    assert result["correlation_id"]

    items = list(db.scalars(select(Finding).order_by(Finding.id)))
    assert {item.status for item in items} == {"open", "treated", "rejected"}
    assert all(item.presence_status == "active" for item in items)
    assert all(item.archived_at is not None for item in items)
    assert len({item.archived_at for item in items}) == 1

    history_statement = select(OpportunityArchiveHistory).order_by(OpportunityArchiveHistory.id)
    history = list(db.scalars(history_statement))
    assert len(history) == 3
    expected_correlations = {result["correlation_id"]}
    assert {item.context["correlation_id"] for item in history} == expected_correlations
    assert {item.context["operation"] for item in history} == {"bulk"}

    event_statement = select(AuditEvent).where(AuditEvent.action == "opportunity.bulk_archive")
    events = list(db.scalars(event_statement))
    assert len(events) == 1
    assert events[0].correlation_id == result["correlation_id"]

    second = bulk_archive(db, [open_item.id, treated.id], actor)
    db.commit()
    assert second["archived"] == 0
    assert second["already_archived"] == 2
    assert len(list(db.scalars(select(OpportunityArchiveHistory)))) == 3


def test_bulk_archive_missing_id_fails_before_mutation(db):
    actor = _actor(db)
    finding = _finding(db, "known-id")

    with pytest.raises(HTTPException) as exc:
        bulk_archive(db, [finding.id, "missing-id"], actor)
    assert exc.value.status_code == 404
    assert finding.archived_at is None
    assert db.scalar(select(OpportunityArchiveHistory)) is None


def test_archive_preview_and_execution_share_server_side_filters(db):
    actor = _actor(db)
    target = _finding(db, "aws-open-high", severity="high")
    _finding(db, "aws-treated-high", status="treated", severity="high")
    _finding(
        db,
        "oci-open-high",
        provider="oci",
        account_id="tenancy-1",
        severity="high",
    )
    archived = _finding(db, "aws-open-archived", severity="high")
    archived.archived_at = NOW
    archived.archive_reason = "MANUAL"
    db.flush()

    filters = OpportunityFilters(provider="aws", status="open", severity="high")
    preview = archive_preview(db, filters, archive_all=False)
    assert preview["to_archive"] == 1
    assert preview["already_archived"] == 1
    assert preview["matched"] == 2
    assert preview["by_status"] == {"open": 1}
    assert preview["by_provider"] == {"aws": 1}
    assert preview["savings"][0]["currency"] == "USD"

    result = archive_by_filter(db, filters, actor, archive_all=False)
    db.commit()
    assert result["archived"] == 1
    assert result["already_archived"] == 1
    assert db.get(Finding, target.id).archived_at is not None
    assert db.get(Finding, "aws-treated-high").archived_at is None
    assert db.get(Finding, "oci-open-high").archived_at is None


def test_empty_filter_requires_explicit_archive_all(db):
    actor = _actor(db)
    _finding(db, "all-1")
    _finding(db, "all-2", status="treated")

    with pytest.raises(HTTPException) as preview_error:
        archive_preview(db, OpportunityFilters(), archive_all=False)
    assert preview_error.value.status_code == 422

    with pytest.raises(HTTPException) as execution_error:
        archive_by_filter(db, OpportunityFilters(), actor, archive_all=False)
    assert execution_error.value.status_code == 422

    result = archive_by_filter(db, OpportunityFilters(), actor, archive_all=True)
    db.commit()
    assert result["archived"] == 2


def test_period_close_snapshots_before_archive_and_keeps_snapshot_immutable(db):
    actor = _actor(db)
    finding = _finding(db, "period-item", status="treated")
    finding.treated_at = NOW
    run = CollectionRun(
        id="period-run",
        provider="aws",
        account_id=finding.account_id,
        started_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 20, 12, 5, tzinfo=UTC),
        status=CollectionRunStatus.SUCCESS.value,
    )
    db.add(run)
    db.flush()
    db.add(
        OpportunityObservation(
            opportunity_id=finding.id,
            collection_run_id=run.id,
            observed_at=run.started_at,
            severity="medium",
            current_monthly_cost=Decimal("100"),
            estimated_monthly_savings=Decimal("25"),
            currency="USD",
            confidence="high",
            provider_metadata={},
            evidence={},
        )
    )
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, NOW)
    db.flush()

    result = close_period_and_archive(
        db,
        cycle_id=cycle.id,
        filters=OpportunityFilters(provider="aws", status="treated"),
        archive_all=False,
        actor=actor,
    )
    db.commit()

    assert result["cycle_closed"] is True
    assert result["snapshots_created"] == 1
    assert result["archived"] == 1
    snapshot_statement = select(OpportunityHistorySnapshot).where(
        OpportunityHistorySnapshot.cycle_id == cycle.id
    )
    snapshot = db.scalar(snapshot_statement)
    assert snapshot is not None
    assert snapshot.status == "treated"
    assert snapshot.archived is False
    assert db.get(Finding, finding.id).archived_at is not None

    db.get(Finding, finding.id).title = "Changed after close"
    db.commit()
    db.refresh(snapshot)
    assert snapshot.title == "Opportunity period-item"
    assert snapshot.archived is False


def test_period_close_is_blocked_by_running_collection(db):
    actor = _actor(db)
    _finding(db, "running-period")
    run = CollectionRun(
        id="running-run",
        provider="aws",
        account_id="111111111111",
        started_at=NOW,
        status=CollectionRunStatus.RUNNING.value,
    )
    db.add(run)
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, NOW)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        close_period_and_archive(
            db,
            cycle_id=cycle.id,
            filters=OpportunityFilters(provider="aws"),
            archive_all=False,
            actor=actor,
        )
    assert exc.value.status_code == 409
    assert "coletas em andamento" in exc.value.detail
    assert db.get(Finding, "running-period").archived_at is None
