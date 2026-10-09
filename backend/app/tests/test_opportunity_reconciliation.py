from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.models.collection_run import CollectionRun
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.services.opportunity_reconciliation import (
    persist_collection_scope_executions,
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


def _run(
    db: Session,
    suffix: str,
    when: datetime,
    *,
    provider: str = "aws",
    account_id: str = "account-1",
    regions: list[str] | None = None,
    status: str = "SUCCESS",
) -> CollectionRun:
    run = CollectionRun(
        id=f"run-{suffix}",
        provider=provider,
        account_id=account_id,
        scope={"regions": regions or ["sa-east-1"]},
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
        service=None,
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
    rule_key: str = "ebs_unattached",
    region: str = "sa-east-1",
    status: str = "open",
    presence_status: str = OpportunityPresenceStatus.ACTIVE.value,
    last_seen_at: datetime = START,
) -> Finding:
    finding = Finding(
        id=f"finding-{suffix}",
        fingerprint=(suffix * 64)[:64].ljust(64, "0"),
        provider=provider,
        account_id=account_id,
        rule_key=rule_key,
        service="service",
        region=region,
        resource_id=f"resource-{suffix}",
        title=f"Finding {suffix}",
        description="reconciliation test",
        evidence={},
        status=status,
        presence_status=presence_status,
        first_seen_at=last_seen_at,
        last_seen_at=last_seen_at,
    )
    db.add(finding)
    db.flush()
    return finding


def _observation(db: Session, finding: Finding, run: CollectionRun) -> OpportunityObservation:
    observation = OpportunityObservation(
        opportunity_id=finding.id,
        collection_run_id=run.id,
        observed_at=run.started_at,
        severity="medium",
        confidence="high",
        evidence={},
    )
    db.add(observation)
    db.flush()
    return observation


def _reconcile(
    db: Session,
    run: CollectionRun,
    scopes: list[CollectionScopeExecution],
    *,
    threshold: int = 3,
):
    result = reconcile_opportunity_presence(
        db,
        run,
        scopes,
        missing_threshold=threshold,
    )
    db.flush()
    return result


def test_first_valid_absence_marks_missing_and_zero_result_counts(engine):
    with Session(engine) as db:
        finding = _finding(db, "a")
        run = _run(db, "absence-1", START + timedelta(hours=1))
        scope = _scope(db, run)

        result = _reconcile(db, run, [scope])

        assert result.marked_missing == 1
        assert finding.presence_status == OpportunityPresenceStatus.MISSING.value
        assert finding.missing_count == 1
        assert finding.missing_since_at is not None


def test_three_consecutive_valid_absences_resolve_externally(engine):
    with Session(engine) as db:
        finding = _finding(db, "b")
        for index in range(1, 4):
            run = _run(db, f"absence-{index}", START + timedelta(hours=index))
            scope = _scope(db, run)
            _reconcile(db, run, [scope], threshold=3)

        assert finding.missing_count == 3
        assert finding.presence_status == OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value
        assert finding.resolved_externally_at is not None
        assert finding.status == "open"


@pytest.mark.parametrize(
    "scope_status",
    [CollectionScopeExecutionStatus.FAILED.value, CollectionScopeExecutionStatus.SKIPPED.value],
)
def test_failed_or_skipped_scope_never_counts_absence(engine, scope_status):
    with Session(engine) as db:
        finding = _finding(db, "c")
        run = _run(db, "failed-scope", START + timedelta(hours=1))
        scope = _scope(db, run, status=scope_status)

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0


def test_different_region_does_not_count_absence(engine):
    with Session(engine) as db:
        finding = _finding(db, "d", region="us-east-1")
        run = _run(db, "west", START + timedelta(hours=1), regions=["us-west-2"])
        scope = _scope(db, run, region="us-west-2")

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0


def test_different_rule_does_not_count_absence(engine):
    with Session(engine) as db:
        finding = _finding(db, "e", rule_key="ebs_unattached")
        run = _run(db, "ec2-rule", START + timedelta(hours=1))
        scope = _scope(db, run, rule_key="ec2_stopped_with_ebs")

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0


def test_observed_opportunity_is_not_marked_missing(engine):
    with Session(engine) as db:
        finding = _finding(db, "f")
        run = _run(db, "observed", START + timedelta(hours=1))
        scope = _scope(db, run)
        _observation(db, finding, run)

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0


def test_reappearance_resets_missing_sequence_without_human_status_change(engine):
    with Session(engine) as db:
        finding = _finding(
            db,
            "g",
            status="rejected",
            presence_status=OpportunityPresenceStatus.MISSING.value,
        )
        finding.missing_count = 2
        finding.missing_since_at = START + timedelta(minutes=10)
        run = _run(db, "reappear", START + timedelta(hours=1))

        changed = reactivate_presence_from_observation(finding, run)

        assert changed is True
        assert finding.status == "rejected"
        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0
        assert finding.missing_since_at is None
        assert finding.resolved_externally_at is None


def test_resolved_externally_reappearance_returns_active_without_reopening_treated(engine):
    with Session(engine) as db:
        finding = _finding(
            db,
            "h",
            status="treated",
            presence_status=OpportunityPresenceStatus.RESOLVED_EXTERNALLY.value,
        )
        finding.missing_count = 3
        finding.resolved_externally_at = START + timedelta(minutes=30)
        run = _run(db, "resolved-reappear", START + timedelta(hours=2))

        reactivate_presence_from_observation(finding, run)

        assert finding.status == "treated"
        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0
        assert finding.resolved_externally_at is None


def test_same_run_retry_increments_missing_count_only_once(engine):
    with Session(engine) as db:
        finding = _finding(db, "i")
        run = _run(db, "retry", START + timedelta(hours=1))
        scope = _scope(db, run)

        _reconcile(db, run, [scope])
        _reconcile(db, run, [scope])

        assert finding.missing_count == 1
        assert finding.presence_reconciled_run_id == run.id


def test_old_run_cannot_regress_newer_presence_state(engine):
    with Session(engine) as db:
        finding = _finding(db, "j")
        newer = _run(db, "newer", START + timedelta(hours=2))
        newer_scope = _scope(db, newer)
        _reconcile(db, newer, [newer_scope])
        assert finding.missing_count == 1

        older = _run(db, "older", START + timedelta(hours=1))
        older_scope = _scope(db, older)
        result = _reconcile(db, older, [older_scope])

        assert result.skipped_out_of_order == 1
        assert finding.missing_count == 1
        assert finding.presence_reconciled_run_id == newer.id


def test_failed_collection_run_never_applies_absence(engine):
    with Session(engine) as db:
        finding = _finding(db, "k")
        run = _run(db, "failed-run", START + timedelta(hours=1), status="FAILED")
        scope = _scope(db, run)

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert finding.missing_count == 0


def test_partial_collection_reconciles_only_successful_scope(engine):
    with Session(engine) as db:
        ec2_finding = _finding(db, "l", rule_key="ec2_stopped_with_ebs")
        ebs_finding = _finding(db, "m", rule_key="ebs_unattached")
        run = _run(db, "partial", START + timedelta(hours=1))
        ec2_scope = _scope(db, run, rule_key="ec2_stopped_with_ebs")
        ebs_scope = _scope(
            db,
            run,
            rule_key="ebs_unattached",
            status=CollectionScopeExecutionStatus.FAILED.value,
        )

        _reconcile(db, run, [ec2_scope, ebs_scope])

        assert ec2_finding.presence_status == OpportunityPresenceStatus.MISSING.value
        assert ec2_finding.missing_count == 1
        assert ebs_finding.presence_status == OpportunityPresenceStatus.ACTIVE.value
        assert ebs_finding.missing_count == 0


@pytest.mark.parametrize("provider", ["aws", "oci"])
def test_reconciliation_core_is_provider_neutral(engine, provider):
    with Session(engine) as db:
        finding = _finding(
            db,
            f"provider-{provider}",
            provider=provider,
            account_id=f"{provider}-account",
            rule_key=f"{provider}_rule",
        )
        run = _run(
            db,
            f"provider-{provider}",
            START + timedelta(hours=1),
            provider=provider,
            account_id=f"{provider}-account",
        )
        scope = _scope(db, run, rule_key=f"{provider}_rule")

        _reconcile(db, run, [scope])

        assert finding.presence_status == OpportunityPresenceStatus.MISSING.value
        assert finding.missing_count == 1


def test_scope_execution_persistence_is_idempotent(engine):
    with Session(engine) as db:
        run = _run(db, "scope-retry", START + timedelta(hours=1))
        first = CollectionScopeExecution(
            collection_run_id=run.id,
            provider=run.provider,
            account_id=run.account_id,
            region="sa-east-1",
            rule_key="ebs_unattached",
            status=CollectionScopeExecutionStatus.SUCCESS.value,
            started_at=run.started_at,
            finished_at=run.finished_at or run.started_at,
        )
        persist_collection_scope_executions(db, run, [first])
        retry = CollectionScopeExecution(
            collection_run_id=run.id,
            provider=run.provider,
            account_id=run.account_id,
            region="sa-east-1",
            rule_key="ebs_unattached",
            status=CollectionScopeExecutionStatus.SUCCESS.value,
            started_at=run.started_at,
            finished_at=run.finished_at or run.started_at,
        )
        persist_collection_scope_executions(db, run, [retry])

        rows = list(db.scalars(select(CollectionScopeExecution)))
        assert len(rows) == 1
        assert rows[0].status == CollectionScopeExecutionStatus.SUCCESS.value


def test_resolution_threshold_defaults_to_three_and_rejects_invalid_values():
    settings = Settings()
    assert settings.opportunity_resolution_missing_runs == 3
    with pytest.raises(ValidationError):
        Settings(OPPORTUNITY_RESOLUTION_MISSING_RUNS=0)
