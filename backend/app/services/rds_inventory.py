from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider
from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance
from app.services.aws_auth import BOTO_CONFIG, assume_account_session

logger = logging.getLogger(__name__)

RDS_COVERAGE_ELIGIBLE_STATUSES = frozenset(
    {
        "available",
        "backing-up",
        "configuring-enhanced-monitoring",
        "configuring-iam-database-auth",
        "configuring-log-exports",
        "converting-to-vpc",
        "maintenance",
        "modifying",
        "moving-to-vpc",
        "rebooting",
        "renaming",
        "resetting-master-credentials",
        "starting",
        "stopped",
        "stopping",
        "storage-full",
        "storage-optimization",
        "upgrading",
    }
)

_ENGINE_ALIASES = {
    "aurora": "aurora-mysql",
    "aurora mysql": "aurora-mysql",
    "aurora-mysql": "aurora-mysql",
    "aurora postgresql": "aurora-postgresql",
    "aurora-postgresql": "aurora-postgresql",
    "db2-ae": "db2-ae",
    "db2-se": "db2-se",
    "mariadb": "mariadb",
    "mysql": "mysql",
    "oracle-ee": "oracle-ee",
    "oracle-ee-cdb": "oracle-ee-cdb",
    "oracle-se": "oracle-se",
    "oracle-se1": "oracle-se1",
    "oracle-se2": "oracle-se2",
    "oracle-se2-cdb": "oracle-se2-cdb",
    "postgres": "postgres",
    "postgresql": "postgres",
    "sqlserver-ee": "sqlserver-ee",
    "sqlserver-ex": "sqlserver-ex",
    "sqlserver-se": "sqlserver-se",
    "sqlserver-web": "sqlserver-web",
}
_LICENSE_SUFFIXES = {
    "bring your own license",
    "bring-your-own-license",
    "byol",
    "li",
    "license included",
    "license-included",
}


@dataclass(frozen=True)
class DbInstanceClassParts:
    prefix: str | None
    family: str | None
    size: str | None
    full_class: str


def parse_db_instance_class(value: str | None) -> DbInstanceClassParts:
    full_class = (value or "").strip()
    parts = full_class.split(".", 2)
    if len(parts) != 3:
        return DbInstanceClassParts(None, None, None, full_class)
    return DbInstanceClassParts(parts[0] or None, parts[1] or None, parts[2] or None, full_class)


def normalize_rds_engine(value: str | None) -> str:
    raw = " ".join((value or "").strip().lower().split())
    if not raw:
        return ""
    if raw.endswith(")") and "(" in raw:
        base, suffix = raw.rsplit("(", 1)
        suffix = suffix[:-1].strip()
        if suffix in _LICENSE_SUFFIXES:
            raw = base.strip()
    return _ENGINE_ALIASES.get(raw, raw)


def is_rds_coverage_eligible(status: str | None) -> bool:
    return (status or "").strip().lower() in RDS_COVERAGE_ELIGIBLE_STATUSES


def reservation_expiration(start_time: datetime, duration_seconds: int) -> datetime:
    return start_time + timedelta(seconds=int(duration_seconds))


def days_until_expiration(expiration_at: datetime, *, now: datetime | None = None) -> float:
    current = now or datetime.now(UTC)
    if expiration_at.tzinfo is None:
        expiration_at = expiration_at.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return (expiration_at - current).total_seconds() / 86400


def _monetary_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _tags_by_key(items: list[dict[str, Any]] | None) -> dict[str, str]:
    return {
        str(item["Key"]): str(item.get("Value", ""))
        for item in (items or [])
        if item.get("Key") is not None
    }


def _client_error_code(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code") or exc.__class__.__name__)
    return exc.__class__.__name__


def _list_tags(client: Any, arn: str) -> dict[str, str]:
    try:
        response = client.list_tags_for_resource(ResourceName=arn)
    except (ClientError, BotoCoreError) as exc:
        logger.warning(
            "RDS tag collection failed arn=%s error=%s",
            arn,
            _client_error_code(exc),
        )
        return {}
    return _tags_by_key(response.get("TagList"))


def collect_db_instances(client: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paginator = client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for item in page.get("DBInstances", []):
            copied = dict(item)
            arn = copied.get("DBInstanceArn")
            copied["_DeepOpsTags"] = _list_tags(client, str(arn)) if arn else {}
            items.append(copied)
    return items


def collect_reserved_db_instances(client: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paginator = client.get_paginator("describe_reserved_db_instances")
    for page in paginator.paginate():
        items.extend(dict(item) for item in page.get("ReservedDBInstances", []))
    return items


def _instance_values(
    *,
    cloud_account_id: int,
    account_id: str,
    region: str,
    item: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    instance_class = str(item.get("DBInstanceClass") or "")
    parts = parse_db_instance_class(instance_class)
    subnet_group = item.get("DBSubnetGroup") or {}
    engine = str(item.get("Engine") or "")
    status = str(item.get("DBInstanceStatus") or "")
    return {
        "cloud_account_id": cloud_account_id,
        "account_id": account_id,
        "region": region,
        "db_instance_identifier": str(item.get("DBInstanceIdentifier") or ""),
        "db_instance_arn": str(item.get("DBInstanceArn") or ""),
        "db_instance_class": instance_class,
        "class_prefix": parts.prefix,
        "instance_family": parts.family,
        "instance_size": parts.size,
        "engine": engine,
        "engine_normalized": normalize_rds_engine(engine),
        "engine_version": item.get("EngineVersion"),
        "license_model": item.get("LicenseModel"),
        "status": status,
        "coverage_eligible": is_rds_coverage_eligible(status),
        "multi_az": bool(item.get("MultiAZ", False)),
        "availability_zone": item.get("AvailabilityZone"),
        "secondary_availability_zone": item.get("SecondaryAvailabilityZone"),
        "storage_type": item.get("StorageType"),
        "allocated_storage": item.get("AllocatedStorage"),
        "iops": item.get("Iops"),
        "storage_throughput": item.get("StorageThroughput"),
        "publicly_accessible": item.get("PubliclyAccessible"),
        "cluster_identifier": item.get("DBClusterIdentifier"),
        "vpc_id": subnet_group.get("VpcId"),
        "tags": item.get("_DeepOpsTags") or {},
        "processor_features": item.get("ProcessorFeatures") or [],
        "option_group_memberships": item.get("OptionGroupMemberships") or [],
        "parameter_groups": item.get("DBParameterGroups") or [],
        "aws_created_at": item.get("InstanceCreateTime"),
        "collected_at": observed_at,
        "last_seen_at": observed_at,
        "is_active": True,
    }


def _reservation_values(
    *,
    cloud_account_id: int,
    account_id: str,
    region: str,
    item: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    instance_class = str(item.get("DBInstanceClass") or "")
    parts = parse_db_instance_class(instance_class)
    product_description = str(item.get("ProductDescription") or "")
    start_time = item.get("StartTime")
    duration_seconds = int(item.get("Duration") or 0)
    if not isinstance(start_time, datetime):
        raise ValueError("Reserved DB Instance is missing StartTime")
    return {
        "cloud_account_id": cloud_account_id,
        "account_id": account_id,
        "region": region,
        "reserved_db_instance_id": str(item.get("ReservedDBInstanceId") or ""),
        "offering_id": item.get("ReservedDBInstancesOfferingId"),
        "db_instance_class": instance_class,
        "class_prefix": parts.prefix,
        "instance_family": parts.family,
        "instance_size": parts.size,
        "product_description": product_description,
        "engine_normalized": normalize_rds_engine(product_description),
        "instance_count": int(item.get("DBInstanceCount") or 0),
        "multi_az": bool(item.get("MultiAZ", False)),
        "offering_type": item.get("OfferingType"),
        "offering_class": item.get("OfferingClass"),
        "currency_code": item.get("CurrencyCode"),
        "fixed_price": _monetary_text(item.get("FixedPrice")),
        "usage_price": _monetary_text(item.get("UsagePrice")),
        "recurring_charges": item.get("RecurringCharges") or [],
        "state": str(item.get("State") or ""),
        "lease_id": item.get("LeaseId"),
        "start_time": start_time,
        "duration_seconds": duration_seconds,
        "expiration_at": reservation_expiration(start_time, duration_seconds),
        "collected_at": observed_at,
        "last_seen_at": observed_at,
        "is_active": True,
    }


def _assign(row: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(row, key, value)


def reconcile_db_instances(
    db: Session,
    *,
    cloud_account_id: int,
    account_id: str,
    region: str,
    items: list[dict[str, Any]],
    observed_at: datetime | None = None,
) -> dict[str, int]:
    observed_at = observed_at or utcnow()
    existing_rows = (
        db.query(AwsRdsInstance)
        .filter(
            AwsRdsInstance.cloud_account_id == cloud_account_id,
            AwsRdsInstance.region == region,
        )
        .all()
    )
    existing = {row.db_instance_arn: row for row in existing_rows}
    seen: set[str] = set()
    created = 0
    updated = 0

    for item in items:
        arn = str(item.get("DBInstanceArn") or "")
        if not arn:
            logger.warning(
                "Skipping RDS DB Instance without ARN account=%s region=%s identifier=%s",
                account_id,
                region,
                item.get("DBInstanceIdentifier"),
            )
            continue
        values = _instance_values(
            cloud_account_id=cloud_account_id,
            account_id=account_id,
            region=region,
            item=item,
            observed_at=observed_at,
        )
        row = existing.get(arn)
        if row is None:
            row = AwsRdsInstance(**values)
            db.add(row)
            created += 1
        else:
            _assign(row, values)
            updated += 1
        seen.add(arn)

    marked_inactive = 0
    for row in existing_rows:
        if row.db_instance_arn not in seen and row.is_active:
            row.is_active = False
            row.collected_at = observed_at
            marked_inactive += 1
    return {
        "found": len(seen),
        "created": created,
        "updated": updated,
        "marked_inactive": marked_inactive,
    }


def reconcile_reserved_db_instances(
    db: Session,
    *,
    cloud_account_id: int,
    account_id: str,
    region: str,
    items: list[dict[str, Any]],
    observed_at: datetime | None = None,
) -> dict[str, int]:
    observed_at = observed_at or utcnow()
    existing_rows = (
        db.query(AwsRdsReservedInstance)
        .filter(
            AwsRdsReservedInstance.cloud_account_id == cloud_account_id,
            AwsRdsReservedInstance.region == region,
        )
        .all()
    )
    existing = {row.reserved_db_instance_id: row for row in existing_rows}
    seen: set[str] = set()
    created = 0
    updated = 0

    skipped = 0
    for item in items:
        reservation_id = str(item.get("ReservedDBInstanceId") or "")
        if not reservation_id:
            logger.warning(
                "Skipping Reserved DB Instance without id account=%s region=%s",
                account_id,
                region,
            )
            skipped += 1
            continue
        seen.add(reservation_id)
        try:
            values = _reservation_values(
                cloud_account_id=cloud_account_id,
                account_id=account_id,
                region=region,
                item=item,
                observed_at=observed_at,
            )
        except ValueError:
            logger.warning(
                "Skipping incomplete Reserved DB Instance account=%s region=%s id=%s",
                account_id,
                region,
                reservation_id,
            )
            skipped += 1
            row = existing.get(reservation_id)
            if row is not None:
                row.last_seen_at = observed_at
                row.collected_at = observed_at
                row.is_active = True
            continue
        row = existing.get(reservation_id)
        if row is None:
            row = AwsRdsReservedInstance(**values)
            db.add(row)
            created += 1
        else:
            _assign(row, values)
            updated += 1

    marked_inactive = 0
    for row in existing_rows:
        if row.reserved_db_instance_id not in seen and row.is_active:
            row.is_active = False
            row.collected_at = observed_at
            marked_inactive += 1
    return {
        "found": len(seen),
        "created": created,
        "updated": updated,
        "marked_inactive": marked_inactive,
        "skipped": skipped,
    }


def collect_rds_inventory(
    db: Session,
    *,
    cloud_account_id: int | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    query = db.query(CloudAccount).filter(
        CloudAccount.provider == CloudProvider.AWS.value,
        CloudAccount.enabled.is_(True),
    )
    if cloud_account_id is not None:
        query = query.filter(CloudAccount.id == cloud_account_id)
    accounts = query.order_by(CloudAccount.id).all()

    result: dict[str, Any] = {
        "accounts_processed": 0,
        "regions_processed": 0,
        "rds_instances_found": 0,
        "reservations_found": 0,
        "errors": [],
        "scopes": [],
    }
    logger.info(
        "Starting RDS inventory collection accounts=%s cloud_account_id=%s",
        len(accounts),
        cloud_account_id,
    )

    for cloud_account in accounts:
        aws_account = cloud_account.aws_configuration
        if aws_account is None:
            result["errors"].append(
                {
                    "cloud_account_id": cloud_account.id,
                    "account_id": cloud_account.native_account_id,
                    "region": None,
                    "operation": "configuration",
                    "error": "missing_aws_configuration",
                }
            )
            continue

        try:
            session = assume_account_session(aws_account)
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "RDS inventory assume-role failed account=%s error=%s",
                aws_account.aws_account_id,
                _client_error_code(exc),
            )
            result["errors"].append(
                {
                    "cloud_account_id": cloud_account.id,
                    "account_id": aws_account.aws_account_id,
                    "region": None,
                    "operation": "assume_role",
                    "error": _client_error_code(exc),
                }
            )
            continue

        result["accounts_processed"] += 1
        regions = list(dict.fromkeys(aws_account.regions or []))
        for region in regions:
            result["regions_processed"] += 1
            scope_started = time.monotonic()
            scope: dict[str, Any] = {
                "cloud_account_id": cloud_account.id,
                "account_id": aws_account.aws_account_id,
                "region": region,
            }
            client = session.client("rds", region_name=region, config=BOTO_CONFIG)

            try:
                instances = collect_db_instances(client)
                instance_counts = reconcile_db_instances(
                    db,
                    cloud_account_id=cloud_account.id,
                    account_id=aws_account.aws_account_id,
                    region=region,
                    items=instances,
                )
                db.commit()
                scope["instances"] = instance_counts
                result["rds_instances_found"] += instance_counts["found"]
            except (ClientError, BotoCoreError, ValueError) as exc:
                db.rollback()
                code = _client_error_code(exc)
                logger.warning(
                    "RDS DB Instance collection failed account=%s region=%s error=%s",
                    aws_account.aws_account_id,
                    region,
                    code,
                )
                scope["instances_error"] = code
                result["errors"].append(
                    {
                        "cloud_account_id": cloud_account.id,
                        "account_id": aws_account.aws_account_id,
                        "region": region,
                        "operation": "DescribeDBInstances",
                        "error": code,
                    }
                )

            try:
                reservations = collect_reserved_db_instances(client)
                reservation_counts = reconcile_reserved_db_instances(
                    db,
                    cloud_account_id=cloud_account.id,
                    account_id=aws_account.aws_account_id,
                    region=region,
                    items=reservations,
                )
                db.commit()
                scope["reservations"] = reservation_counts
                result["reservations_found"] += reservation_counts["found"]
            except (ClientError, BotoCoreError, ValueError) as exc:
                db.rollback()
                code = _client_error_code(exc)
                logger.warning(
                    "RDS reservation collection failed account=%s region=%s error=%s",
                    aws_account.aws_account_id,
                    region,
                    code,
                )
                scope["reservations_error"] = code
                result["errors"].append(
                    {
                        "cloud_account_id": cloud_account.id,
                        "account_id": aws_account.aws_account_id,
                        "region": region,
                        "operation": "DescribeReservedDBInstances",
                        "error": code,
                    }
                )

            scope["duration_ms"] = round((time.monotonic() - scope_started) * 1000)
            result["scopes"].append(scope)
            logger.info(
                "RDS inventory scope completed account=%s region=%s instances=%s "
                "reservations=%s duration_ms=%s",
                aws_account.aws_account_id,
                region,
                scope.get("instances", {}).get("found"),
                scope.get("reservations", {}).get("found"),
                scope["duration_ms"],
            )

    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    logger.info(
        "RDS inventory collection completed accounts=%s regions=%s instances=%s "
        "reservations=%s errors=%s duration_ms=%s",
        result["accounts_processed"],
        result["regions_processed"],
        result["rds_instances_found"],
        result["reservations_found"],
        len(result["errors"]),
        result["duration_ms"],
    )
    return result
