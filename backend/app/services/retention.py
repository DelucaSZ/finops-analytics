from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.dashboard_summary import DashboardAccountSummary
from app.models.opportunity_observation import OpportunityObservation

logger = logging.getLogger("deepops.retention")


@dataclass(frozen=True)
class RetentionPreview:
    cutoff: datetime
    total_observations: int
    observations_before_cutoff: int
    eligible_observations: int
    protected_observations: int
    oldest_observation_at: datetime | None
    oldest_eligible_at: datetime | None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetentionResult:
    cutoff: datetime
    eligible_at_start: int
    deleted_observations: int
    batches: int
    collection_runs_marked_partial: int
    max_rows_reached: bool

    def as_dict(self) -> dict:
        return asdict(self)


def retention_cutoff(*, days: int, now: datetime | None = None) -> datetime:
    if days <= 0:
        raise ValueError("Retention days must be greater than zero")
    current = now or datetime.now(UTC)
    current = current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
    return current - timedelta(days=days)


def _scope(statement, run, *, provider: str | None, account_id: str | None):
    if provider:
        statement = statement.where(run.provider == provider.lower())
    if account_id:
        statement = statement.where(run.account_id == account_id)
    return statement


def _protected_run_predicate(run):
    newer = aliased(CollectionRun, name="retention_newer_success")
    newer_successes = (
        select(func.count())
        .select_from(newer)
        .where(
            newer.status == CollectionRunStatus.SUCCESS,
            newer.provider == run.provider,
            newer.account_id == run.account_id,
            or_(
                newer.started_at > run.started_at,
                and_(newer.started_at == run.started_at, newer.id > run.id),
            ),
        )
        .correlate(run)
        .scalar_subquery()
    )
    recent_success = and_(
        run.status == CollectionRunStatus.SUCCESS,
        newer_successes < 2,
    )
    summary_reference = (
        select(DashboardAccountSummary.provider)
        .where(
            or_(
                DashboardAccountSummary.collection_run_id == run.id,
                DashboardAccountSummary.baseline_collection_run_id == run.id,
            )
        )
        .correlate(run)
        .exists()
    )
    return or_(recent_success, summary_reference)


def _old_rows_statement(
    *,
    cutoff: datetime,
    provider: str | None,
    account_id: str | None,
    eligible_only: bool,
):
    run = aliased(CollectionRun, name="retention_collection_run")
    statement = (
        select(
            OpportunityObservation.id.label("observation_id"),
            OpportunityObservation.collection_run_id.label("collection_run_id"),
            OpportunityObservation.observed_at.label("observed_at"),
        )
        .join(run, OpportunityObservation.collection_run_id == run.id)
        .where(OpportunityObservation.observed_at < cutoff)
    )
    statement = _scope(statement, run, provider=provider, account_id=account_id)
    if eligible_only:
        statement = statement.where(~_protected_run_predicate(run))
    return statement


def retention_preview(
    db: Session,
    *,
    cutoff: datetime,
    provider: str | None = None,
    account_id: str | None = None,
) -> RetentionPreview:
    run = aliased(CollectionRun, name="retention_preview_run")
    scope = select(OpportunityObservation.id, OpportunityObservation.observed_at).join(
        run, OpportunityObservation.collection_run_id == run.id
    )
    scope = _scope(scope, run, provider=provider, account_id=account_id).subquery()

    total_observations, oldest_observation_at = db.execute(
        select(func.count(), func.min(scope.c.observed_at)).select_from(scope)
    ).one()

    old_rows = _old_rows_statement(
        cutoff=cutoff,
        provider=provider,
        account_id=account_id,
        eligible_only=False,
    ).subquery()
    observations_before_cutoff = db.scalar(select(func.count()).select_from(old_rows)) or 0

    eligible_rows = _old_rows_statement(
        cutoff=cutoff,
        provider=provider,
        account_id=account_id,
        eligible_only=True,
    ).subquery()
    eligible_observations, oldest_eligible_at = db.execute(
        select(func.count(), func.min(eligible_rows.c.observed_at)).select_from(eligible_rows)
    ).one()

    eligible = int(eligible_observations or 0)
    before = int(observations_before_cutoff)
    return RetentionPreview(
        cutoff=cutoff,
        total_observations=int(total_observations or 0),
        observations_before_cutoff=before,
        eligible_observations=eligible,
        protected_observations=max(0, before - eligible),
        oldest_observation_at=oldest_observation_at,
        oldest_eligible_at=oldest_eligible_at,
    )


def cleanup_observations(
    db: Session,
    *,
    cutoff: datetime,
    batch_size: int,
    max_rows: int = 0,
    provider: str | None = None,
    account_id: str | None = None,
) -> RetentionResult:
    if batch_size <= 0:
        raise ValueError("Batch size must be greater than zero")
    if max_rows < 0:
        raise ValueError("Max rows must be zero or greater")

    preview = retention_preview(
        db,
        cutoff=cutoff,
        provider=provider,
        account_id=account_id,
    )
    db.commit()

    deleted_total = 0
    batches = 0
    affected_runs: set[str] = set()

    logger.info(
        "Retention cleanup started cutoff=%s eligible=%s batch_size=%s max_rows=%s "
        "provider=%s account_id=%s",
        cutoff.isoformat(),
        preview.eligible_observations,
        batch_size,
        max_rows,
        provider,
        account_id,
    )

    while True:
        if max_rows and deleted_total >= max_rows:
            break
        limit = batch_size
        if max_rows:
            limit = min(limit, max_rows - deleted_total)

        candidates = list(
            db.execute(
                _old_rows_statement(
                    cutoff=cutoff,
                    provider=provider,
                    account_id=account_id,
                    eligible_only=True,
                )
                .order_by(
                    OpportunityObservation.observed_at,
                    OpportunityObservation.id,
                )
                .limit(limit)
            )
        )
        if not candidates:
            break

        observation_ids = [row.observation_id for row in candidates]
        run_ids = {row.collection_run_id for row in candidates}
        try:
            db.execute(
                update(CollectionRun)
                .where(CollectionRun.id.in_(run_ids))
                .values(detailed_observations_available=False)
            )
            result = db.execute(
                delete(OpportunityObservation).where(OpportunityObservation.id.in_(observation_ids))
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Retention batch failed cutoff=%s batch=%s requested_rows=%s",
                cutoff.isoformat(),
                batches + 1,
                len(observation_ids),
            )
            raise

        rowcount = result.rowcount
        deleted = len(observation_ids) if rowcount is None or rowcount < 0 else int(rowcount)
        deleted_total += deleted
        batches += 1
        affected_runs.update(run_ids)
        logger.info(
            "Retention batch committed cutoff=%s batch=%s rows_deleted=%s total_deleted=%s",
            cutoff.isoformat(),
            batches,
            deleted,
            deleted_total,
        )

    max_rows_reached = bool(
        max_rows and deleted_total >= max_rows and deleted_total < preview.eligible_observations
    )
    result = RetentionResult(
        cutoff=cutoff,
        eligible_at_start=preview.eligible_observations,
        deleted_observations=deleted_total,
        batches=batches,
        collection_runs_marked_partial=len(affected_runs),
        max_rows_reached=max_rows_reached,
    )
    logger.info(
        "Retention cleanup finished cutoff=%s deleted=%s batches=%s runs_marked_partial=%s "
        "max_rows_reached=%s",
        cutoff.isoformat(),
        deleted_total,
        batches,
        len(affected_runs),
        max_rows_reached,
    )
    return result
