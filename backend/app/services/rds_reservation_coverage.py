from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.rds_coverage import (
    RdsInstanceReservationCoverage,
    RdsReservationAllocation,
    RdsReservationCoverageRun,
    RdsReservationUtilization,
)
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.aws_auth import BOTO_CONFIG, assume_account_session
from app.services.aws_cost_explorer import AwsBillingUpstreamError
from app.services.rds_cost_explorer import RdsCostExplorerClient
from app.services.rds_reservation_engine import RdsReservationCoverageEngine
from app.services.rds_reservation_freshness import effective_rds_inventory_snapshot_at
from app.services.rds_reservation_rules import (
    COVERAGE_FULL,
    COVERAGE_PARTIAL,
    COVERAGE_UNCOVERED,
    COVERAGE_UNKNOWN,
    ZERO,
    BillingScopeContext,
    _safe_percentage,
    is_active_reservation,
    is_reservation_coverage_eligible_instance,
    normalize_rds_engine,
)

logger = logging.getLogger(__name__)


def _cluster_metadata(client: Any) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    paginator = client.get_paginator("describe_db_clusters")
    for page in paginator.paginate():
        for cluster in page.get("DBClusters", []):
            identifier = str(cluster.get("DBClusterIdentifier") or "")
            if not identifier:
                continue
            engine = normalize_rds_engine(str(cluster.get("Engine") or ""))
            if engine in {"aurora-mysql", "aurora-postgresql"}:
                topology = "aurora_cluster"
            elif cluster.get("DBClusterInstanceClass"):
                topology = "multi_az_cluster_member"
            else:
                topology = None
            result[identifier] = {
                "deployment_topology": topology,
                "cluster_storage_type": cluster.get("StorageType"),
            }
    return result


def enrich_rds_cluster_metadata(db: Session, instances: list[AwsRdsInstance]) -> None:
    grouped: dict[tuple[int, str], list[AwsRdsInstance]] = defaultdict(list)
    for instance in instances:
        if instance.cluster_identifier:
            grouped[(instance.cloud_account_id, instance.region)].append(instance)
    if not grouped:
        return

    accounts = {
        account.id: account
        for account in (
            db.query(CloudAccount).filter(CloudAccount.id.in_({key[0] for key in grouped})).all()
        )
    }
    for (cloud_account_id, region), rows in sorted(grouped.items()):
        for row in rows:
            row.deployment_topology = None
            row.cluster_storage_type = None
        cloud_account = accounts.get(cloud_account_id)
        aws_account = cloud_account.aws_configuration if cloud_account else None
        if aws_account is None:
            continue
        try:
            session = assume_account_session(aws_account)
            client = session.client("rds", region_name=region, config=BOTO_CONFIG)
            metadata = _cluster_metadata(client)
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "RDS cluster metadata enrichment unavailable account=%s region=%s error=%s",
                rows[0].account_id,
                region,
                exc.__class__.__name__,
            )
            continue
        for row in rows:
            item = metadata.get(row.cluster_identifier or "")
            if not item:
                continue
            row.deployment_topology = item.get("deployment_topology")
            row.cluster_storage_type = item.get("cluster_storage_type")


def _reconciliation_status(calculated: Decimal, observed: Decimal) -> str:
    variance = abs(calculated - observed)
    if variance <= Decimal("0.5"):
        return "MATCH"
    if variance <= Decimal("5"):
        return "MINOR_VARIANCE"
    return "MISMATCH"


def _observe_billing_coverage(
    db: Session, *, accounts: list[CloudAccount], end_date: date
) -> tuple[Decimal | None, str, str]:
    start_date = end_date - timedelta(days=1)
    total_running = ZERO
    total_reserved = ZERO
    available = 0
    unavailable = 0
    details: list[str] = []

    for cloud_account in accounts:
        aws_account = cloud_account.aws_configuration
        if aws_account is None:
            unavailable += 1
            continue
        try:
            session = assume_account_session(aws_account)
            client = RdsCostExplorerClient(session)
            observation = client.get_rds_reservation_coverage(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                linked_account_id=aws_account.aws_account_id,
            )
        except (AwsBillingUpstreamError, ClientError, BotoCoreError) as exc:
            unavailable += 1
            code = getattr(exc, "code", exc.__class__.__name__)
            details.append(f"{aws_account.aws_account_id}:{code}")
            continue
        available += 1
        total_running += observation.total_running_units
        total_reserved += observation.reserved_units

    if not accounts or available != len(accounts) or unavailable:
        detail = f"billing validation available for {available}/{len(accounts)} accounts"
        if details:
            detail += "; " + ", ".join(details)
        return None, "NOT_AVAILABLE", detail
    observed = _safe_percentage(total_reserved, total_running)
    detail = f"last complete day {start_date.isoformat()}..{end_date.isoformat()}"
    return observed, "AVAILABLE", detail


def _prepare_run(
    db: Session,
    *,
    now: datetime,
    run: RdsReservationCoverageRun | None,
) -> RdsReservationCoverageRun:
    if run is None:
        snapshot_at = effective_rds_inventory_snapshot_at(db, fallback=now) or now
        run = RdsReservationCoverageRun(
            started_at=now,
            inventory_snapshot_at=snapshot_at,
            status="RUNNING",
            pipeline_stage="coverage",
            inventory_status="UNKNOWN",
            opportunity_status="NOT_RUN",
            reconciliation_status="NOT_AVAILABLE",
            billing_validation_status="NOT_AVAILABLE",
        )
        db.add(run)
    else:
        run.status = "RUNNING"
        run.pipeline_stage = "coverage"
        run.completed_at = None
        run.error_detail = None
        run.reconciliation_status = "NOT_AVAILABLE"
        run.reconciliation_detail = None
        run.billing_validation_status = "NOT_AVAILABLE"
        run.aws_observed_coverage_percentage = None
    db.commit()
    db.refresh(run)
    return run


def _generate_opportunities_for_completed_run(
    db: Session,
    *,
    run_id: int,
    now: datetime,
) -> None:
    run = db.get(RdsReservationCoverageRun, run_id)
    if run is None:
        return
    run.pipeline_stage = "opportunities"
    run.opportunity_status = "RUNNING"
    run.opportunity_error_detail = None
    db.commit()
    try:
        from app.services.rds_reservation_opportunities import (
            generate_rds_reservation_opportunities,
        )

        result = generate_rds_reservation_opportunities(db, coverage_run_id=run_id, now=now)
        db.commit()
        run = db.get(RdsReservationCoverageRun, run_id)
        if run is not None:
            run.opportunity_status = "COMPLETED"
            run.pipeline_stage = "completed"
            run.completed_at = utcnow()
            db.commit()
        logger.info(
            "event=rds_opportunities_completed coverage_run_id=%s "
            "created=%s updated=%s resolved=%s",
            run_id,
            result.created,
            result.updated,
            result.resolved,
        )
    except Exception as exc:
        db.rollback()
        run = db.get(RdsReservationCoverageRun, run_id)
        if run is not None:
            run.opportunity_status = "FAILED"
            run.opportunity_error_detail = str(exc)[:2000]
            run.pipeline_stage = "completed"
            run.completed_at = utcnow()
            db.commit()
        logger.exception("event=rds_opportunities_failed coverage_run_id=%s", run_id)


def run_rds_reservation_coverage(
    db: Session,
    *,
    validate_billing: bool = True,
    now: datetime | None = None,
    billing_scope: BillingScopeContext | None = None,
    run: RdsReservationCoverageRun | None = None,
    generate_opportunities: bool = True,
) -> RdsReservationCoverageRun:
    now = now or utcnow()
    started_clock = time.monotonic()
    run = _prepare_run(db, now=now, run=run)

    try:
        instances = (
            db.query(AwsRdsInstance)
            .filter(AwsRdsInstance.is_active.is_(True))
            .order_by(
                AwsRdsInstance.account_id,
                AwsRdsInstance.region,
                AwsRdsInstance.db_instance_identifier,
            )
            .all()
        )
        reservations = (
            db.query(AwsRdsReservedInstance)
            .filter(AwsRdsReservedInstance.is_active.is_(True))
            .order_by(
                AwsRdsReservedInstance.account_id,
                AwsRdsReservedInstance.region,
                AwsRdsReservedInstance.reserved_db_instance_id,
            )
            .all()
        )
        enrich_rds_cluster_metadata(db, instances)
        eligible_instances = [
            item for item in instances if is_reservation_coverage_eligible_instance(item)
        ]
        active_reservations = [item for item in reservations if is_active_reservation(item, at=now)]
        analysis = RdsReservationCoverageEngine(billing_scope).analyze(
            eligible_instances, active_reservations, at=now
        )

        for result in analysis.instances:
            db.add(
                RdsInstanceReservationCoverage(
                    coverage_run_id=run.id,
                    rds_instance_id=result.instance.id,
                    account_id=result.instance.account_id,
                    region=result.instance.region,
                    required_units=result.required_units,
                    covered_units=result.covered_units,
                    uncovered_units=result.uncovered_units,
                    coverage_percentage=result.coverage_percentage,
                    coverage_status=result.coverage_status,
                    coverage_scope=result.coverage_scope,
                    calculation_method=result.calculation_method,
                    explanation=result.explanation,
                )
            )
        for allocation in analysis.allocations:
            required = next(
                item.required_units
                for item in analysis.instances
                if item.instance.id == allocation.instance.id
            )
            db.add(
                RdsReservationAllocation(
                    coverage_run_id=run.id,
                    reservation_id=allocation.reservation.id,
                    rds_instance_id=allocation.instance.id,
                    allocated_units=allocation.units,
                    allocation_percentage=_safe_percentage(allocation.units, required),
                    match_type=allocation.match_type,
                    allocation_scope=allocation.allocation_scope,
                    reason={"code": allocation.reason},
                )
            )
        for result in analysis.reservations:
            db.add(
                RdsReservationUtilization(
                    coverage_run_id=run.id,
                    reservation_id=result.reservation.id,
                    total_units=result.total_units,
                    allocated_units=result.allocated_units,
                    unused_units=result.unused_units,
                    utilization_percentage=result.utilization_percentage,
                )
            )

        statuses = defaultdict(int)
        for item in analysis.instances:
            statuses[item.coverage_status] += 1
        required_units = sum((item.required_units for item in analysis.instances), ZERO)
        covered_units = sum((item.covered_units for item in analysis.instances), ZERO)
        reserved_units = sum((item.total_units for item in analysis.reservations), ZERO)
        allocated_units = sum((item.allocated_units for item in analysis.reservations), ZERO)
        accounts = sorted({item.account_id for item in eligible_instances})

        run.accounts_analyzed = len(accounts)
        run.instances_analyzed = len(analysis.instances)
        run.reservations_analyzed = len(analysis.reservations)
        run.fully_covered = statuses[COVERAGE_FULL]
        run.partially_covered = statuses[COVERAGE_PARTIAL]
        run.uncovered = statuses[COVERAGE_UNCOVERED]
        run.unknown = statuses[COVERAGE_UNKNOWN]
        run.required_units = required_units
        run.covered_units = covered_units
        run.uncovered_units = max(ZERO, required_units - covered_units)
        run.reserved_units = reserved_units
        run.allocated_reserved_units = allocated_units
        run.unused_reserved_units = max(ZERO, reserved_units - allocated_units)
        run.calculated_coverage_percentage = _safe_percentage(covered_units, required_units)

        if validate_billing:
            cloud_accounts = (
                db.query(CloudAccount)
                .filter(CloudAccount.native_account_id.in_(accounts))
                .order_by(CloudAccount.id)
                .all()
            )
            observed, validation_status, detail = _observe_billing_coverage(
                db, accounts=cloud_accounts, end_date=now.astimezone(UTC).date()
            )
            run.aws_observed_coverage_percentage = observed
            run.billing_validation_status = validation_status
            run.reconciliation_detail = detail
            if observed is not None:
                run.reconciliation_status = _reconciliation_status(
                    run.calculated_coverage_percentage, observed
                )
        run.status = "COMPLETED"
        run.completed_at = utcnow()
        run.pipeline_stage = "opportunities" if generate_opportunities else "coverage"
        run_id = run.id
        db.commit()
        logger.info(
            "event=rds_coverage_completed coverage_run_id=%s instances=%s reservations=%s full=%s "
            "partial=%s uncovered=%s unknown=%s required_units=%s covered_units=%s "
            "unused_reserved_units=%s allocations=%s duration_ms=%s reconciliation=%s",
            run_id,
            run.instances_analyzed,
            run.reservations_analyzed,
            run.fully_covered,
            run.partially_covered,
            run.uncovered,
            run.unknown,
            run.required_units,
            run.covered_units,
            run.unused_reserved_units,
            len(analysis.allocations),
            int((time.monotonic() - started_clock) * 1000),
            run.reconciliation_status,
        )

        if generate_opportunities:
            _generate_opportunities_for_completed_run(db, run_id=run_id, now=now)

        refreshed = db.get(RdsReservationCoverageRun, run_id)
        return refreshed or run
    except Exception as exc:
        db.rollback()
        failed = db.get(RdsReservationCoverageRun, run.id)
        if failed is not None:
            failed.status = "FAILED"
            failed.pipeline_stage = "coverage"
            failed.completed_at = utcnow()
            failed.error_detail = str(exc)[:2000]
            db.commit()
        logger.exception("event=rds_coverage_failed coverage_run_id=%s", run.id)
        raise
