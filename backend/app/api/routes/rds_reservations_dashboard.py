from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.base import utcnow
from app.db.session import get_db
from app.models.account import CloudAccount
from app.models.finding import Finding, OpportunityPresenceStatus
from app.models.rds_coverage import (
    RdsInstanceReservationCoverage,
    RdsReservationAllocation,
    RdsReservationCoverageRun,
    RdsReservationUtilization,
)
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_inventory import normalize_rds_engine
from app.services.rds_reservation_opportunities import RDS_RESERVATION_RULES

router = APIRouter(
    prefix="/rds/reservations-dashboard",
    tags=["rds-reservations-dashboard"],
    dependencies=[Depends(require_admin)],
)

ZERO = Decimal("0")


def _latest_completed_run(db: Session) -> RdsReservationCoverageRun:
    run = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.status == "COMPLETED")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RDS_COVERAGE_NOT_CALCULATED",
                "message": "No completed RDS reservation coverage run found",
            },
        )
    return run


def _float(value: Decimal | int | float | None) -> float:
    return float(value or ZERO)


def _percentage(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= ZERO:
        return 0.0
    return float(max(ZERO, min(Decimal("100"), numerator / denominator * Decimal("100"))))


def _days_remaining(expiration_at: datetime, *, now: datetime) -> int:
    value = expiration_at if expiration_at.tzinfo else expiration_at.replace(tzinfo=UTC)
    seconds = (value.astimezone(UTC) - now).total_seconds()
    if seconds == 0:
        return 0
    if seconds > 0:
        return int((seconds + 86399) // 86400)
    return -int((abs(seconds) + 86399) // 86400)


def _account_payload(account: CloudAccount | None, native_id: str) -> dict[str, Any]:
    return {
        "id": account.id if account else None,
        "name": account.name if account else None,
        "account_id": native_id,
    }


def _apply_coverage_filters(
    query,
    *,
    account: str | None,
    region: str | None,
    engine: str | None,
    family: str | None,
    instance_class: str | None,
    coverage_status: str | None,
):
    if account:
        query = query.filter(RdsInstanceReservationCoverage.account_id == account)
    if region:
        query = query.filter(RdsInstanceReservationCoverage.region == region)
    if engine:
        query = query.filter(AwsRdsInstance.engine_normalized == normalize_rds_engine(engine))
    if family:
        query = query.filter(AwsRdsInstance.instance_family == family)
    if instance_class:
        query = query.filter(AwsRdsInstance.db_instance_class == instance_class)
    if coverage_status:
        query = query.filter(
            RdsInstanceReservationCoverage.coverage_status == coverage_status.upper()
        )
    return query


def _apply_reservation_filters(
    query,
    *,
    account: str | None,
    region: str | None,
    engine: str | None,
    family: str | None,
    instance_class: str | None,
    reservation_status: str | None,
    expiration_range: str | None,
    now: datetime,
):
    if account:
        query = query.filter(AwsRdsReservedInstance.account_id == account)
    if region:
        query = query.filter(AwsRdsReservedInstance.region == region)
    if engine:
        query = query.filter(
            AwsRdsReservedInstance.engine_normalized == normalize_rds_engine(engine)
        )
    if family:
        query = query.filter(AwsRdsReservedInstance.instance_family == family)
    if instance_class:
        query = query.filter(AwsRdsReservedInstance.db_instance_class == instance_class)
    if reservation_status:
        query = query.filter(func.lower(AwsRdsReservedInstance.state) == reservation_status.lower())
    if expiration_range:
        normalized = expiration_range.upper()
        if normalized == "LE_7":
            query = query.filter(
                AwsRdsReservedInstance.expiration_at >= now,
                AwsRdsReservedInstance.expiration_at <= now + timedelta(days=7),
            )
        elif normalized == "LE_15":
            query = query.filter(
                AwsRdsReservedInstance.expiration_at >= now,
                AwsRdsReservedInstance.expiration_at <= now + timedelta(days=15),
            )
        elif normalized == "LE_30":
            query = query.filter(
                AwsRdsReservedInstance.expiration_at >= now,
                AwsRdsReservedInstance.expiration_at <= now + timedelta(days=30),
            )
        elif normalized == "GT_30":
            query = query.filter(AwsRdsReservedInstance.expiration_at > now + timedelta(days=30))
        elif normalized == "EXPIRED":
            query = query.filter(AwsRdsReservedInstance.expiration_at < now)
    return query


@router.get("/summary")
def summary(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    instance_class: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _latest_completed_run(db)
    now = utcnow()

    coverage_query = (
        db.query(RdsInstanceReservationCoverage, AwsRdsInstance)
        .join(
            AwsRdsInstance,
            AwsRdsInstance.id == RdsInstanceReservationCoverage.rds_instance_id,
        )
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
    )
    coverage_query = _apply_coverage_filters(
        coverage_query,
        account=account,
        region=region,
        engine=engine,
        family=family,
        instance_class=instance_class,
        coverage_status=None,
    )
    coverage_rows = coverage_query.all()

    utilization_query = (
        db.query(RdsReservationUtilization, AwsRdsReservedInstance)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationUtilization.reservation_id,
        )
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
    )
    utilization_query = _apply_reservation_filters(
        utilization_query,
        account=account,
        region=region,
        engine=engine,
        family=family,
        instance_class=instance_class,
        reservation_status=None,
        expiration_range=None,
        now=now,
    )
    utilization_rows = utilization_query.all()

    statuses = {"FULL": 0, "PARTIAL": 0, "UNCOVERED": 0, "UNKNOWN": 0}
    required = ZERO
    covered = ZERO
    uncovered = ZERO
    inventory_times: list[datetime] = []
    for coverage, instance in coverage_rows:
        statuses[coverage.coverage_status] = statuses.get(coverage.coverage_status, 0) + 1
        required += coverage.required_units
        covered += coverage.covered_units
        uncovered += coverage.uncovered_units
        if instance.collected_at:
            inventory_times.append(instance.collected_at)

    reserved = ZERO
    allocated = ZERO
    unused = ZERO
    expiring_30 = 0
    reservation_inventory_times: list[datetime] = []
    for utilization, reservation in utilization_rows:
        reserved += utilization.total_units
        allocated += utilization.allocated_units
        unused += utilization.unused_units
        if reservation.collected_at:
            reservation_inventory_times.append(reservation.collected_at)
        if now <= reservation.expiration_at <= now + timedelta(days=30):
            expiring_30 += 1

    inventory_candidates = inventory_times + reservation_inventory_times
    inventory_updated_at = (
        max(inventory_candidates) if inventory_candidates else run.inventory_snapshot_at
    )

    return {
        "coverage_run_id": run.id,
        "rds": {
            "total": len(coverage_rows),
            "fully_covered": statuses.get("FULL", 0),
            "partially_covered": statuses.get("PARTIAL", 0),
            "uncovered": statuses.get("UNCOVERED", 0),
            "unknown": statuses.get("UNKNOWN", 0),
        },
        "coverage": {
            "required_units": _float(required),
            "covered_units": _float(covered),
            "uncovered_units": _float(uncovered),
            "coverage_percentage": _percentage(covered, required),
        },
        "reservations": {
            "active": len(utilization_rows),
            "reserved_units": _float(reserved),
            "used_units": _float(allocated),
            "unused_units": _float(unused),
            "utilization_percentage": _percentage(allocated, reserved),
        },
        "expiring_next_30_days": expiring_30,
        "billing": {
            "technical_coverage_percentage": _percentage(covered, required),
            "aws_observed_coverage_percentage": (
                None
                if run.aws_observed_coverage_percentage is None
                else float(run.aws_observed_coverage_percentage)
            ),
            "validation_status": run.billing_validation_status,
            "reconciliation_status": run.reconciliation_status,
            "reconciliation_detail": run.reconciliation_detail,
        },
        "freshness": {
            "inventory_updated_at": inventory_updated_at,
            "coverage_calculated_at": run.completed_at,
            "billing_data_reference": run.reconciliation_detail,
        },
    }


@router.get("/coverage")
def coverage(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    instance_class: str | None = Query(default=None, max_length=64),
    coverage_status: str | None = Query(default=None, max_length=24),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: Literal["account", "region", "instance", "coverage", "required"] = "account",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _latest_completed_run(db)
    query = (
        db.query(RdsInstanceReservationCoverage, AwsRdsInstance, CloudAccount)
        .join(
            AwsRdsInstance,
            AwsRdsInstance.id == RdsInstanceReservationCoverage.rds_instance_id,
        )
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsInstance.cloud_account_id)
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
    )
    query = _apply_coverage_filters(
        query,
        account=account,
        region=region,
        engine=engine,
        family=family,
        instance_class=instance_class,
        coverage_status=coverage_status,
    )
    sort_columns = {
        "account": RdsInstanceReservationCoverage.account_id,
        "region": RdsInstanceReservationCoverage.region,
        "instance": AwsRdsInstance.db_instance_identifier,
        "coverage": RdsInstanceReservationCoverage.coverage_percentage,
        "required": RdsInstanceReservationCoverage.required_units,
    }
    sort_column = sort_columns[sort]
    ordered = desc(sort_column) if order == "desc" else asc(sort_column)
    total = query.count()
    rows = (
        query.order_by(ordered, AwsRdsInstance.db_instance_identifier)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    instance_ids = [coverage_row.rds_instance_id for coverage_row, _, _ in rows]
    allocations = (
        db.query(RdsReservationAllocation, AwsRdsReservedInstance, CloudAccount)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationAllocation.reservation_id,
        )
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsReservedInstance.cloud_account_id)
        .filter(
            RdsReservationAllocation.coverage_run_id == run.id,
            RdsReservationAllocation.rds_instance_id.in_(instance_ids),
        )
        .order_by(RdsReservationAllocation.rds_instance_id, RdsReservationAllocation.id)
        .all()
        if instance_ids
        else []
    )
    by_instance: dict[int, list[dict[str, Any]]] = {}
    for allocation, reservation, reservation_account in allocations:
        by_instance.setdefault(allocation.rds_instance_id, []).append(
            {
                "allocation_id": allocation.id,
                "reservation_id": reservation.reserved_db_instance_id,
                "reservation_db_id": reservation.id,
                "reservation_account": _account_payload(
                    reservation_account, reservation.account_id
                ),
                "reservation_class": reservation.db_instance_class,
                "allocated_units": _float(allocation.allocated_units),
                "allocation_percentage": _float(allocation.allocation_percentage),
                "match_type": allocation.match_type,
                "allocation_scope": allocation.allocation_scope,
                "reason": allocation.reason or {},
            }
        )

    items: list[dict[str, Any]] = []
    for coverage_row, instance, cloud_account in rows:
        items.append(
            {
                "instance_id": instance.id,
                "instance": instance.db_instance_identifier,
                "account": _account_payload(cloud_account, instance.account_id),
                "region": instance.region,
                "engine": instance.engine_normalized,
                "engine_version": instance.engine_version,
                "instance_class": instance.db_instance_class,
                "family": instance.instance_family,
                "size": instance.instance_size,
                "topology": instance.deployment_topology
                or ("multi_az" if instance.multi_az else "single_az"),
                "multi_az": bool(instance.multi_az),
                "license_model": instance.license_model,
                "required_units": _float(coverage_row.required_units),
                "covered_units": _float(coverage_row.covered_units),
                "uncovered_units": _float(coverage_row.uncovered_units),
                "coverage_percentage": _float(coverage_row.coverage_percentage),
                "coverage_status": coverage_row.coverage_status,
                "coverage_scope": coverage_row.coverage_scope,
                "calculation_method": coverage_row.calculation_method,
                "allocations": by_instance.get(instance.id, []),
                "explanation": coverage_row.explanation or {},
                "inventory_updated_at": instance.collected_at,
            }
        )
    return {
        "coverage_run_id": run.id,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/reservations")
def reservations(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    instance_class: str | None = Query(default=None, max_length=64),
    reservation_status: str | None = Query(default=None, max_length=24),
    expiration_range: str | None = Query(
        default=None, pattern="^(LE_7|LE_15|LE_30|GT_30|EXPIRED)$"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: Literal["account", "region", "reservation", "utilization", "expiration"] = "expiration",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = _latest_completed_run(db)
    now = utcnow()
    query = (
        db.query(RdsReservationUtilization, AwsRdsReservedInstance, CloudAccount)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationUtilization.reservation_id,
        )
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsReservedInstance.cloud_account_id)
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
    )
    query = _apply_reservation_filters(
        query,
        account=account,
        region=region,
        engine=engine,
        family=family,
        instance_class=instance_class,
        reservation_status=reservation_status,
        expiration_range=expiration_range,
        now=now,
    )
    sort_columns = {
        "account": AwsRdsReservedInstance.account_id,
        "region": AwsRdsReservedInstance.region,
        "reservation": AwsRdsReservedInstance.reserved_db_instance_id,
        "utilization": RdsReservationUtilization.utilization_percentage,
        "expiration": AwsRdsReservedInstance.expiration_at,
    }
    sort_column = sort_columns[sort]
    ordered = desc(sort_column) if order == "desc" else asc(sort_column)
    total = query.count()
    rows = (
        query.order_by(ordered, AwsRdsReservedInstance.reserved_db_instance_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    reservation_ids = [reservation.id for _, reservation, _ in rows]
    allocation_rows = (
        db.query(RdsReservationAllocation, AwsRdsInstance, CloudAccount)
        .join(AwsRdsInstance, AwsRdsInstance.id == RdsReservationAllocation.rds_instance_id)
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsInstance.cloud_account_id)
        .filter(
            RdsReservationAllocation.coverage_run_id == run.id,
            RdsReservationAllocation.reservation_id.in_(reservation_ids),
        )
        .order_by(RdsReservationAllocation.reservation_id, RdsReservationAllocation.id)
        .all()
        if reservation_ids
        else []
    )
    workloads_by_reservation: dict[int, list[dict[str, Any]]] = {}
    for allocation, instance, workload_account in allocation_rows:
        workloads_by_reservation.setdefault(allocation.reservation_id, []).append(
            {
                "allocation_id": allocation.id,
                "instance": instance.db_instance_identifier,
                "instance_id": instance.id,
                "workload_account": _account_payload(workload_account, instance.account_id),
                "allocated_units": _float(allocation.allocated_units),
                "match_type": allocation.match_type,
                "allocation_scope": allocation.allocation_scope,
                "reason": allocation.reason or {},
            }
        )

    expiring_findings = (
        db.query(Finding)
        .filter(
            Finding.provider == "aws",
            Finding.service == "rds",
            Finding.rule_key == "RDS_RESERVATION_EXPIRING",
            Finding.presence_status == OpportunityPresenceStatus.ACTIVE.value,
            Finding.archived_at.is_(None),
            Finding.resource_id.in_(
                [reservation.reserved_db_instance_id for _, reservation, _ in rows]
            ),
        )
        .all()
        if rows
        else []
    )
    expiring_by_id = {finding.resource_id: finding for finding in expiring_findings}

    items = []
    for utilization, reservation, cloud_account in rows:
        expiring = expiring_by_id.get(reservation.reserved_db_instance_id)
        metadata = expiring.provider_metadata if expiring else {}
        items.append(
            {
                "reservation_id": reservation.id,
                "reservation": reservation.reserved_db_instance_id,
                "offering_id": reservation.offering_id,
                "account": _account_payload(cloud_account, reservation.account_id),
                "region": reservation.region,
                "engine": reservation.engine_normalized,
                "instance_class": reservation.db_instance_class,
                "family": reservation.instance_family,
                "size": reservation.instance_size,
                "quantity": reservation.instance_count,
                "multi_az": bool(reservation.multi_az),
                "offering_type": reservation.offering_type,
                "offering_class": reservation.offering_class,
                "currency": reservation.currency_code,
                "fixed_price": _float(reservation.fixed_price),
                "recurring_charges": reservation.recurring_charges,
                "state": reservation.state,
                "start_time": reservation.start_time,
                "expiration_at": reservation.expiration_at,
                "days_remaining": _days_remaining(reservation.expiration_at, now=now),
                "total_capacity": _float(utilization.total_units),
                "allocated_capacity": _float(utilization.allocated_units),
                "unused_capacity": _float(utilization.unused_units),
                "utilization_percentage": _float(utilization.utilization_percentage),
                "workloads": workloads_by_reservation.get(reservation.id, []),
                "expiration_severity": expiring.severity if expiring else None,
                "expiration_band": metadata.get("expiration_band") if metadata else None,
                "recommended_action": (metadata.get("recommended_action") if metadata else None),
                "inventory_updated_at": reservation.collected_at,
            }
        )
    return {
        "coverage_run_id": run.id,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/opportunities")
def opportunities(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    instance_class: str | None = Query(default=None, max_length=64),
    opportunity_type: str | None = Query(default=None, max_length=64),
    opportunity_status: str | None = Query(default=None, pattern="^(open|treated|rejected)$"),
    severity: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: Literal["first_seen", "last_seen", "severity"] = "last_seen",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = db.query(Finding).filter(
        Finding.provider == "aws",
        Finding.service == "rds",
        Finding.rule_key.in_(RDS_RESERVATION_RULES),
        Finding.presence_status == OpportunityPresenceStatus.ACTIVE.value,
        Finding.archived_at.is_(None),
    )
    if account:
        query = query.filter(Finding.account_id == account)
    if region:
        query = query.filter(Finding.region == region)
    if opportunity_type:
        query = query.filter(Finding.rule_key == opportunity_type)
    if opportunity_status:
        query = query.filter(Finding.status == opportunity_status)
    if severity:
        query = query.filter(Finding.severity == severity)
    if engine:
        query = query.filter(
            Finding.provider_metadata["engine"].as_string() == normalize_rds_engine(engine)
        )
    if family:
        query = query.filter(Finding.provider_metadata["instance_family"].as_string() == family)
    if instance_class:
        query = query.filter(
            Finding.provider_metadata["instance_class"].as_string() == instance_class
        )

    sort_columns = {
        "first_seen": Finding.first_seen_at,
        "last_seen": Finding.last_seen_at,
        "severity": Finding.severity,
    }
    sort_column = sort_columns[sort]
    ordered = desc(sort_column) if order == "desc" else asc(sort_column)
    total = query.count()
    rows = query.order_by(ordered, Finding.id).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": finding.id,
                "type": finding.rule_key,
                "resource": finding.resource_name or finding.resource_id,
                "resource_id": finding.resource_id,
                "resource_type": finding.resource_type,
                "account_id": finding.account_id,
                "account_name": (finding.provider_metadata or {}).get("account_name"),
                "region": finding.region,
                "severity": finding.severity,
                "status": finding.status,
                "presence_status": finding.presence_status,
                "first_seen_at": finding.first_seen_at,
                "last_seen_at": finding.last_seen_at,
                "title": finding.title,
                "description": finding.description,
                "recommended_action": ((finding.provider_metadata or {}).get("recommended_action")),
                "metadata": finding.provider_metadata or {},
            }
            for finding in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/options")
def options(db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _latest_completed_run(db)
    coverage_rows = (
        db.query(AwsRdsInstance, CloudAccount)
        .join(
            RdsInstanceReservationCoverage,
            RdsInstanceReservationCoverage.rds_instance_id == AwsRdsInstance.id,
        )
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsInstance.cloud_account_id)
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
        .all()
    )
    reservation_rows = (
        db.query(AwsRdsReservedInstance, CloudAccount)
        .join(
            RdsReservationUtilization,
            RdsReservationUtilization.reservation_id == AwsRdsReservedInstance.id,
        )
        .outerjoin(CloudAccount, CloudAccount.id == AwsRdsReservedInstance.cloud_account_id)
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
        .all()
    )
    accounts: dict[str, dict[str, Any]] = {}
    regions: set[str] = set()
    engines: set[str] = set()
    families: set[str] = set()
    classes: set[str] = set()
    for item, cloud_account in [*coverage_rows, *reservation_rows]:
        accounts[item.account_id] = _account_payload(cloud_account, item.account_id)
        if item.region:
            regions.add(item.region)
        if item.engine_normalized:
            engines.add(item.engine_normalized)
        if item.instance_family:
            families.add(item.instance_family)
        if item.db_instance_class:
            classes.add(item.db_instance_class)
    return {
        "accounts": sorted(
            accounts.values(),
            key=lambda item: ((item.get("name") or ""), item["account_id"]),
        ),
        "regions": sorted(regions),
        "engines": sorted(engines),
        "families": sorted(families),
        "instance_classes": sorted(classes),
    }
