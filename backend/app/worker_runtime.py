from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.core.config import settings
from app.db.migrations import wait_for_database
from app.db.session import SessionLocal, engine
from app.models.opportunity_management_policy import OpportunityMaintenanceState
from app.models.opportunity_retention_run import (
    OpportunityRetentionRun,
    OpportunityRetentionRunStatus,
)
from app.services.opportunity_policy import OpportunityManagementPolicyService
from app.services.opportunity_retention import (
    OpportunityRetentionResult,
    OpportunityRetentionService,
)
from app.services.retention import cleanup_observations, retention_cutoff

logger = logging.getLogger("deepops.worker_runtime")

LOCK_NAMESPACE = 2305
LOCK_RECHECK = timedelta(minutes=5)
FAILURE_RETRY = timedelta(hours=1)
CYCLE_CLOSE_CADENCE = timedelta(minutes=15)
OBSERVATION_CLEANUP_CADENCE = timedelta(days=1)


class DailyOpportunityRetentionScheduler:
    """Run retention once per UTC day and again when the persisted policy version changes."""

    def __init__(
        self,
        database_engine: Engine,
        *,
        runner: Callable[[], OpportunityRetentionResult] | None = None,
        session_factory: sessionmaker[Session] | None = None,
        lock_namespace: int = LOCK_NAMESPACE,
    ) -> None:
        self.engine = database_engine
        self.runner = runner or self._run_policy
        self.session_factory = session_factory or SessionLocal
        self.lock_namespace = lock_namespace
        self._lock_connection = None
        self._held_period: date | None = None
        self._next_lock_check_at: datetime | None = None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def _run_policy(self) -> OpportunityRetentionResult:
        with SessionLocal() as db:
            policy = OpportunityManagementPolicyService.get_or_create(db)
            return OpportunityRetentionService.from_management_policy(policy).run(db)

    def _release_lock(self) -> None:
        if self._lock_connection is None:
            self._held_period = None
            return
        if self._held_period is not None and self.engine.dialect.name == "postgresql":
            try:
                self._lock_connection.scalar(
                    text("SELECT pg_advisory_unlock(:namespace, :period)"),
                    {
                        "namespace": self.lock_namespace,
                        "period": self._held_period.toordinal(),
                    },
                )
            except Exception:
                logger.exception("event=opportunity_retention_lock_release_failed")
        try:
            self._lock_connection.close()
        finally:
            self._lock_connection = None
            self._held_period = None

    def close(self) -> None:
        self._release_lock()

    def _claim_period(self, period: date) -> bool:
        self._release_lock()
        if self.engine.dialect.name != "postgresql":
            self._held_period = period
            return True

        connection = self.engine.connect()
        try:
            claimed = bool(
                connection.scalar(
                    text("SELECT pg_try_advisory_lock(:namespace, :period)"),
                    {"namespace": self.lock_namespace, "period": period.toordinal()},
                )
            )
        except Exception:
            connection.close()
            raise
        if not claimed:
            connection.close()
            return False
        self._lock_connection = connection
        self._held_period = period
        return True

    def _prepare_period(self, period: date, current: datetime) -> str:
        with self.session_factory() as db:
            policy = OpportunityManagementPolicyService.get_or_create(db)
            current_version = policy.version
            run = db.scalar(
                select(OpportunityRetentionRun)
                .where(OpportunityRetentionRun.period_date == period)
                .with_for_update()
            )
            if (
                run is not None
                and run.status == OpportunityRetentionRunStatus.SUCCESS.value
                and isinstance(run.result, dict)
                and run.result.get("policy_version") == current_version
            ):
                return "completed"
            if (
                run is not None
                and run.status == OpportunityRetentionRunStatus.FAILED.value
                and run.finished_at is not None
                and current < self._utc(run.finished_at) + FAILURE_RETRY
            ):
                return "backoff"
            if run is None:
                run = OpportunityRetentionRun(
                    period_date=period,
                    status=OpportunityRetentionRunStatus.RUNNING.value,
                    started_at=current,
                )
                db.add(run)
            else:
                run.status = OpportunityRetentionRunStatus.RUNNING.value
                run.started_at = current
                run.finished_at = None
                run.result = {}
                run.error_detail = None
            db.commit()
            return "run"

    def _mark_success(
        self,
        period: date,
        current: datetime,
        result: OpportunityRetentionResult,
    ) -> None:
        with self.session_factory() as db:
            run = db.scalar(
                select(OpportunityRetentionRun)
                .where(OpportunityRetentionRun.period_date == period)
                .with_for_update()
            )
            if run is None:
                raise RuntimeError("Opportunity retention checkpoint disappeared")
            policy = OpportunityManagementPolicyService.get_or_create(db)
            if result.policy_version is None:
                result.policy_version = policy.version
            run.status = OpportunityRetentionRunStatus.SUCCESS.value
            run.finished_at = current
            run.result = result.as_dict()
            run.error_detail = None
            state = OpportunityManagementPolicyService.get_maintenance_state(db)
            state.last_retention_run_at = current
            state.last_retention_result = result.as_dict()
            db.commit()

    def _mark_failed(self, period: date, current: datetime) -> None:
        with self.session_factory() as db:
            run = db.scalar(
                select(OpportunityRetentionRun)
                .where(OpportunityRetentionRun.period_date == period)
                .with_for_update()
            )
            if run is None:
                return
            run.status = OpportunityRetentionRunStatus.FAILED.value
            run.finished_at = current
            run.result = {"errors": 1}
            run.error_detail = "retention execution failed"
            db.commit()

    def tick(self, *, now: datetime | None = None) -> OpportunityRetentionResult | None:
        current = self._utc(now or datetime.now(UTC))
        period = current.date()
        if self._next_lock_check_at is not None and current < self._next_lock_check_at:
            return None

        try:
            if not self._claim_period(period):
                self._next_lock_check_at = current + LOCK_RECHECK
                return None
            preparation = self._prepare_period(period, current)
            if preparation == "completed":
                self._next_lock_check_at = current + LOCK_RECHECK
                return None
            if preparation == "backoff":
                self._next_lock_check_at = current + LOCK_RECHECK
                return None
            result = self.runner()
            self._mark_success(period, current, result)
            self._next_lock_check_at = current + LOCK_RECHECK
            logger.info(
                "event=opportunity_retention_daily_completed period=%s "
                "policy_version=%s archived=%s evaluated=%s",
                period.isoformat(),
                result.policy_version,
                result.archived_total,
                result.evaluated,
            )
            return result
        except Exception:
            try:
                self._mark_failed(period, current)
            except Exception:
                logger.exception(
                    "event=opportunity_retention_checkpoint_failed period=%s",
                    period.isoformat(),
                )
            self._next_lock_check_at = current + FAILURE_RETRY
            logger.exception("event=opportunity_retention_run_failed period=%s", period.isoformat())
            return None
        finally:
            self._release_lock()


class OpportunityAutomationScheduler:
    """Persistent cadence for cycle auto-close and observation cleanup."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.session_factory = session_factory or SessionLocal

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def _claim_due(
        self,
        *,
        field: str,
        cadence: timedelta,
        current: datetime,
    ) -> bool:
        with self.session_factory() as db:
            state = OpportunityManagementPolicyService.get_maintenance_state(db)
            # Serialize workers through the singleton row. SQLite ignores FOR UPDATE,
            # but production PostgreSQL provides the intended multi-worker lock.
            state = db.scalar(
                select(OpportunityMaintenanceState)
                .where(OpportunityMaintenanceState.id == 1)
                .with_for_update()
            ) or state
            previous = getattr(state, field)
            if previous is not None and current < self._utc(previous) + cadence:
                db.rollback()
                return False
            setattr(state, field, current)
            db.commit()
            return True

    def _store_result(self, field: str, result: dict) -> None:
        with self.session_factory() as db:
            state = OpportunityManagementPolicyService.get_maintenance_state(db)
            setattr(state, field, result)
            db.commit()

    def _cycle_close(self, current: datetime) -> None:
        if not self._claim_due(
            field="last_cycle_close_check_at",
            cadence=CYCLE_CLOSE_CADENCE,
            current=current,
        ):
            return
        try:
            with self.session_factory() as db:
                policy = OpportunityManagementPolicyService.get_or_create(db)
                result = OpportunityManagementPolicyService.auto_close_due_cycles(
                    db,
                    policy=policy,
                    now=current,
                )
                db.commit()
            self._store_result("last_cycle_close_result", result)
        except Exception:
            logger.exception("event=opportunity_cycle_auto_close_failed")

    def _cleanup(self, current: datetime) -> None:
        if not self._claim_due(
            field="last_observation_cleanup_at",
            cadence=OBSERVATION_CLEANUP_CADENCE,
            current=current,
        ):
            return
        try:
            with self.session_factory() as db:
                policy = OpportunityManagementPolicyService.get_or_create(db)
                if not policy.enabled:
                    result = {
                        "policy_version": policy.version,
                        "deleted_observations": 0,
                        "disabled": True,
                    }
                else:
                    cleanup = cleanup_observations(
                        db,
                        cutoff=retention_cutoff(
                            days=policy.observation_retention_days,
                            now=current,
                        ),
                        batch_size=settings.retention_batch_size,
                        max_rows=settings.retention_max_rows_per_run,
                    )
                    result = {
                        "policy_version": policy.version,
                        **cleanup.as_dict(),
                    }
            self._store_result("last_observation_cleanup_result", result)
        except Exception:
            logger.exception("event=opportunity_observation_cleanup_failed")

    def tick(self, *, now: datetime | None = None) -> None:
        current = self._utc(now or datetime.now(UTC))
        self._cycle_close(current)
        self._cleanup(current)


def process_runtime_once(
    scheduler: DailyOpportunityRetentionScheduler,
    automation_scheduler: OpportunityAutomationScheduler | None = None,
) -> bool:
    # Collection/reconciliation work runs first so cycle close never races ahead
    # of a completed scan that still needs to persist its observations.
    worked = worker.process_once()
    scheduler.tick()
    if automation_scheduler is not None:
        automation_scheduler.tick()
    return worked


def main() -> None:
    wait_for_database(engine)
    scheduler = DailyOpportunityRetentionScheduler(engine)
    automation_scheduler = OpportunityAutomationScheduler()
    logger.info("NuvemIQ worker started")
    try:
        while True:
            worked = process_runtime_once(scheduler, automation_scheduler)
            if not worked:
                time.sleep(settings.worker_poll_seconds)
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
