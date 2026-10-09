import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import settings
from app.db.migrations import wait_for_database
from app.db.session import SessionLocal, engine
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.collection_errors import classify_collection_error, sanitize_collection_error
from app.services.collection_executors import (
    CollectionPreconditionError,
    ProviderExecutionError,
    get_collection_executor,
)
from app.services.dashboard_aggregation import rebuild_account_summary
from app.services.opportunity_fingerprint import build_opportunity_fingerprint
from app.services.opportunity_reconciliation import (
    build_collection_scope_executions,
    persist_collection_scope_executions,
    reactivate_presence_from_observation,
    reconcile_opportunity_presence,
)
from app.services.provider_capabilities import (
    ProviderOperation,
    UnsupportedProviderOperation,
    providers_supporting,
    require_provider_operation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("deepops.worker")


def enqueue_due_scans(db: Session) -> None:
    now = datetime.now(UTC)
    due_accounts = list(
        db.scalars(
            select(CloudAccount).where(
                CloudAccount.provider.in_(providers_supporting(ProviderOperation.SCHEDULING)),
                CloudAccount.enabled.is_(True),
                CloudAccount.schedule_enabled.is_(True),
                CloudAccount.next_scan_at.is_not(None),
                CloudAccount.next_scan_at <= now,
            )
        )
    )
    for account in due_accounts:
        active = db.scalar(
            select(Scan).where(
                Scan.cloud_account_id == account.id,
                Scan.status.in_(["pending", "running"]),
            )
        )
        previous_next_scan_at = account.next_scan_at
        if active is None:
            legacy_account_id = (
                account.aws_configuration.id if account.aws_configuration is not None else None
            )
            scan = Scan(
                account_id=legacy_account_id,
                cloud_account_id=account.id,
                trigger="scheduled",
            )
            db.add(scan)
            db.flush()
            logger.info(
                "event=scheduled_collection_enqueued provider=%s cloud_account_id=%s "
                "native_account_id=%s scan_id=%s trigger=scheduled previous_next_scan_at=%s "
                "interval_hours=%s",
                account.provider,
                account.id,
                account.native_account_id,
                scan.id,
                previous_next_scan_at,
                account.scan_interval_hours,
            )
        else:
            logger.info(
                "event=scheduled_collection_skipped provider=%s cloud_account_id=%s "
                "native_account_id=%s scan_id=%s trigger=scheduled reason=active_scan",
                account.provider,
                account.id,
                account.native_account_id,
                active.id,
            )
        account.next_scan_at = now + timedelta(hours=account.scan_interval_hours)
        logger.debug(
            "event=schedule_advanced provider=%s cloud_account_id=%s native_account_id=%s "
            "previous_next_scan_at=%s next_scan_at=%s interval_hours=%s active_scan=%s",
            account.provider,
            account.id,
            account.native_account_id,
            previous_next_scan_at,
            account.next_scan_at,
            account.scan_interval_hours,
            active.id if active is not None else None,
        )
    db.commit()


def _scan_operation(scan: Scan) -> ProviderOperation:
    if scan.trigger == "scheduled":
        return ProviderOperation.SCHEDULING
    return ProviderOperation.MANUAL_COLLECTION


def _fail_claimed_precondition(scan: Scan, exc: Exception) -> None:
    error = sanitize_collection_error(exc) or "Collection precondition failed"
    scan.status = "failed"
    scan.completed_at = datetime.now(UTC)
    scan.error = error[:4000]


def claim_scan(db: Session) -> Scan | None:
    statement = (
        select(Scan)
        .where(Scan.status == "pending")
        .order_by(Scan.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    with db.begin():
        scan = db.scalar(statement)
        if scan:
            started_at = datetime.now(UTC)
            scan.status = "running"
            scan.started_at = started_at
            cloud_account = db.get(CloudAccount, scan.cloud_account_id)
            try:
                if cloud_account is None:
                    raise CollectionPreconditionError("CloudAccount for scan does not exist")
                if not cloud_account.enabled:
                    raise CollectionPreconditionError("Cloud account is disabled")

                require_provider_operation(cloud_account.provider, _scan_operation(scan))
                executor = get_collection_executor(cloud_account.provider)
                preparation = executor.prepare(db, cloud_account, scan=scan)
                db.add(
                    CollectionRun(
                        scan_id=scan.id,
                        provider=cloud_account.provider,
                        account_id=cloud_account.native_account_id,
                        scope=dict(preparation.scope),
                        started_at=started_at,
                        status=CollectionRunStatus.RUNNING,
                    )
                )
            except (UnsupportedProviderOperation, CollectionPreconditionError) as exc:
                _fail_claimed_precondition(scan, exc)
                provider = cloud_account.provider if cloud_account is not None else "unknown"
                native_account_id = (
                    cloud_account.native_account_id if cloud_account is not None else "unknown"
                )
                info = classify_collection_error(exc)
                logger.warning(
                    "event=collection_failed provider=%s cloud_account_id=%s "
                    "native_account_id=%s scan_id=%s collection_run_id=missing trigger=%s "
                    "stage=precondition error_category=%s retryable=%s error=%s",
                    provider,
                    scan.cloud_account_id,
                    native_account_id,
                    scan.id,
                    scan.trigger,
                    info.category,
                    str(info.retryable).lower() if info.retryable is not None else "unknown",
                    info.public_message,
                )
    return scan


def collection_run_for_scan(db: Session, scan_id: str) -> CollectionRun | None:
    return db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan_id))


def _finding_by_fingerprint(db: Session, fingerprint: str) -> Finding | None:
    return db.scalar(select(Finding).where(Finding.fingerprint == fingerprint).with_for_update())


def _create_finding_race_safe(
    db: Session,
    *,
    fingerprint: str,
    scan: Scan,
    run: CollectionRun,
    item,
    observed_at: datetime,
) -> Finding:
    candidate = Finding(
        fingerprint=fingerprint,
        scan_id=scan.id,
        provider=run.provider,
        account_id=run.account_id,
        rule_key=item.rule_key,
        service=item.service,
        region=item.region,
        resource_id=item.resource_id,
        resource_name=item.resource_name,
        resource_type=item.resource_type,
        provider_metadata=dict(item.provider_metadata),
        title=item.title,
        description=item.description,
        evidence=dict(item.evidence),
        current_monthly_cost=item.current_monthly_cost,
        estimated_monthly_savings=item.estimated_monthly_savings,
        currency=item.currency,
        confidence=item.confidence,
        severity=item.severity,
        status="open",
        presence_status=OpportunityPresenceStatus.ACTIVE.value,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
        return candidate
    except IntegrityError:
        existing = _finding_by_fingerprint(db, fingerprint)
        if existing is None:
            raise
        return existing


def _observation_for_run(
    db: Session, opportunity_id: str, collection_run_id: str
) -> OpportunityObservation | None:
    return db.scalar(
        select(OpportunityObservation)
        .where(
            OpportunityObservation.opportunity_id == opportunity_id,
            OpportunityObservation.collection_run_id == collection_run_id,
        )
        .with_for_update()
    )


def _create_observation_race_safe(
    db: Session,
    *,
    finding: Finding,
    run: CollectionRun,
    item,
    observed_at: datetime,
) -> tuple[OpportunityObservation, bool]:
    candidate = OpportunityObservation(
        opportunity_id=finding.id,
        collection_run_id=run.id,
        observed_at=observed_at,
        severity=item.severity,
        current_monthly_cost=item.current_monthly_cost,
        estimated_monthly_savings=item.estimated_monthly_savings,
        currency=item.currency,
        confidence=item.confidence,
        provider_metadata=dict(item.provider_metadata),
        evidence=dict(item.evidence),
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
        return candidate, True
    except IntegrityError:
        existing = _observation_for_run(db, finding.id, run.id)
        if existing is None:
            raise
        return existing, False


def _refresh_observation(observation: OpportunityObservation, item) -> None:
    observation.severity = item.severity
    observation.current_monthly_cost = item.current_monthly_cost
    observation.estimated_monthly_savings = item.estimated_monthly_savings
    observation.currency = item.currency
    observation.confidence = item.confidence
    observation.provider_metadata = dict(item.provider_metadata)
    observation.evidence = dict(item.evidence)


def _normalized_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _refresh_finding_snapshot(finding: Finding, scan: Scan, item) -> None:
    finding.scan_id = scan.id
    finding.resource_name = item.resource_name
    finding.resource_type = item.resource_type
    finding.provider_metadata = dict(item.provider_metadata)
    finding.title = item.title
    finding.description = item.description
    finding.evidence = dict(item.evidence)
    finding.current_monthly_cost = item.current_monthly_cost
    finding.estimated_monthly_savings = item.estimated_monthly_savings
    finding.currency = item.currency
    finding.confidence = item.confidence
    finding.severity = item.severity


def persist_findings(
    db: Session,
    scan: Scan,
    run: CollectionRun,
    collected: list,
    active_rule_keys: list[str],
    *,
    observed_at: datetime | None = None,
) -> int:
    observed_at = observed_at or datetime.now(UTC)
    by_fingerprint = {}
    for item in collected:
        fingerprint = build_opportunity_fingerprint(
            provider=run.provider,
            account_id=run.account_id,
            region=item.region,
            scope=item.service,
            resource_id=item.resource_id,
            rule_id=item.rule_key,
        )
        by_fingerprint[fingerprint] = item

    findings_by_fingerprint: dict[str, Finding] = {}
    if by_fingerprint:
        findings_by_fingerprint = {
            finding.fingerprint: finding
            for finding in db.scalars(
                select(Finding).where(Finding.fingerprint.in_(by_fingerprint)).with_for_update()
            )
        }

    for fingerprint, item in by_fingerprint.items():
        if fingerprint not in findings_by_fingerprint:
            findings_by_fingerprint[fingerprint] = _create_finding_race_safe(
                db,
                fingerprint=fingerprint,
                scan=scan,
                run=run,
                item=item,
                observed_at=observed_at,
            )

    observations_by_opportunity: dict[str, OpportunityObservation] = {}
    opportunity_ids = [finding.id for finding in findings_by_fingerprint.values()]
    if opportunity_ids:
        observations_by_opportunity = {
            observation.opportunity_id: observation
            for observation in db.scalars(
                select(OpportunityObservation)
                .where(
                    OpportunityObservation.collection_run_id == run.id,
                    OpportunityObservation.opportunity_id.in_(opportunity_ids),
                )
                .with_for_update()
            )
        }

    for fingerprint, item in by_fingerprint.items():
        finding = findings_by_fingerprint[fingerprint]
        observation = observations_by_opportunity.get(finding.id)
        observation_created = False
        if observation is None:
            observation, observation_created = _create_observation_race_safe(
                db,
                finding=finding,
                run=run,
                item=item,
                observed_at=observed_at,
            )
            observations_by_opportunity[finding.id] = observation
        _refresh_observation(observation, item)

        if observation_created:
            finding.total_occurrence_count = int(finding.total_occurrence_count or 0) + 1

        is_latest_observation = observation_created and (
            finding.last_seen_at is None
            or _normalized_utc(observation.observed_at) >= _normalized_utc(finding.last_seen_at)
        )
        if finding.scan_id == scan.id or is_latest_observation:
            _refresh_finding_snapshot(finding, scan, item)
        if is_latest_observation:
            finding.last_seen_at = observation.observed_at
            reactivate_presence_from_observation(finding, run)
            if finding.status == "treated" and finding.treated_at is not None:
                treated_at = _normalized_utc(finding.treated_at)
                if _normalized_utc(observation.observed_at) > treated_at:
                    finding.needs_review = True

    db.flush()
    return len(by_fingerprint)


def execute_scan(db: Session, scan: Scan) -> None:
    if scan.status != "running":
        raise CollectionPreconditionError("Scan is not running")

    cloud_account = db.get(CloudAccount, scan.cloud_account_id)
    if cloud_account is None:
        raise CollectionPreconditionError("CloudAccount for scan does not exist")
    if not cloud_account.enabled:
        raise CollectionPreconditionError("Cloud account is disabled")

    require_provider_operation(cloud_account.provider, _scan_operation(scan))
    executor = get_collection_executor(cloud_account.provider)
    executor.prepare(db, cloud_account, scan=scan)

    run = collection_run_for_scan(db, scan.id)
    if run is None:
        raise CollectionPreconditionError("CollectionRun missing for claimed scan")
    if run.provider != cloud_account.provider or run.account_id != cloud_account.native_account_id:
        raise CollectionPreconditionError(
            "CollectionRun identity does not match the scan CloudAccount"
        )

    result = executor.execute(db, cloud_account, scan)

    # Start the persistence transaction only after cloud I/O finishes; reload state
    # that may have changed during collection. Fingerprint locks/savepoints stay intact.
    scan = db.get(Scan, scan.id, populate_existing=True)
    run = db.get(CollectionRun, run.id, populate_existing=True)
    cloud_account = db.get(CloudAccount, cloud_account.id, populate_existing=True)
    if scan is None or run is None or cloud_account is None:
        raise CollectionPreconditionError("Collection state was removed during provider execution")
    if run.provider != cloud_account.provider or run.account_id != cloud_account.native_account_id:
        raise CollectionPreconditionError("CloudAccount identity changed during provider execution")

    persistence_started = time.monotonic()
    logger.info(
        "event=collection_stage_started provider=%s cloud_account_id=%s native_account_id=%s "
        "scan_id=%s collection_run_id=%s trigger=%s stage=persistence",
        run.provider,
        cloud_account.id,
        run.account_id,
        scan.id,
        run.id,
        scan.trigger,
    )
    opportunity_count = persist_findings(
        db,
        scan,
        run,
        result.findings,
        result.active_rule_keys,
    )
    completed_at = datetime.now(UTC)
    scope_executions = persist_collection_scope_executions(
        db,
        run,
        build_collection_scope_executions(
            db,
            cloud_account,
            run,
            result,
            finished_at=completed_at,
        ),
    )
    reconciliation = reconcile_opportunity_presence(
        db,
        run,
        scope_executions,
        missing_threshold=settings.opportunity_resolution_missing_runs,
    )

    scan.findings_count = opportunity_count
    scan.status = "completed_with_warnings" if result.collector_errors else "completed"
    scan.completed_at = completed_at
    scan.error = (
        "\n".join(sanitize_collection_error(error) or "" for error in result.collector_errors)[
            :4000
        ]
        if result.collector_errors
        else None
    )

    run.status = CollectionRunStatus.SUCCESS
    run.finished_at = completed_at
    run.opportunities_found = opportunity_count
    run.resources_analyzed = result.resources_analyzed
    run.error_detail = None

    executor.mark_connection_success(cloud_account)
    summary_provider = run.provider
    summary_account_id = run.account_id
    summary_collection_run_id = run.id
    failed_or_skipped_scopes = sum(
        1 for scope in scope_executions if scope.status != "SUCCESS"
    )
    db.commit()
    logger.info(
        "event=opportunity_presence_reconciled provider=%s account_id=%s collection_run_id=%s "
        "opportunities_reconciled=%s marked_missing=%s resolved_externally=%s "
        "skipped_due_to_failed_scope=%s skipped_out_of_order=%s",
        summary_provider,
        summary_account_id,
        summary_collection_run_id,
        reconciliation.opportunities_reconciled,
        reconciliation.marked_missing,
        reconciliation.resolved_externally,
        failed_or_skipped_scopes,
        reconciliation.skipped_out_of_order,
    )
    logger.info(
        "event=collection_stage_completed provider=%s cloud_account_id=%s native_account_id=%s "
        "scan_id=%s collection_run_id=%s trigger=%s stage=persistence duration_ms=%s "
        "opportunity_count=%s",
        summary_provider,
        cloud_account.id,
        summary_account_id,
        scan.id,
        summary_collection_run_id,
        scan.trigger,
        max(0, int((time.monotonic() - persistence_started) * 1000)),
        opportunity_count,
    )

    # Collection success is operational truth. The dashboard aggregate is derived and
    # repaired independently so a summary failure never rewrites a valid run as FAILED.
    try:
        rebuild_account_summary(
            db,
            provider=summary_provider,
            account_id=summary_account_id,
            collection_run_id=summary_collection_run_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Dashboard summary rebuild failed provider=%s account_id=%s collection_run_id=%s",
            summary_provider,
            summary_account_id,
            summary_collection_run_id,
        )


def fail_scan(db: Session, scan_id: str, exc: Exception) -> None:
    db.rollback()
    failed_scan = db.get(Scan, scan_id)
    if failed_scan is None:
        return

    finished_at = datetime.now(UTC)
    error = sanitize_collection_error(exc) or "Collection failed"
    failed_scan.status = "failed"
    failed_scan.completed_at = finished_at
    failed_scan.error = error[:4000]

    run = collection_run_for_scan(db, scan_id)
    if run:
        run.status = CollectionRunStatus.FAILED
        run.finished_at = finished_at
        run.error_detail = error[:4000]

    cloud_account = db.get(CloudAccount, failed_scan.cloud_account_id)
    if (
        cloud_account is not None
        and isinstance(exc, ProviderExecutionError)
        and exc.connection_failure
        and exc.provider == cloud_account.provider
    ):
        try:
            executor = get_collection_executor(cloud_account.provider)
        except CollectionPreconditionError:
            executor = None
        if executor is not None:
            executor.mark_connection_failure(cloud_account, error)
    db.commit()


def process_once() -> bool:
    with SessionLocal() as db:
        enqueue_due_scans(db)
        scan = claim_scan(db)
        if scan is None:
            return False

        cloud_account = db.get(CloudAccount, scan.cloud_account_id)
        run = collection_run_for_scan(db, scan.id)
        if cloud_account is not None:
            provider = cloud_account.provider
            native_account_id = cloud_account.native_account_id
        elif run is not None:
            provider = run.provider
            native_account_id = run.account_id
        else:
            provider = "unknown"
            native_account_id = "unknown"
        collection_run_id = run.id if run else "missing"

        if scan.status != "running":
            logger.warning(
                "event=collection_skipped provider=%s cloud_account_id=%s native_account_id=%s "
                "scan_id=%s collection_run_id=%s trigger=%s status=%s error=%s",
                provider,
                scan.cloud_account_id,
                native_account_id,
                scan.id,
                collection_run_id,
                scan.trigger,
                scan.status,
                scan.error,
            )
            return True

        collection_started = time.monotonic()
        try:
            logger.info(
                "event=collection_started provider=%s cloud_account_id=%s native_account_id=%s "
                "scan_id=%s collection_run_id=%s trigger=%s executor=%s",
                provider,
                scan.cloud_account_id,
                native_account_id,
                scan.id,
                collection_run_id,
                scan.trigger,
                type(get_collection_executor(provider)).__name__,
            )
            execute_scan(db, scan)
            completed_scan = db.get(Scan, scan.id)
            completed_run = collection_run_for_scan(db, scan.id)
            logger.info(
                "event=collection_completed provider=%s cloud_account_id=%s native_account_id=%s "
                "scan_id=%s collection_run_id=%s trigger=%s resource_count=%s "
                "finding_count=%s opportunity_count=%s warning_count=%s duration_ms=%s",
                provider,
                scan.cloud_account_id,
                native_account_id,
                scan.id,
                collection_run_id,
                scan.trigger,
                completed_run.resources_analyzed if completed_run is not None else 0,
                completed_scan.findings_count if completed_scan is not None else 0,
                completed_run.opportunities_found if completed_run is not None else 0,
                1 if completed_scan is not None and completed_scan.error else 0,
                max(0, int((time.monotonic() - collection_started) * 1000)),
            )
        except Exception as exc:  # worker boundary: persist errors and continue
            info = classify_collection_error(exc)
            stage = exc.stage if isinstance(exc, ProviderExecutionError) else "internal"
            retryable = exc.retryable if isinstance(exc, ProviderExecutionError) else info.retryable
            category = exc.category if isinstance(exc, ProviderExecutionError) else info.category
            logger.error(
                "event=collection_failed provider=%s cloud_account_id=%s native_account_id=%s "
                "scan_id=%s collection_run_id=%s trigger=%s stage=%s error_category=%s "
                "retryable=%s duration_ms=%s error=%s",
                provider,
                scan.cloud_account_id,
                native_account_id,
                scan.id,
                collection_run_id,
                scan.trigger,
                stage,
                category,
                str(retryable).lower() if retryable is not None else "unknown",
                max(0, int((time.monotonic() - collection_started) * 1000)),
                info.public_message,
            )
            fail_scan(db, scan.id, exc)
        return True


def main() -> None:
    wait_for_database(engine)
    logger.info("NuvemIQ worker started")
    while True:
        worked = process_once()
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
