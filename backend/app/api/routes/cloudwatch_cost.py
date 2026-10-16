from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.schemas.cloudwatch_cost import CloudWatchCostResponse
from app.services.cloudwatch_cost_engine import CloudWatchCostEngine
from app.services.cloudwatch_usage_query import CloudWatchUsageFilters

router = APIRouter(
    prefix="/deepops-costs/cloudwatch",
    tags=["cloudwatch-costs"],
    dependencies=[Depends(require_admin)],
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _filters(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    cloud_account_id: int | None,
    aws_account_id: str | None,
    region: str | None,
    operation: str | None,
    collector: str | None,
    analyzer: str | None,
    collection_run_id: str | None,
) -> CloudWatchUsageFilters:
    if date_from and date_to and _utc(date_from) >= _utc(date_to):
        raise HTTPException(status_code=422, detail="date_from must precede date_to")
    return CloudWatchUsageFilters(
        date_from=date_from,
        date_to=date_to,
        cloud_account_id=cloud_account_id,
        aws_account_id=aws_account_id,
        region=region,
        operation=operation,
        collector=collector,
        analyzer=analyzer,
        collection_run_id=collection_run_id,
    )


def _common_filters(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cloud_account_id: int | None = None,
    aws_account_id: str | None = Query(default=None, min_length=12, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    operation: str | None = Query(default=None, max_length=64),
    collector: str | None = Query(default=None, max_length=80),
    analyzer: str | None = Query(default=None, max_length=80),
    collection_run_id: str | None = Query(default=None, max_length=36),
) -> CloudWatchUsageFilters:
    return _filters(
        date_from=date_from,
        date_to=date_to,
        cloud_account_id=cloud_account_id,
        aws_account_id=aws_account_id,
        region=region,
        operation=operation,
        collector=collector,
        analyzer=analyzer,
        collection_run_id=collection_run_id,
    )


@router.get("/summary", response_model=CloudWatchCostResponse)
def cloudwatch_cost_summary(
    filters: CloudWatchUsageFilters = Depends(_common_filters),
    db: Session = Depends(get_db),
) -> dict:
    return CloudWatchCostEngine(db).calculate(filters)


@router.get("/timeseries", response_model=CloudWatchCostResponse)
def cloudwatch_cost_timeseries(
    granularity: Literal["daily", "monthly"] = "daily",
    filters: CloudWatchUsageFilters = Depends(_common_filters),
    db: Session = Depends(get_db),
) -> dict:
    return CloudWatchCostEngine(db).calculate(filters, granularity=granularity)


@router.get("/breakdown", response_model=CloudWatchCostResponse)
def cloudwatch_cost_breakdown(
    group_by: Literal[
        "account",
        "region",
        "operation",
        "collector",
        "analyzer",
        "collection_run",
    ] = "operation",
    filters: CloudWatchUsageFilters = Depends(_common_filters),
    db: Session = Depends(get_db),
) -> dict:
    return CloudWatchCostEngine(db).calculate(filters, group_by=group_by)
