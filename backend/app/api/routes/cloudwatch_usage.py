from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.schemas.cloudwatch_usage import CloudWatchUsagePage, CloudWatchUsageSummary
from app.services.cloudwatch_usage_query import (
    CloudWatchUsageFilters,
    list_usage_events,
    usage_summary,
)

router = APIRouter(
    prefix="/usage/cloudwatch",
    tags=["cloudwatch-usage"],
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
    success: bool | None,
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
        success=success,
    )


@router.get("", response_model=CloudWatchUsagePage)
def cloudwatch_usage_events(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cloud_account_id: int | None = None,
    aws_account_id: str | None = Query(default=None, min_length=12, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    operation: str | None = Query(default=None, max_length=64),
    collector: str | None = Query(default=None, max_length=80),
    analyzer: str | None = Query(default=None, max_length=80),
    collection_run_id: str | None = Query(default=None, max_length=36),
    success: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return list_usage_events(
        db,
        _filters(
            date_from=date_from,
            date_to=date_to,
            cloud_account_id=cloud_account_id,
            aws_account_id=aws_account_id,
            region=region,
            operation=operation,
            collector=collector,
            analyzer=analyzer,
            collection_run_id=collection_run_id,
            success=success,
        ),
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=CloudWatchUsageSummary)
def cloudwatch_usage_summary(
    group_by: Literal[
        "operation", "account", "region", "collector", "analyzer"
    ] = "operation",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cloud_account_id: int | None = None,
    aws_account_id: str | None = Query(default=None, min_length=12, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    operation: str | None = Query(default=None, max_length=64),
    collector: str | None = Query(default=None, max_length=80),
    analyzer: str | None = Query(default=None, max_length=80),
    collection_run_id: str | None = Query(default=None, max_length=36),
    success: bool | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return usage_summary(
        db,
        _filters(
            date_from=date_from,
            date_to=date_to,
            cloud_account_id=cloud_account_id,
            aws_account_id=aws_account_id,
            region=region,
            operation=operation,
            collector=collector,
            analyzer=analyzer,
            collection_run_id=collection_run_id,
            success=success,
        ),
        group_by=group_by,
    )
