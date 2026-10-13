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
from app.models.opportunity_retention_run import (
    OpportunityRetentionRun,
    OpportunityRetentionRunStatus,
)
from app.services.opportunity_retention import (
    OpportunityRetentionResult,
    OpportunityRetentionService,
)

logger = logging.getLogger("deepops.worker_runtime")

LOCK_NAMESPACE = 2305
LOCK_RECHECK = timedelta(minutes=5)
FAILURE_RETRY = timedelta(hours=1)


class DailyOpportunityRetentionScheduler:
    """Run retention once per UTC day across workers and restarts."""

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
        self._completed_period: date | None = None
        self._next_lock_check_at: datetime | None = None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def _run_policy(self) -> OpportunityRetentionResult:
        with SessionLocal() as db:
            return OpportunityRetentionService.from_settings().run(db)

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
            run = db.scalar(
                select(OpportunityRetentionRun)
                .where(OpportunityRetentionRun.period_date == period)
                .with_for_update()
            )
            if run is not None and run.status == OpportunityRetentionRunStatus.SUCCESS.value:
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
            run.status = OpportunityRetentionRunStatus.SUCCESS.value
            run.finished_at = current
            run.result = result.as_dict()
            run.error_detail = None
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
        if not settings.opportunity_retention_enabled:
            self._release_lock()
            return None

        current = self._utc(now or datetime.now(UTC))
        period = current.date()
        if self._completed_period == period:
            return None
        if self._next_lock_check_at is not None and current < self._next_lock_check_at:
            return None

        try:
            if not self._claim_period(period):
                self._next_lock_check_at = current + LOCK_RECHECK
                return None
            preparation = self._prepare_period(period, current)
            if preparation == "completed":
                self._completed_period = period
                return None
            if preparation == "backoff":
                self._next_lock_check_at = current + LOCK_RECHECK
                return None
            result = self.runner()
            self._mark_success(period, current, result)
            self._completed_period = period
            self._next_lock_check_at = None
            logger.info(
                "event=opportunity_retention_daily_completed period=%s archived=%s evaluated=%s",
                period.isoformat(),
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


def process_runtime_once(scheduler: DailyOpportunityRetentionScheduler) -> bool:
    scheduler.tick()
    return worker.process_once()


def main() -> None:
    wait_for_database(engine)
    scheduler = DailyOpportunityRetentionScheduler(engine)
    logger.info("NuvemIQ worker started")
    try:
        while True:
            worked = process_runtime_once(scheduler)
            if not worked:
                time.sleep(settings.worker_poll_seconds)
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
