from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.rds_inventory import AwsRdsInstance, AwsRdsReservedInstance

FRESH = "FRESH"
STALE = "STALE"
UNKNOWN = "UNKNOWN"


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def classify_rds_inventory_freshness(
    inventory_snapshot_at: datetime | None,
    *,
    now: datetime | None = None,
) -> str:
    if inventory_snapshot_at is None:
        return UNKNOWN
    current = normalize_utc(now or utcnow())
    threshold = timedelta(hours=settings.rds_reservation_inventory_freshness_hours)
    return FRESH if normalize_utc(inventory_snapshot_at) >= current - threshold else STALE


def is_rds_inventory_fresh(
    inventory_snapshot_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    return classify_rds_inventory_freshness(inventory_snapshot_at, now=now) == FRESH


def effective_rds_inventory_snapshot_at(
    db: Session,
    *,
    fallback: datetime | None = None,
) -> datetime | None:
    """Return the conservative timestamp of the active inventory used by coverage.

    Coverage reads all active RDS instances and reservations. The effective snapshot
    is therefore the oldest collected_at among those active rows, not the coverage
    calculation time. An empty-but-successfully-collected inventory may use the
    caller-provided collection completion timestamp as its snapshot marker.
    """

    candidates: list[datetime] = []
    for model in (AwsRdsInstance, AwsRdsReservedInstance):
        collected_at = (
            db.query(func.min(model.collected_at))
            .filter(model.is_active.is_(True))
            .scalar()
        )
        if collected_at is not None:
            candidates.append(normalize_utc(collected_at))
    if candidates:
        return min(candidates)
    return normalize_utc(fallback) if fallback is not None else None
