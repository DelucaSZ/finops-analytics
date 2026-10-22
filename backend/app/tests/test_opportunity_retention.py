import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_archive_history import (
    OpportunityArchiveAction,
    OpportunityArchiveHistory,
    OpportunityArchiveReason,
)
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_retention_run import (
    OpportunityRetentionRun,
    OpportunityRetentionRunStatus,
)
from app.services.opportunity_retention import (
    OpportunityRetentionResult,
    OpportunityRetentionService,
)
from app.worker_runtime import (
    DailyOpportunityRetentionScheduler,
    process_runtime_once,
)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _finding(
    opportunity_id: str,
    *,
    provider: str = "aws",
    status: str = "open",
    presence_status: str = OpportunityPresenceStatus.ACTIVE.value,
    treated_at: datetime | None = None,
    rejected_at: datetime | None = None,
    resolved_externally_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    needs_review: bool = False,
) -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=(opportunity_id.encode().hex() * 64)[:64],
        provider=provider,
        account_id="111111111111" if provider == "aws" else "ocid1.tenancy.oc1..retention",
        rule_key="ebs_unattached" if provider == "aws" else "oci_block_volume_unattached",
        service="EC2" if provider == "aws" else "Block Storage",
        region="sa-east-1" if provider == "aws" else "sa-saopaulo-1",
        resource_id=f"resource-{opportunity_id}",
        resource_name=opportunity_id,
        resource_type="Volume",
        provider_metadata={},
        title="Retention test",
        description="Retention policy test",
        evidence={},
        current_monthly_cost=Decimal("10"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD" if provider == "aws" else "BRL",
        confidence="high",
        severity="medium",
        status=status,
        presence_status=presence_status,
        first_seen_at=NOW - timedelta(days=365),
        last_seen_at=last_seen_at or NOW - timedelta(days=365),
        treated_at=treated_at,
        rejected_at=rejected_at,
        resolved_externally_at=resolved_externally_at,
        needs_review=needs_review,
    )


@pytest.fixture
def retention_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.services.opportunity_retention.refresh_summaries_for_findings",
        lambda db, findings: None,
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _service(**changes) -> OpportunityRetentionService:
    values = {
        "treated_days": 60,
        "rejected_days": 30,
        "resolved_externally_days": 30,
        "batch_size": 2,
    }
    values.update(changes)
    return OpportunityRetentionService(**values)


def _history(db: Session, opportunity_id: str) -> list[OpportunityArchiveHistory]:
    return list(
        db.scalars(
            select(OpportunityArchiveHistory)
            .where(OpportunityArchiveHistory.opportunity_id == opportunity_id)
            .order_by(OpportunityArchiveHistory.occurred_at, OpportunityArchiveHistory.id)
        )
    )


def test_treated_below_cutoff_is_not_archived(retention_db):
    with Session(retention_db) as db:
        db.add(_finding("treated-59", status="treated", treated_at=NOW - timedelta(days=59)))
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_total == 0
        assert db.get(Finding, "treated-59").archived_at is None


def test_treated_exact_cutoff_is_eligible_and_audited(retention_db):
    with Session(retention_db) as db:
        finding = _finding("treated-60", status="treated", treated_at=NOW - timedelta(days=60))
        db.add(finding)
        db.commit()
        result = _service().run(db, now=NOW)
        db.refresh(finding)
        assert result.archived_treated == 1
        assert finding.archived_at == NOW.replace(tzinfo=None) or finding.archived_at == NOW
        assert finding.archive_reason == OpportunityArchiveReason.RETENTION_POLICY.value
        assert finding.archived_by is None
        event = _history(db, finding.id)[0]
        assert event.action == OpportunityArchiveAction.ARCHIVE.value
        assert event.reason == OpportunityArchiveReason.RETENTION_POLICY.value
        assert event.changed_by is None
        assert event.context["actor"] == "SYSTEM"
        assert event.context["policy"] == "treated_retention"
        assert event.context["threshold_days"] == 60
        assert event.context["reference_timestamp"].startswith("2026-08-14T12:00:00")


def test_rejected_and_resolved_externally_use_their_own_timestamps(retention_db):
    with Session(retention_db) as db:
        db.add_all(
            [
                _finding(
                    "rejected-31",
                    status="rejected",
                    rejected_at=NOW - timedelta(days=31),
                    last_seen_at=NOW,
                ),
                _finding(
                    "resolved-31",
                    status="open",
                    presence_status=OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value,
                    resolved_externally_at=NOW - timedelta(days=31),
                ),
            ]
        )
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_rejected == 1
        assert result.archived_resolved_externally == 1
        assert db.get(Finding, "rejected-31").status == "rejected"
        assert db.get(Finding, "resolved-31").status == "open"


def test_open_active_and_missing_are_never_archived_by_age(retention_db):
    with Session(retention_db) as db:
        db.add_all(
            [
                _finding("open-active-old"),
                _finding(
                    "open-missing-old",
                    presence_status=OpportunityPresenceStatus.MISSING.value,
                ),
            ]
        )
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_total == 0
        assert db.get(Finding, "open-active-old").archived_at is None
        assert db.get(Finding, "open-missing-old").archived_at is None


def test_treated_reappearance_and_needs_review_have_priority(retention_db):
    with Session(retention_db) as db:
        treated_at = NOW - timedelta(days=90)
        db.add_all(
            [
                _finding(
                    "treated-review",
                    status="treated",
                    treated_at=treated_at,
                    last_seen_at=NOW - timedelta(days=1),
                    needs_review=True,
                ),
                _finding(
                    "treated-active-newer",
                    status="treated",
                    treated_at=treated_at,
                    last_seen_at=NOW - timedelta(days=1),
                    needs_review=False,
                ),
            ]
        )
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_total == 0
        assert result.skipped_needs_review == 1
        assert result.skipped_active_after_treatment == 1


def test_rejected_can_archive_even_when_still_active(retention_db):
    with Session(retention_db) as db:
        finding = _finding(
            "rejected-active",
            status="rejected",
            rejected_at=NOW - timedelta(days=45),
            last_seen_at=NOW - timedelta(hours=1),
        )
        db.add(finding)
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_rejected == 1
        assert db.get(Finding, finding.id).presence_status == OpportunityPresenceStatus.ACTIVE.value


def test_policy_precedence_is_deterministic(retention_db):
    with Session(retention_db) as db:
        finding = _finding(
            "treated-resolved",
            status="treated",
            presence_status=OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value,
            treated_at=NOW - timedelta(days=90),
            resolved_externally_at=NOW - timedelta(days=90),
        )
        db.add(finding)
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_total == 1
        assert result.archived_treated == 1
        assert result.archived_resolved_externally == 0
        assert _history(db, finding.id)[0].context["policy"] == "treated_retention"


def test_manual_archive_is_ignored_and_reason_is_preserved(retention_db):
    with Session(retention_db) as db:
        finding = _finding("manual", status="treated", treated_at=NOW - timedelta(days=90))
        finding.archived_at = NOW - timedelta(days=10)
        finding.archive_reason = OpportunityArchiveReason.MANUAL.value
        db.add(finding)
        db.add(
            OpportunityArchiveHistory(
                opportunity_id=finding.id,
                action=OpportunityArchiveAction.ARCHIVE.value,
                reason=OpportunityArchiveReason.MANUAL.value,
                occurred_at=NOW - timedelta(days=10),
                context={},
            )
        )
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_total == 0
        db.refresh(finding)
        assert finding.archive_reason == OpportunityArchiveReason.MANUAL.value
        assert len(_history(db, finding.id)) == 1


def test_idempotency_second_run_archives_zero_and_does_not_duplicate_event(retention_db):
    with Session(retention_db) as db:
        db.add(_finding("idem", status="treated", treated_at=NOW - timedelta(days=90)))
        db.commit()
        first = _service().run(db, now=NOW)
        second = _service().run(db, now=NOW + timedelta(minutes=1))
        assert first.archived_total == 1
        assert second.archived_total == 0
        assert len(_history(db, "idem")) == 1


def test_custom_threshold_and_disabled_policy(retention_db):
    with Session(retention_db) as db:
        db.add_all(
            [
                _finding("custom-11", status="treated", treated_at=NOW - timedelta(days=11)),
                _finding(
                    "disabled-rejected",
                    status="rejected",
                    rejected_at=NOW - timedelta(days=90),
                ),
            ]
        )
        db.commit()
        result = _service(treated_days=10, rejected_enabled=False).run(db, now=NOW)
        assert result.archived_treated == 1
        assert db.get(Finding, "disabled-rejected").archived_at is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPPORTUNITY_RETENTION_TREATED_DAYS", 0),
        ("OPPORTUNITY_RETENTION_REJECTED_DAYS", -1),
        ("OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_DAYS", 0),
        ("OPPORTUNITY_RETENTION_BATCH_SIZE", 0),
    ],
)
def test_invalid_retention_configuration_fails_predictably(name, value):
    with pytest.raises(ValidationError):
        Settings(**{name: value})


def test_retention_settings_defaults_match_policy():
    configured = Settings()
    assert configured.opportunity_retention_enabled is True
    assert configured.opportunity_retention_treated_enabled is True
    assert configured.opportunity_retention_treated_days == 30
    assert configured.opportunity_retention_rejected_enabled is True
    assert configured.opportunity_retention_rejected_days == 30
    assert configured.opportunity_retention_resolved_externally_enabled is True
    assert configured.opportunity_retention_resolved_externally_days == 30


def test_recent_manual_or_reappearance_unarchive_starts_a_fresh_retention_window(retention_db):
    with Session(retention_db) as db:
        old = NOW - timedelta(days=120)
        manual = _finding("manual-unarchive", status="treated", treated_at=old)
        reappeared = _finding(
            "reappeared-unarchive",
            status="rejected",
            rejected_at=old,
            last_seen_at=NOW - timedelta(days=1),
        )
        db.add_all([manual, reappeared])
        db.flush()
        db.add_all(
            [
                OpportunityArchiveHistory(
                    opportunity_id=manual.id,
                    action=OpportunityArchiveAction.UNARCHIVE.value,
                    reason=OpportunityArchiveReason.MANUAL.value,
                    occurred_at=NOW - timedelta(days=1),
                    context={},
                ),
                OpportunityArchiveHistory(
                    opportunity_id=reappeared.id,
                    action=OpportunityArchiveAction.UNARCHIVE.value,
                    reason=OpportunityArchiveReason.REAPPEARED.value,
                    occurred_at=NOW - timedelta(days=1),
                    context={},
                ),
            ]
        )
        db.commit()
        assert _service().run(db, now=NOW).archived_total == 0
        assert _service().run(db, now=NOW + timedelta(days=30)).archived_rejected == 1
        assert db.get(Finding, manual.id).archived_at is None
        assert _service().run(db, now=NOW + timedelta(days=60)).archived_treated == 1


@pytest.mark.parametrize("provider", ["aws", "oci"])
def test_policy_is_provider_neutral(retention_db, provider):
    with Session(retention_db) as db:
        finding = _finding(
            f"provider-{provider}",
            provider=provider,
            status="treated",
            treated_at=NOW - timedelta(days=90),
        )
        db.add(finding)
        db.commit()
        result = _service().run(db, now=NOW)
        assert result.archived_treated == 1
        assert db.get(Finding, finding.id).provider == provider


def test_archiving_preserves_observations_and_lifecycle_fields(retention_db):
    with Session(retention_db) as db:
        finding = _finding("history", status="treated", treated_at=NOW - timedelta(days=90))
        db.add(finding)
        db.flush()
        collection_run = CollectionRun(
            provider="aws",
            account_id="111111111111",
            started_at=NOW - timedelta(days=100),
            finished_at=NOW - timedelta(days=100),
            status=CollectionRunStatus.SUCCESS.value,
        )
        db.add(collection_run)
        db.flush()
        db.add(
            OpportunityObservation(
                opportunity_id=finding.id,
                collection_run_id=collection_run.id,
                observed_at=NOW - timedelta(days=100),
                evidence={"preserved": True},
                current_monthly_cost=Decimal("10"),
                estimated_monthly_savings=Decimal("10"),
                currency="USD",
                confidence="high",
                severity="medium",
                provider_metadata={},
            )
        )
        db.commit()
        _service().run(db, now=NOW)
        db.refresh(finding)
        assert finding.status == "treated"
        assert finding.treated_at is not None
        assert db.scalar(select(func.count()).select_from(OpportunityObservation)) == 1
        assert len(_history(db, finding.id)) == 1


def test_timezone_aware_cutoff_accepts_equivalent_offset(retention_db):
    with Session(retention_db) as db:
        cutoff_with_offset = datetime.fromisoformat("2026-08-14T09:00:00-03:00")
        finding = _finding("tz", status="treated", treated_at=cutoff_with_offset)
        db.add(finding)
        db.commit()
        assert _service().run(db, now=NOW).archived_total == 1


def _postgres_engine():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise PostgreSQL concurrency")
    schema = "retention_" + uuid.uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    return engine, control, schema


def test_concurrent_runs_create_one_archive_event(monkeypatch):
    engine, control, schema = _postgres_engine()
    monkeypatch.setattr(
        "app.services.opportunity_retention.refresh_summaries_for_findings",
        lambda db, findings: None,
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(_finding("concurrent", status="treated", treated_at=NOW - timedelta(days=90)))
            db.commit()

        barrier = threading.Barrier(2)

        def run(_):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                return _service().run(db, now=NOW).archived_total

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [1, 2]))
        assert sum(results) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(OpportunityArchiveHistory)) == 1
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_postgres_daily_scheduler_elects_one_worker_and_survives_restart(monkeypatch):
    engine, control, schema = _postgres_engine()
    monkeypatch.setattr("app.worker_runtime.settings.opportunity_retention_enabled", True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    calls = []

    def run_policy():
        calls.append(1)
        return OpportunityRetentionResult(evaluated=1, archived_total=1)

    namespace = 1_000_000 + (uuid.uuid4().int % 1_000_000)
    first = DailyOpportunityRetentionScheduler(
        engine,
        runner=run_policy,
        session_factory=sessions,
        lock_namespace=namespace,
    )
    second = DailyOpportunityRetentionScheduler(
        engine,
        runner=run_policy,
        session_factory=sessions,
        lock_namespace=namespace,
    )
    try:
        assert first.tick(now=NOW) is not None
        assert second.tick(now=NOW) is None
        assert len(calls) == 1
        with sessions() as db:
            checkpoint = db.scalar(select(OpportunityRetentionRun))
            assert checkpoint.status == OpportunityRetentionRunStatus.SUCCESS.value
            assert checkpoint.period_date == NOW.date()
            assert checkpoint.result["archived_total"] == 1
    finally:
        first.close()
        second.close()
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_scheduler_failure_is_checkpointed_and_retried_after_backoff(monkeypatch, retention_db):
    monkeypatch.setattr("app.worker_runtime.settings.opportunity_retention_enabled", True)
    sessions = sessionmaker(bind=retention_db)
    calls = []

    def run_policy():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("test failure")
        return OpportunityRetentionResult(evaluated=1)

    scheduler = DailyOpportunityRetentionScheduler(
        retention_db,
        runner=run_policy,
        session_factory=sessions,
    )
    try:
        assert scheduler.tick(now=NOW) is None
        assert scheduler.tick(now=NOW + timedelta(minutes=30)) is None
        assert scheduler.tick(now=NOW + timedelta(hours=1)) is not None
        assert len(calls) == 2
        with sessions() as db:
            checkpoint = db.scalar(select(OpportunityRetentionRun))
            assert checkpoint.status == OpportunityRetentionRunStatus.SUCCESS.value
    finally:
        scheduler.close()


def test_runtime_cycle_runs_collection_before_retention(monkeypatch):
    calls = []

    class Scheduler:
        def tick(self):
            calls.append("retention")

    def process_once():
        calls.append("collection")
        return False

    monkeypatch.setattr("app.worker_runtime.worker.process_once", process_once)
    assert process_runtime_once(Scheduler()) is False
    assert calls == ["collection", "retention"]
