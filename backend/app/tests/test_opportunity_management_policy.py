from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.models.audit_event import AuditEvent
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_archive_history import OpportunityArchiveHistory
from app.models.opportunity_history_cycle import OpportunityHistoryCycleStatus
from app.models.opportunity_management_policy import OpportunityManagementPolicy
from app.models.user import User
from app.schemas.opportunity_policy import (
    OpportunityPolicyPreviewRequest,
    OpportunityPolicyUpdate,
)
from app.services.opportunity_history import OpportunityHistoryCycleService
from app.services.opportunity_policy import OpportunityManagementPolicyService
from app.services.opportunity_retention import OpportunityRetentionService

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


@pytest.fixture
def db_engine(monkeypatch):
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


def _admin() -> User:
    return User(
        name="Admin",
        email="admin-policy@example.com",
        password_hash="not-used",
        role="admin",
    )


def _finding(opportunity_id: str, *, last_seen_at: datetime, status: str = "open") -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=(opportunity_id.encode().hex() * 64)[:64],
        provider="aws",
        account_id="111111111111",
        rule_key="ebs_unattached",
        service="EC2",
        region="sa-east-1",
        resource_id=f"vol-{opportunity_id}",
        resource_name=opportunity_id,
        resource_type="Volume",
        provider_metadata={},
        title="Policy test",
        description="Policy test",
        evidence={},
        current_monthly_cost=Decimal("10"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        severity="medium",
        status=status,
        presence_status="active",
        first_seen_at=NOW - timedelta(days=365),
        last_seen_at=last_seen_at,
        needs_review=False,
    )


def _preview_payload(**changes) -> OpportunityPolicyPreviewRequest:
    values = {
        "cycle_mode": "CALENDAR_MONTH",
        "cycle_length_days": 30,
        "cycle_timezone": "UTC",
        "cycle_anchor_date": date(2026, 10, 1),
        "automatic_cycle_close_enabled": False,
        "treated_archive_enabled": True,
        "treated_archive_days": 30,
        "rejected_archive_enabled": True,
        "rejected_archive_days": 30,
        "resolved_external_archive_enabled": True,
        "resolved_external_archive_days": 30,
        "open_archive_enabled": False,
        "open_archive_days": 30,
        "observation_retention_days": 400,
        "enabled": True,
    }
    values.update(changes)
    return OpportunityPolicyPreviewRequest(**values)


def test_bootstrap_defaults_are_product_defaults_not_legacy_class_defaults(db_engine, monkeypatch):
    for name in (
        "OPPORTUNITY_RETENTION_ENABLED",
        "OPPORTUNITY_RETENTION_TREATED_ENABLED",
        "OPPORTUNITY_RETENTION_TREATED_DAYS",
        "OPPORTUNITY_RETENTION_REJECTED_ENABLED",
        "OPPORTUNITY_RETENTION_REJECTED_DAYS",
        "OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_ENABLED",
        "OPPORTUNITY_RETENTION_RESOLVED_EXTERNALLY_DAYS",
        "NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)

    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(
            db,
            configured=Settings(_env_file=None),
        )
        db.commit()
        assert policy.cycle_mode == "CALENDAR_MONTH"
        assert policy.automatic_cycle_close_enabled is False
        assert policy.treated_archive_days == 30
        assert policy.rejected_archive_days == 30
        assert policy.resolved_external_archive_days == 30
        assert policy.open_archive_enabled is False
        assert policy.observation_retention_days == 400
        assert policy.version == 1


def test_bootstrap_uses_explicit_legacy_env_only_once(db_engine, monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_RETENTION_TREATED_DAYS", "75")
    monkeypatch.setenv("NUVEMIQ_OPPORTUNITY_OBSERVATION_RETENTION_DAYS", "500")
    configured = Settings(_env_file=None)

    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(db, configured=configured)
        db.commit()
        assert policy.treated_archive_days == 75
        assert policy.observation_retention_days == 500

    monkeypatch.setenv("OPPORTUNITY_RETENTION_TREATED_DAYS", "10")
    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(
            db,
            configured=Settings(_env_file=None),
        )
        assert policy.treated_archive_days == 75


@pytest.mark.parametrize(
    "changes",
    [
        {"cycle_timezone": "not/a-real-zone"},
        {"cycle_mode": "FIXED_DAYS", "cycle_anchor_date": None},
        {"cycle_mode": "FIXED_DAYS", "cycle_length_days": 90, "observation_retention_days": 30},
        {"cycle_mode": "CALENDAR_MONTH", "observation_retention_days": 30},
    ],
)
def test_policy_validation_rejects_unsafe_cycle_configuration(changes):
    with pytest.raises(ValidationError):
        _preview_payload(**changes)


def test_calendar_month_uses_iana_timezone_boundaries():
    candidate = _preview_payload(cycle_timezone="America/Sao_Paulo")
    start, end, label = OpportunityManagementPolicyService.cycle_bounds(candidate, NOW)
    assert start == datetime(2026, 10, 1, 3, tzinfo=UTC)
    assert end == datetime(2026, 11, 1, 3, tzinfo=UTC)
    assert label == "10/2026"


def test_fixed_days_uses_explicit_anchor_without_month_semantics():
    candidate = _preview_payload(
        cycle_mode="FIXED_DAYS",
        cycle_length_days=30,
        cycle_timezone="America/Sao_Paulo",
        cycle_anchor_date=date(2026, 10, 1),
        observation_retention_days=400,
    )
    start, end, _ = OpportunityManagementPolicyService.cycle_bounds(candidate, NOW)
    assert start == datetime(2026, 10, 1, 3, tzinfo=UTC)
    assert end == datetime(2026, 10, 31, 3, tzinfo=UTC)


def test_update_increments_version_audits_and_rejects_stale_write(db_engine):
    with Session(db_engine) as db:
        actor = _admin()
        db.add(actor)
        policy = OpportunityManagementPolicyService.get_or_create(db)
        db.commit()

        payload = OpportunityPolicyUpdate(
            **_preview_payload(treated_archive_days=45).model_dump(),
            expected_version=policy.version,
        )
        updated = OpportunityManagementPolicyService.update(db, payload, actor=actor)
        db.commit()
        assert updated.version == 2
        assert updated.treated_archive_days == 45
        event = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "opportunity_policy.update")
        )
        assert event is not None

        stale = OpportunityPolicyUpdate(
            **_preview_payload(treated_archive_days=60).model_dump(),
            expected_version=1,
        )
        with pytest.raises(HTTPException) as exc:
            OpportunityManagementPolicyService.update(db, stale, actor=actor)
        assert exc.value.status_code == 409


def test_open_retention_uses_last_seen_and_records_policy_version(db_engine):
    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(db)
        policy.open_archive_enabled = True
        policy.open_archive_days = 30
        policy.version = 7
        finding = _finding("open-old", last_seen_at=NOW - timedelta(days=31))
        recent = _finding("open-recent", last_seen_at=NOW - timedelta(days=2))
        db.add_all([finding, recent])
        db.commit()

        result = OpportunityRetentionService.from_management_policy(policy).run(db, now=NOW)
        assert result.archived_open == 1
        assert db.get(Finding, finding.id).status == "open"
        assert db.get(Finding, recent.id).archived_at is None
        history = db.scalar(
            select(OpportunityArchiveHistory).where(
                OpportunityArchiveHistory.opportunity_id == finding.id
            )
        )
        assert history.context["policy_key"] == "open_retention"
        assert history.context["policy_version"] == 7
        assert history.context["reference_timestamp"].startswith("2026-09-20")


def test_cycle_keeps_policy_snapshot_when_closed(db_engine):
    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(db)
        policy.version = 9
        cycle = OpportunityManagementPolicyService.get_or_create_cycle_for(
            db,
            datetime(2026, 9, 10, tzinfo=UTC),
            policy=policy,
        )
        assert cycle.metadata_json["policy"]["policy_version"] == 9
        db.commit()

        OpportunityHistoryCycleService.close_cycle(
            db,
            cycle.id,
            actor=None,
            close_reason="SYSTEM",
        )
        db.commit()
        db.refresh(cycle)
        assert cycle.status == OpportunityHistoryCycleStatus.CLOSED.value
        assert cycle.policy_version == 9
        assert cycle.metadata_json["policy"]["policy_version"] == 9
        assert "snapshot_count" in cycle.metadata_json


def test_policy_change_does_not_rewrite_current_cycle_boundaries(db_engine):
    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(db)
        cycle = OpportunityManagementPolicyService.get_or_create_cycle_for(
            db,
            NOW,
            policy=policy,
        )
        original = (cycle.period_start, cycle.period_end)
        db.commit()

        policy.cycle_mode = "FIXED_DAYS"
        policy.cycle_length_days = 14
        policy.cycle_anchor_date = date(2026, 10, 5)
        policy.cycle_timezone = "America/Sao_Paulo"
        policy.version += 1
        db.commit()

        same = OpportunityManagementPolicyService.get_or_create_cycle_for(
            db,
            NOW,
            policy=policy,
        )
        assert same.id == cycle.id
        assert (
            same.period_start.replace(tzinfo=UTC),
            same.period_end.replace(tzinfo=UTC),
        ) == original


def test_auto_close_defers_running_and_failed_does_not_block(db_engine):
    with Session(db_engine) as db:
        policy = OpportunityManagementPolicyService.get_or_create(db)
        policy.automatic_cycle_close_enabled = True
        old = OpportunityManagementPolicyService.get_or_create_cycle_for(
            db,
            datetime(2026, 8, 15, tzinfo=UTC),
            policy=policy,
        )
        db.add(
            CollectionRun(
                provider="aws",
                account_id="111111111111",
                started_at=datetime(2026, 8, 10, tzinfo=UTC),
                status=CollectionRunStatus.RUNNING.value,
            )
        )
        db.commit()

        deferred = OpportunityManagementPolicyService.auto_close_due_cycles(
            db,
            policy=policy,
            now=NOW,
        )
        assert deferred["deferred_running"] == 1
        assert db.get(type(old), old.id).status == OpportunityHistoryCycleStatus.OPEN.value

        run = db.scalar(
            select(CollectionRun).where(CollectionRun.status == CollectionRunStatus.RUNNING.value)
        )
        run.status = CollectionRunStatus.FAILED.value
        run.finished_at = datetime(2026, 8, 10, 1, tzinfo=UTC)
        db.commit()

        closed = OpportunityManagementPolicyService.auto_close_due_cycles(
            db,
            policy=policy,
            now=NOW,
        )
        db.commit()
        assert closed["closed"] >= 1
        assert db.get(type(old), old.id).status == OpportunityHistoryCycleStatus.CLOSED.value


def test_preview_is_read_only_and_reports_open_eligibility(db_engine):
    with Session(db_engine) as db:
        OpportunityManagementPolicyService.get_or_create(db)
        db.add(_finding("preview-open", last_seen_at=NOW - timedelta(days=40)))
        db.commit()
        before_policies = db.scalar(select(func.count()).select_from(OpportunityManagementPolicy))
        preview = OpportunityManagementPolicyService.preview(
            db,
            _preview_payload(open_archive_enabled=True, open_archive_days=30),
            now=NOW,
        )
        assert preview["open_eligible"] == 1
        assert (
            db.scalar(select(func.count()).select_from(OpportunityManagementPolicy))
            == before_policies
        )
        assert db.get(Finding, "preview-open").archived_at is None
