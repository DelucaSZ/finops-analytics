from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.rds_coverage import (
    RdsInstanceReservationCoverage,
    RdsReservationAllocation,
    RdsReservationCoverageRun,
    RdsReservationUtilization,
)
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_inventory import (
    collect_rds_inventory,
    days_until_expiration,
    normalize_rds_engine,
)
from app.services.rds_reservation_coverage import run_rds_reservation_coverage

router = APIRouter(
    prefix="/rds",
    tags=["rds-inventory"],
    dependencies=[Depends(require_admin)],
)


def _instance_payload(row: AwsRdsInstance) -> dict[str, Any]:
    return {
        "id": row.id,
        "cloud_account_id": row.cloud_account_id,
        "account_id": row.account_id,
        "region": row.region,
        "db_instance_identifier": row.db_instance_identifier,
        "db_instance_arn": row.db_instance_arn,
        "db_instance_class": row.db_instance_class,
        "class_prefix": row.class_prefix,
        "instance_family": row.instance_family,
        "instance_size": row.instance_size,
        "engine": row.engine,
        "engine_normalized": row.engine_normalized,
        "engine_version": row.engine_version,
        "license_model": row.license_model,
        "status": row.status,
        "coverage_eligible": row.coverage_eligible,
        "multi_az": row.multi_az,
        "deployment_topology": row.deployment_topology,
        "cluster_storage_type": row.cluster_storage_type,
        "availability_zone": row.availability_zone,
        "secondary_availability_zone": row.secondary_availability_zone,
        "storage_type": row.storage_type,
        "allocated_storage": row.allocated_storage,
        "iops": row.iops,
        "storage_throughput": row.storage_throughput,
        "publicly_accessible": row.publicly_accessible,
        "cluster_identifier": row.cluster_identifier,
        "vpc_id": row.vpc_id,
        "tags": row.tags,
        "processor_features": row.processor_features,
        "option_group_memberships": row.option_group_memberships,
        "parameter_groups": row.parameter_groups,
        "aws_created_at": row.aws_created_at,
        "collected_at": row.collected_at,
        "last_seen_at": row.last_seen_at,
        "is_active": row.is_active,
    }


def _reservation_payload(row: AwsRdsReservedInstance) -> dict[str, Any]:
    return {
        "id": row.id,
        "cloud_account_id": row.cloud_account_id,
        "account_id": row.account_id,
        "region": row.region,
        "reserved_db_instance_id": row.reserved_db_instance_id,
        "offering_id": row.offering_id,
        "db_instance_class": row.db_instance_class,
        "class_prefix": row.class_prefix,
        "instance_family": row.instance_family,
        "instance_size": row.instance_size,
        "product_description": row.product_description,
        "engine_normalized": row.engine_normalized,
        "instance_count": row.instance_count,
        "multi_az": row.multi_az,
        "offering_type": row.offering_type,
        "offering_class": row.offering_class,
        "currency_code": row.currency_code,
        "fixed_price": row.fixed_price,
        "usage_price": row.usage_price,
        "recurring_charges": row.recurring_charges,
        "state": row.state,
        "lease_id": row.lease_id,
        "start_time": row.start_time,
        "duration_seconds": row.duration_seconds,
        "expiration_at": row.expiration_at,
        "days_until_expiration": days_until_expiration(row.expiration_at),
        "collected_at": row.collected_at,
        "last_seen_at": row.last_seen_at,
        "is_active": row.is_active,
    }


def _run_summary(row: RdsReservationCoverageRun) -> dict[str, Any]:
    return {
        "coverage_run_id": row.id,
        "status": row.status,
        "inventory_snapshot_at": row.inventory_snapshot_at,
        "completed_at": row.completed_at,
        "total_rds": row.instances_analyzed,
        "fully_covered": row.fully_covered,
        "partially_covered": row.partially_covered,
        "uncovered": row.uncovered,
        "unknown": row.unknown,
        "required_units": float(row.required_units),
        "covered_units": float(row.covered_units),
        "uncovered_units": float(row.uncovered_units),
        "coverage_percentage": float(row.calculated_coverage_percentage),
        "active_reservations": row.reservations_analyzed,
        "reserved_units": float(row.reserved_units),
        "allocated_reserved_units": float(row.allocated_reserved_units),
        "unused_reserved_units": float(row.unused_reserved_units),
        "aws_observed_coverage_percentage": (
            None
            if row.aws_observed_coverage_percentage is None
            else float(row.aws_observed_coverage_percentage)
        ),
        "billing_validation_status": row.billing_validation_status,
        "reconciliation_status": row.reconciliation_status,
        "reconciliation_detail": row.reconciliation_detail,
    }


def _latest_completed_run(db: Session) -> RdsReservationCoverageRun:
    run = (
        db.query(RdsReservationCoverageRun)
        .filter(RdsReservationCoverageRun.status == "COMPLETED")
        .order_by(RdsReservationCoverageRun.id.desc())
        .first()
    )
    if run is None:
        raise HTTPException(
            status_code=404, detail="No completed RDS reservation coverage run found"
        )
    return run


@router.post("/collect")
def collect_inventory(
    cloud_account_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return collect_rds_inventory(db, cloud_account_id=cloud_account_id)


@router.get("/instances")
def list_instances(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    instance_class: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=64),
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = db.query(AwsRdsInstance)
    if account:
        query = query.filter(AwsRdsInstance.account_id == account)
    if region:
        query = query.filter(AwsRdsInstance.region == region)
    if engine:
        query = query.filter(AwsRdsInstance.engine_normalized == normalize_rds_engine(engine))
    if instance_class:
        query = query.filter(AwsRdsInstance.db_instance_class == instance_class)
    if status:
        query = query.filter(AwsRdsInstance.status == status)
    if active_only:
        query = query.filter(AwsRdsInstance.is_active.is_(True))

    total = query.count()
    rows = (
        query.order_by(
            AwsRdsInstance.account_id,
            AwsRdsInstance.region,
            AwsRdsInstance.db_instance_identifier,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_instance_payload(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/reservations")
def list_reservations(
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    instance_class: str | None = Query(default=None, max_length=64),
    state: str | None = Query(default=None, max_length=64),
    expiration_before: datetime | None = Query(default=None),
    expiration_after: datetime | None = Query(default=None),
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = db.query(AwsRdsReservedInstance)
    if account:
        query = query.filter(AwsRdsReservedInstance.account_id == account)
    if region:
        query = query.filter(AwsRdsReservedInstance.region == region)
    if engine:
        query = query.filter(
            AwsRdsReservedInstance.engine_normalized == normalize_rds_engine(engine)
        )
    if instance_class:
        query = query.filter(AwsRdsReservedInstance.db_instance_class == instance_class)
    if state:
        query = query.filter(AwsRdsReservedInstance.state == state)
    if expiration_before:
        query = query.filter(AwsRdsReservedInstance.expiration_at <= expiration_before)
    if expiration_after:
        query = query.filter(AwsRdsReservedInstance.expiration_at >= expiration_after)
    if active_only:
        query = query.filter(AwsRdsReservedInstance.is_active.is_(True))

    total = query.count()
    rows = (
        query.order_by(
            AwsRdsReservedInstance.expiration_at,
            AwsRdsReservedInstance.account_id,
            AwsRdsReservedInstance.region,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_reservation_payload(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("/reservation-coverage/run")
def calculate_reservation_coverage(
    validate_billing: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = run_rds_reservation_coverage(db, validate_billing=validate_billing)
    return _run_summary(run)


@router.get("/reservation-coverage")
def get_reservation_coverage(
    run_id: int | None = Query(default=None, ge=1),
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    coverage_status: str | None = Query(default=None, max_length=24),
    coverage_scope: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.get(RdsReservationCoverageRun, run_id) if run_id else _latest_completed_run(db)
    if run is None:
        raise HTTPException(status_code=404, detail="RDS reservation coverage run not found")

    query = (
        db.query(RdsInstanceReservationCoverage, AwsRdsInstance)
        .join(AwsRdsInstance, AwsRdsInstance.id == RdsInstanceReservationCoverage.rds_instance_id)
        .filter(RdsInstanceReservationCoverage.coverage_run_id == run.id)
    )
    if account:
        query = query.filter(RdsInstanceReservationCoverage.account_id == account)
    if region:
        query = query.filter(RdsInstanceReservationCoverage.region == region)
    if engine:
        query = query.filter(AwsRdsInstance.engine_normalized == normalize_rds_engine(engine))
    if family:
        query = query.filter(AwsRdsInstance.instance_family == family)
    if coverage_status:
        query = query.filter(
            RdsInstanceReservationCoverage.coverage_status == coverage_status.upper()
        )
    if coverage_scope:
        query = query.filter(
            RdsInstanceReservationCoverage.coverage_scope == coverage_scope.upper()
        )

    total = query.count()
    rows = (
        query.order_by(
            RdsInstanceReservationCoverage.account_id,
            RdsInstanceReservationCoverage.region,
            AwsRdsInstance.db_instance_identifier,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    instance_ids = [coverage.rds_instance_id for coverage, _ in rows]
    allocations = (
        db.query(RdsReservationAllocation, AwsRdsReservedInstance)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationAllocation.reservation_id,
        )
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
    for allocation, reservation in allocations:
        by_instance.setdefault(allocation.rds_instance_id, []).append(
            {
                "reservation_id": reservation.reserved_db_instance_id,
                "reservation_db_id": reservation.id,
                "allocated_units": float(allocation.allocated_units),
                "allocation_percentage": float(allocation.allocation_percentage),
                "match_type": allocation.match_type,
                "allocation_scope": allocation.allocation_scope,
                "reason": allocation.reason,
            }
        )

    items = []
    for coverage, instance in rows:
        items.append(
            {
                "instance": instance.db_instance_identifier,
                "instance_id": instance.id,
                "engine": instance.engine_normalized,
                "instance_class": instance.db_instance_class,
                "family": instance.instance_family,
                "region": instance.region,
                "account": instance.account_id,
                "required_units": float(coverage.required_units),
                "covered_units": float(coverage.covered_units),
                "uncovered_units": float(coverage.uncovered_units),
                "coverage_percentage": float(coverage.coverage_percentage),
                "coverage_status": coverage.coverage_status,
                "coverage_scope": coverage.coverage_scope,
                "calculation_method": coverage.calculation_method,
                "allocations": by_instance.get(instance.id, []),
                "explanation": coverage.explanation,
            }
        )
    return {
        "summary": _run_summary(run),
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/reservation-utilization")
def get_reservation_utilization(
    run_id: int | None = Query(default=None, ge=1),
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.get(RdsReservationCoverageRun, run_id) if run_id else _latest_completed_run(db)
    if run is None:
        raise HTTPException(status_code=404, detail="RDS reservation coverage run not found")

    query = (
        db.query(RdsReservationUtilization, AwsRdsReservedInstance)
        .join(
            AwsRdsReservedInstance,
            AwsRdsReservedInstance.id == RdsReservationUtilization.reservation_id,
        )
        .filter(RdsReservationUtilization.coverage_run_id == run.id)
    )
    if account:
        query = query.filter(AwsRdsReservedInstance.account_id == account)
    if region:
        query = query.filter(AwsRdsReservedInstance.region == region)
    if engine:
        query = query.filter(
            AwsRdsReservedInstance.engine_normalized == normalize_rds_engine(engine)
        )

    total = query.count()
    rows = (
        query.order_by(
            AwsRdsReservedInstance.account_id,
            AwsRdsReservedInstance.region,
            AwsRdsReservedInstance.reserved_db_instance_id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "coverage_run_id": run.id,
        "items": [
            {
                "reservation": reservation.reserved_db_instance_id,
                "reservation_id": reservation.id,
                "account": reservation.account_id,
                "region": reservation.region,
                "engine": reservation.engine_normalized,
                "instance_class": reservation.db_instance_class,
                "total_capacity": float(utilization.total_units),
                "allocated_capacity": float(utilization.allocated_units),
                "unused_capacity": float(utilization.unused_units),
                "utilization_percentage": float(utilization.utilization_percentage),
                "expiration_at": reservation.expiration_at,
            }
            for utilization, reservation in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
