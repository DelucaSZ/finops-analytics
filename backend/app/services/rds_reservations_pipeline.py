from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.rds_coverage import RdsReservationCoverageRun
from app.services.rds_inventory import collect_rds_inventory
from app.services.rds_reservation_coverage import run_rds_reservation_coverage
from app.services.rds_reservation_freshness import (
    STALE,
    classify_rds_inventory_freshness,
    effective_rds_inventory_snapshot_at,
    normalize_utc,
)
from app.services.rds_reservation_opportunities import generate_rds_reservation_opportunities

logger = logging.getLogger(__name__)

_PIPELINE_LOCK_NAMESPACE = 2447
_PIPELINE_LOCK_KEY = 1
_RUNNING_TIMEOUT = timedelta(hours=2)
_PROCESS_LOCK = threading.Lock()


class RdsReservationsPipelineBusy(RuntimeError):
    pass


def _utc_now(value: datetime | None = None) -> datetime:
    return normalize_utc(value or utcnow())


@contextmanager
def _pipeline_lock(db: Session) -> Iterator[None]:
    if not _PROCESS_LOCK.acquire(blocking=False):
        raise RdsReservationsPipelineBusy("RDS Reservations refresh is already running")

    lock_connection = None
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            engine = getattr(bind, "engine", bind)
            lock_connection = engine.connect()
            claimed = bool(
                lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
                    {"namespace": _PIPELINE_LOCK_NAMESPACE, "lock_key": _PIPELINE_LOCK_KEY},
                )
            )
            if not claimed:
                raise RdsReservationsPipelineBusy("RDS Reservations refresh is already running")
        yield
    finally:
        if lock_connection is not None:
            try:
                lock_connection.scalar(
                    text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                    {"namespace": _PIPELINE_LOCK_NAMESPACE, "lock_key": _PIPELINE_LOCK_KEY},
                )
            except Exception:
                logger.exception("event=rds_reservations_lock_release_failed")
            lock_connection.close()
        _PROCESS_LOCK.release()


def _recover_abandoned_runs(db: Session, *, now: datetime) -> None:
    cutoff = now - _RUNNING_TIMEOUT
    abandoned = (
        db.query(RdsReservationCoverageRun)
        .filter(
            RdsReservationCoverageRun.status == "RUNNING",
            RdsReservationCoverageRun.started_at < cutoff,
        )
        .all()
    )
    for run in abandoned:
        run.status = "FAILED"
        run.completed_at = now
        run.error_detail = "Pipeline execution was abandoned before completion"
        if run.pipeline_stage == "inventory":
            run.inventory_status = "FAILED"
            run.inventory_error_detail = "Pipeline execution was abandoned during inventory"
        elif run.pipeline_stage == "opportunities":
            # Coverage may already be valid. Preserve it if the stage reached opportunities.
            run.status = "COMPLETED"
            run.opportunity_status = "FAILED"
            run.opportunity_error_detail = "Pipeline execution was abandoned during opportunities"
            run.pipeline_stage = "completed"
    if abandoned:
        db.commit()


def _new_pipeline_run(db: Session, *, now: datetime) -> RdsReservationCoverageRun:
    run = RdsReservationCoverageRun(
        started_at=now,
        inventory_snapshot_at=now,
        status="RUNNING",
        pipeline_stage="inventory",
        inventory_status="RUNNING",
        opportunity_status="NOT_RUN",
        reconciliation_status="NOT_AVAILABLE",
        billing_validation_status="NOT_AVAILABLE",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _pipeline_status(run: RdsReservationCoverageRun, *, freshness: str) -> str:
    if run.status == "RUNNING":
        return "RUNNING"
    if run.status == "FAILED":
        return "FAILED"
    if freshness == STALE:
        return "STALE"
    if run.opportunity_status == "FAILED":
        return "COMPLETED_WITH_WARNINGS"
    return "COMPLETED"


def _summary(
    run: RdsReservationCoverageRun,
    *,
    inventory: dict[str, Any] | None = None,
    opportunities: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    freshness = classify_rds_inventory_freshness(run.inventory_snapshot_at, now=now)
    return {
        "status": _pipeline_status(run, freshness=freshness),
        "coverage_run_id": run.id,
        "stage": run.pipeline_stage,
        "inventory": {
            "status": run.inventory_status,
            "instances": (inventory or {}).get("rds_instances_found"),
            "reservations": (inventory or {}).get("reservations_found"),
            "errors": len((inventory or {}).get("errors") or []),
            "snapshot_at": run.inventory_snapshot_at,
        },
        "coverage": {
            "status": "NOT_RUN" if run.inventory_status == "FAILED" else run.status,
            "instances_analyzed": run.instances_analyzed,
            "fully_covered": run.fully_covered,
            "partially_covered": run.partially_covered,
            "uncovered": run.uncovered,
            "unknown": run.unknown,
            "billing_validation_status": run.billing_validation_status,
        },
        "opportunities": {
            "status": run.opportunity_status,
            "created": (opportunities or {}).get("created"),
            "updated": (opportunities or {}).get("updated"),
            "resolved": (opportunities or {}).get("resolved"),
        },
        "data_freshness": freshness,
        "completed_at": run.completed_at,
    }


def refresh_rds_reservations(
    db: Session,
    *,
    cloud_account_id: int | None = None,
    validate_billing: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _utc_now(now)
    started_clock = time.monotonic()

    with _pipeline_lock(db):
        _recover_abandoned_runs(db, now=current)
        active = (
            db.query(RdsReservationCoverageRun)
            .filter(RdsReservationCoverageRun.status == "RUNNING")
            .order_by(RdsReservationCoverageRun.id.desc())
            .first()
        )
        if active is not None:
            raise RdsReservationsPipelineBusy(
                f"RDS Reservations refresh is already running (run {active.id})"
            )

        run = _new_pipeline_run(db, now=current)
        logger.info(
            "event=rds_reservations_refresh_started coverage_run_id=%s cloud_account_id=%s "
            "validate_billing=%s",
            run.id,
            cloud_account_id or "all",
            str(validate_billing).lower(),
        )

        inventory: dict[str, Any] | None = None
        try:
            inventory = collect_rds_inventory(db, cloud_account_id=cloud_account_id)
        except Exception as exc:
            db.rollback()
            failed = db.get(RdsReservationCoverageRun, run.id)
            if failed is not None:
                failed.status = "FAILED"
                failed.inventory_status = "FAILED"
                failed.pipeline_stage = "inventory"
                failed.inventory_error_detail = str(exc)[:2000]
                failed.error_detail = "RDS inventory collection failed"
                failed.completed_at = utcnow()
                db.commit()
            logger.exception(
                "event=rds_reservations_refresh_failed coverage_run_id=%s stage=inventory",
                run.id,
            )
            return _summary(failed or run, now=current)

        inventory_errors = list(inventory.get("errors") or [])
        if inventory_errors:
            failed = db.get(RdsReservationCoverageRun, run.id)
            if failed is not None:
                failed.status = "FAILED"
                failed.inventory_status = "FAILED"
                failed.pipeline_stage = "inventory"
                failed.inventory_error_detail = "\n".join(str(item) for item in inventory_errors)[
                    :2000
                ]
                failed.error_detail = (
                    "RDS inventory collection completed with errors; coverage skipped"
                )
                failed.completed_at = utcnow()
                db.commit()
            logger.error(
                "event=rds_reservations_refresh_failed coverage_run_id=%s stage=inventory "
                "instances=%s reservations=%s error_count=%s duration_ms=%s",
                run.id,
                inventory.get("rds_instances_found", 0),
                inventory.get("reservations_found", 0),
                len(inventory_errors),
                int((time.monotonic() - started_clock) * 1000),
            )
            return _summary(failed or run, inventory=inventory, now=current)

        run = db.get(RdsReservationCoverageRun, run.id) or run
        inventory_completed_at = utcnow()
        run.inventory_snapshot_at = (
            effective_rds_inventory_snapshot_at(db, fallback=inventory_completed_at)
            or inventory_completed_at
        )
        run.inventory_status = "COMPLETED"
        run.inventory_error_detail = None
        run.pipeline_stage = "coverage"
        db.commit()
        logger.info(
            "event=rds_inventory_completed coverage_run_id=%s cloud_account_id=%s instances=%s "
            "reservations=%s duration_ms=%s",
            run.id,
            cloud_account_id or "all",
            inventory.get("rds_instances_found", 0),
            inventory.get("reservations_found", 0),
            inventory.get("duration_ms", 0),
        )

        try:
            run = run_rds_reservation_coverage(
                db,
                validate_billing=validate_billing,
                now=current,
                run=run,
                generate_opportunities=False,
            )
        except Exception:
            failed = db.get(RdsReservationCoverageRun, run.id) or run
            logger.exception(
                "event=rds_reservations_refresh_failed coverage_run_id=%s stage=coverage "
                "duration_ms=%s",
                run.id,
                int((time.monotonic() - started_clock) * 1000),
            )
            return _summary(failed, inventory=inventory, now=current)

        run.pipeline_stage = "opportunities"
        run.opportunity_status = "RUNNING"
        run.opportunity_error_detail = None
        db.commit()
        opportunity_payload: dict[str, Any] | None = None
        try:
            opportunity_result = generate_rds_reservation_opportunities(
                db,
                coverage_run_id=run.id,
                now=current,
            )
            db.commit()
            opportunity_payload = opportunity_result.to_dict()
            run = db.get(RdsReservationCoverageRun, run.id) or run
            run.opportunity_status = "COMPLETED"
            logger.info(
                "event=rds_opportunities_completed coverage_run_id=%s "
                "created=%s updated=%s resolved=%s",
                run.id,
                opportunity_result.created,
                opportunity_result.updated,
                opportunity_result.resolved,
            )
        except Exception as exc:
            db.rollback()
            run = db.get(RdsReservationCoverageRun, run.id) or run
            run.opportunity_status = "FAILED"
            run.opportunity_error_detail = str(exc)[:2000]
            logger.exception(
                "event=rds_opportunities_failed coverage_run_id=%s",
                run.id,
            )

        run.pipeline_stage = "completed"
        run.completed_at = utcnow()
        db.commit()
        result = _summary(
            run,
            inventory=inventory,
            opportunities=opportunity_payload,
            now=current,
        )
        logger.info(
            "event=rds_reservations_refresh_completed coverage_run_id=%s status=%s instances=%s "
            "reservations=%s opportunities_created=%s duration_ms=%s",
            run.id,
            result["status"],
            run.instances_analyzed,
            run.reservations_analyzed,
            (opportunity_payload or {}).get("created", 0),
            int((time.monotonic() - started_clock) * 1000),
        )
        return result


def get_rds_reservations_operational_status(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _utc_now(now)
    latest = (
        db.query(RdsReservationCoverageRun).order_by(RdsReservationCoverageRun.id.desc()).first()
    )
    successful = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.status == "COMPLETED")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )

    if latest is None:
        return {
            "last_inventory_collection_at": None,
            "last_coverage_run_at": None,
            "last_successful_coverage_run_at": None,
            "coverage_run_id": None,
            "latest_run_id": None,
            "pipeline_status": "NEVER_EXECUTED",
            "pipeline_stage": None,
            "inventory_status": "NOT_RUN",
            "coverage_status": "NOT_RUN",
            "opportunity_status": "NOT_RUN",
            "billing_validation_status": "NOT_AVAILABLE",
            "data_freshness": "UNKNOWN",
            "freshness_threshold_hours": settings.rds_reservation_inventory_freshness_hours,
            "error_detail": None,
        }

    latest_inventory = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.inventory_status == "COMPLETED")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )
    if latest_inventory is None:
        latest_inventory = successful

    freshness = classify_rds_inventory_freshness(
        successful.inventory_snapshot_at if successful is not None else None,
        now=current,
    )
    pipeline_status = _pipeline_status(latest, freshness=freshness)
    coverage_status = latest.status
    if latest.inventory_status == "FAILED" and latest.pipeline_stage == "inventory":
        coverage_status = "NOT_RUN"

    inventory_status = latest.inventory_status
    if inventory_status == "UNKNOWN" and latest.status == "COMPLETED":
        inventory_status = "COMPLETED"

    return {
        "last_inventory_collection_at": (
            latest_inventory.inventory_snapshot_at if latest_inventory is not None else None
        ),
        "last_coverage_run_at": (
            latest.completed_at
            if latest.pipeline_stage != "inventory" or latest.status == "COMPLETED"
            else None
        ),
        "last_successful_coverage_run_at": successful.completed_at if successful else None,
        "coverage_run_id": successful.id if successful else None,
        "latest_run_id": latest.id,
        "pipeline_status": pipeline_status,
        "pipeline_stage": latest.pipeline_stage,
        "inventory_status": inventory_status,
        "coverage_status": coverage_status,
        "opportunity_status": latest.opportunity_status,
        "billing_validation_status": latest.billing_validation_status,
        "data_freshness": freshness,
        "freshness_threshold_hours": settings.rds_reservation_inventory_freshness_hours,
        "error_detail": (
            latest.inventory_error_detail or latest.error_detail or latest.opportunity_error_detail
        ),
    }


def rds_reservations_refresh_due(db: Session, *, now: datetime | None = None) -> bool:
    current = _utc_now(now)
    has_aws = (
        db.query(CloudAccount.id)
        .filter(CloudAccount.provider == "aws", CloudAccount.enabled.is_(True))
        .first()
        is not None
    )
    if not has_aws:
        return False
    running = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.status == "RUNNING")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )
    if running is not None:
        return normalize_utc(running.started_at) < current - _RUNNING_TIMEOUT
    latest_success = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.status == "COMPLETED")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )
    if latest_success is None:
        return True
    return (
        classify_rds_inventory_freshness(latest_success.inventory_snapshot_at, now=current) == STALE
    )
