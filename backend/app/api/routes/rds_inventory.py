from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.rds_inventory import (
    collect_rds_inventory,
    days_until_expiration,
    normalize_rds_engine,
)

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
