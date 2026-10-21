from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import CloudAccount
from app.models.audit_event import AuditEvent
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_history_cycle import OpportunityHistoryCycleStatus
from app.models.opportunity_history_snapshot import OpportunityHistorySnapshot
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.services.opportunity_history import OpportunityHistoryCycleService, cycle_stats

OCT_01 = datetime(2026, 10, 1, tzinfo=UTC)
NOV_01 = datetime(2026, 11, 1, tzinfo=UTC)
DEC_01 = datetime(2026, 12, 1, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _admin(db: Session) -> User:
    actor = User(
        name="History Admin",
        email="history-admin@example.com",
        password_hash="unused",
        role="admin",
    )
    db.add(actor)
    db.flush()
    return actor


def _finding(
    db: Session,
    *,
    opportunity_id: str = "finding-history-1",
    status: str = "open",
    currency: str = "USD",
) -> Finding:
    account = CloudAccount(
        provider="aws",
        native_account_id="111111111111",
        name="Produção",
    )
    finding = Finding(
        id=opportunity_id,
        fingerprint="f" * 64,
        provider="aws",
        account_id="111111111111",
        rule_key="ec2_stopped",
        service="EC2",
        region="sa-east-1",
        resource_type="instance",
        resource_id="i-123",
        resource_name="worker-01",
        provider_metadata={"instance_type": "m6i.large"},
        title="EC2 parada",
        description="Instância sem uso",
        evidence={"state": "stopped"},
        current_monthly_cost=Decimal("999.00"),
        estimated_monthly_savings=Decimal("888.00"),
        currency=currency,
        confidence="high",
        severity="high",
        status=status,
        presence_status="active",
        first_seen_at=datetime(2026, 9, 15, tzinfo=UTC),
        last_seen_at=datetime(2026, 10, 20, tzinfo=UTC),
        total_occurrence_count=2,
        needs_review=False,
    )
    db.add_all([account, finding])
    db.flush()
    return finding


def _run(db: Session, run_id: str, at: datetime, status: str = CollectionRunStatus.SUCCESS.value):
    run = CollectionRun(
        id=run_id,
        provider="aws",
        account_id="111111111111",
        started_at=at,
        finished_at=at,
        status=status,
    )
    db.add(run)
    db.flush()
    return run


def _observation(
    db: Session,
    finding: Finding,
    *,
    run_id: str,
    observed_at: datetime,
    cost: str,
    saving: str,
    severity: str = "high",
    currency: str = "USD",
):
    item = OpportunityObservation(
        opportunity_id=finding.id,
        collection_run_id=run_id,
        observed_at=observed_at,
        severity=severity,
        current_monthly_cost=Decimal(cost),
        estimated_monthly_savings=Decimal(saving),
        currency=currency,
        confidence="high",
        provider_metadata={"observed": run_id},
        evidence={"cost": cost},
    )
    db.add(item)
    db.flush()
    return item


def test_current_cycle_is_monthly_utc_and_not_duplicated(db):
    timestamp = datetime(2026, 10, 21, 15, 30, tzinfo=UTC)
    first = OpportunityHistoryCycleService.get_or_create_cycle_for(db, timestamp)
    second = OpportunityHistoryCycleService.get_or_create_cycle_for(db, timestamp)

    assert first.id == second.id
    assert first.period_start == OCT_01
    assert first.period_end == NOV_01
    assert first.timezone == "UTC"
    assert first.status == OpportunityHistoryCycleStatus.OPEN.value


def test_cycle_rejects_invalid_or_overlapping_period(db):
    OpportunityHistoryCycleService.create_cycle(
        db,
        period_start=OCT_01,
        period_end=NOV_01,
        label="10/2026",
    )
    with pytest.raises(HTTPException) as invalid:
        OpportunityHistoryCycleService.create_cycle(
            db,
            period_start=NOV_01,
            period_end=NOV_01,
            label="inválido",
        )
    assert invalid.value.status_code == 422

    with pytest.raises(HTTPException) as overlap:
        OpportunityHistoryCycleService.create_cycle(
            db,
            period_start=datetime(2026, 10, 15, tzinfo=UTC),
            period_end=DEC_01,
            label="sobreposto",
        )
    assert overlap.value.status_code == 409


def test_close_cycle_uses_observation_for_technical_data_and_finding_for_human_state(db):
    actor = _admin(db)
    finding = _finding(db, status="treated")
    finding.treated_at = datetime(2026, 10, 25, tzinfo=UTC)
    finding.treatment_note = "Ação executada"
    run_a = _run(db, "run-a", datetime(2026, 10, 5, tzinfo=UTC))
    run_b = _run(db, "run-b", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(
        db, finding, run_id=run_a.id, observed_at=run_a.started_at, cost="500", saving="300"
    )
    _observation(
        db,
        finding,
        run_id=run_b.id,
        observed_at=run_b.started_at,
        cost="420",
        saving="250",
        severity="medium",
    )
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(
        db, datetime(2026, 10, 21, tzinfo=UTC)
    )

    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()

    snapshot = db.scalar(select(OpportunityHistorySnapshot))
    assert snapshot is not None
    assert snapshot.status == "treated"
    assert snapshot.treated_at == finding.treated_at
    assert snapshot.current_monthly_cost == Decimal("420.00")
    assert snapshot.estimated_monthly_savings == Decimal("250.00")
    assert snapshot.severity == "medium"
    assert snapshot.first_observed_in_cycle_at == run_a.started_at
    assert snapshot.last_observed_in_cycle_at == run_b.started_at
    assert snapshot.occurrence_count_in_cycle == 2
    assert snapshot.first_collection_run_id_in_cycle == run_a.id
    assert snapshot.last_collection_run_id_in_cycle == run_b.id
    assert snapshot.account_name == "Produção"
    assert cycle.status == OpportunityHistoryCycleStatus.CLOSED.value
    assert cycle.closed_by == actor.id
    assert cycle.closed_at is not None


def test_snapshot_is_immutable_when_live_finding_changes_and_observations_are_removed(db):
    actor = _admin(db)
    finding = _finding(db)
    run = _run(db, "run-oct", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(db, finding, run_id=run.id, observed_at=run.started_at, cost="100", saving="70")
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)
    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()

    snapshot = db.scalar(select(OpportunityHistorySnapshot))
    snapshot_id = snapshot.id
    original = (
        snapshot.status,
        snapshot.title,
        snapshot.resource_name,
        snapshot.current_monthly_cost,
        snapshot.estimated_monthly_savings,
        snapshot.severity,
        snapshot.archived,
    )

    finding.status = "treated"
    finding.title = "Novo título"
    finding.resource_name = "renomeado"
    finding.current_monthly_cost = Decimal("50")
    finding.estimated_monthly_savings = Decimal("10")
    finding.severity = "low"
    finding.archived_at = datetime(2026, 11, 2, tzinfo=UTC)
    db.query(OpportunityObservation).delete(synchronize_session=False)
    db.commit()
    db.expire_all()

    persisted = db.get(OpportunityHistorySnapshot, snapshot_id)
    assert (
        persisted.status,
        persisted.title,
        persisted.resource_name,
        persisted.current_monthly_cost,
        persisted.estimated_monthly_savings,
        persisted.severity,
        persisted.archived,
    ) == original

    persisted.title = "tentativa de mutação"
    with pytest.raises(ValueError, match="append-only"):
        db.flush()
    db.rollback()


def test_same_opportunity_can_exist_in_multiple_cycles_without_rewriting_previous_snapshot(db):
    actor = _admin(db)
    finding = _finding(db, status="rejected")
    october_run = _run(db, "run-oct", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(
        db,
        finding,
        run_id=october_run.id,
        observed_at=october_run.started_at,
        cost="100",
        saving="70",
    )
    october = OpportunityHistoryCycleService.get_or_create_cycle_for(db, october_run.started_at)
    OpportunityHistoryCycleService.close_cycle(db, october.id, actor=actor)
    db.commit()

    november_run = _run(db, "run-nov", datetime(2026, 11, 10, tzinfo=UTC))
    _observation(
        db,
        finding,
        run_id=november_run.id,
        observed_at=november_run.started_at,
        cost="80",
        saving="50",
    )
    november = OpportunityHistoryCycleService.get_or_create_cycle_for(db, november_run.started_at)
    OpportunityHistoryCycleService.close_cycle(db, november.id, actor=actor)
    db.commit()

    snapshots = list(
        db.scalars(
            select(OpportunityHistorySnapshot).order_by(OpportunityHistorySnapshot.captured_at)
        )
    )
    assert len(snapshots) == 2
    assert {item.cycle_id for item in snapshots} == {october.id, november.id}
    assert all(item.status == "rejected" for item in snapshots)
    assert sorted(item.estimated_monthly_savings for item in snapshots) == [
        Decimal("50.00"),
        Decimal("70.00"),
    ]


def test_close_is_idempotent_and_audited_once(db):
    actor = _admin(db)
    finding = _finding(db)
    run = _run(db, "run-a", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(db, finding, run_id=run.id, observed_at=run.started_at, cost="100", saving="70")
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)

    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()
    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()

    assert db.scalar(select(func.count(OpportunityHistorySnapshot.id))) == 1
    audit_count = db.scalar(
        select(func.count(AuditEvent.id)).where(AuditEvent.action == "opportunity_cycle.close")
    )
    assert audit_count == 1


def test_running_collection_blocks_close_without_partial_snapshots(db):
    actor = _admin(db)
    finding = _finding(db)
    run = _run(
        db,
        "run-running",
        datetime(2026, 10, 20, tzinfo=UTC),
        status=CollectionRunStatus.RUNNING.value,
    )
    _observation(db, finding, run_id=run.id, observed_at=run.started_at, cost="100", saving="70")
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)

    with pytest.raises(HTTPException) as blocked:
        OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    assert blocked.value.status_code == 409
    db.rollback()
    assert db.scalar(select(func.count(OpportunityHistorySnapshot.id))) == 0


def test_cycle_stats_preserve_currency_boundaries(db):
    actor = _admin(db)
    usd = _finding(db, opportunity_id="finding-usd", currency="USD")
    usd.fingerprint = "u" * 64
    usd.resource_id = "i-usd"
    run_usd = _run(db, "run-usd", datetime(2026, 10, 10, tzinfo=UTC))
    _observation(
        db,
        usd,
        run_id=run_usd.id,
        observed_at=run_usd.started_at,
        cost="100",
        saving="70",
        currency="USD",
    )

    brl = Finding(
        id="finding-brl",
        fingerprint="b" * 64,
        provider="aws",
        account_id="111111111111",
        rule_key="ebs_idle",
        service="EBS",
        region="sa-east-1",
        resource_type="volume",
        resource_id="vol-1",
        resource_name="dados",
        provider_metadata={},
        title="Volume ocioso",
        description="Teste BRL",
        evidence={},
        current_monthly_cost=Decimal("200"),
        estimated_monthly_savings=Decimal("100"),
        currency="BRL",
        confidence="high",
        severity="medium",
        status="open",
        presence_status="active",
        first_seen_at=datetime(2026, 10, 1, tzinfo=UTC),
        last_seen_at=datetime(2026, 10, 11, tzinfo=UTC),
        total_occurrence_count=1,
        needs_review=False,
    )
    db.add(brl)
    db.flush()
    run_brl = _run(db, "run-brl", datetime(2026, 10, 11, tzinfo=UTC))
    _observation(
        db,
        brl,
        run_id=run_brl.id,
        observed_at=run_brl.started_at,
        cost="200",
        saving="100",
        currency="BRL",
    )

    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(
        db, datetime(2026, 10, 21, tzinfo=UTC)
    )
    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()
    stats = cycle_stats(db, cycle.id)

    assert {row["currency"] for row in stats["potential_savings"]} == {"USD", "BRL"}
    assert len(stats["potential_savings"]) == 2


def test_closed_cycle_cannot_be_mutated_or_deleted(db):
    actor = _admin(db)
    finding = _finding(db)
    run = _run(db, "run-immutable", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(
        db,
        finding,
        run_id=run.id,
        observed_at=run.started_at,
        cost="100",
        saving="70",
    )
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)
    OpportunityHistoryCycleService.close_cycle(db, cycle.id, actor=actor)
    db.commit()

    cycle.label = "alterado"
    with pytest.raises(ValueError, match="immutable"):
        db.flush()
    db.rollback()

    cycle = db.get(type(cycle), cycle.id)
    db.delete(cycle)
    with pytest.raises(ValueError, match="cannot be deleted"):
        db.flush()
    db.rollback()


def test_system_close_allows_null_closed_by(db):
    finding = _finding(db)
    run = _run(db, "run-system", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(
        db,
        finding,
        run_id=run.id,
        observed_at=run.started_at,
        cost="100",
        saving="70",
    )
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)
    OpportunityHistoryCycleService.close_cycle(
        db,
        cycle.id,
        actor=None,
        close_reason="SYSTEM",
    )
    db.commit()

    assert cycle.closed_by is None
    assert cycle.close_reason == "SYSTEM"
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "opportunity_cycle.close"))
    assert audit is not None
    assert audit.actor_id is None
    assert audit.source == "SYSTEM"


def test_caller_rollback_keeps_cycle_open_when_close_fails(db, monkeypatch):
    actor = _admin(db)
    finding = _finding(db)
    run = _run(db, "run-rollback", datetime(2026, 10, 20, tzinfo=UTC))
    _observation(
        db,
        finding,
        run_id=run.id,
        observed_at=run.started_at,
        cost="100",
        saving="70",
    )
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, run.started_at)
    cycle_id = cycle.id
    db.commit()

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr("app.services.opportunity_history.AuditService.record", fail_audit)
    with pytest.raises(RuntimeError, match="simulated audit failure"):
        OpportunityHistoryCycleService.close_cycle(db, cycle_id, actor=actor)
    db.rollback()

    persisted = db.get(type(cycle), cycle_id)
    assert persisted.status == OpportunityHistoryCycleStatus.OPEN.value
    snapshot_count = db.scalar(select(func.count(OpportunityHistorySnapshot.id)))
    audit_count = db.scalar(select(func.count(AuditEvent.id)))
    assert snapshot_count == 0
    assert audit_count == 0
