from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models.cloudwatch_usage import CloudWatchUsageEvent

CloudWatchUsageGroup = Literal[
    "operation",
    "account",
    "region",
    "collector",
    "analyzer",
    "collection_run",
]


@dataclass(frozen=True)
class CloudWatchUsageFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    cloud_account_id: int | None = None
    aws_account_id: str | None = None
    region: str | None = None
    operation: str | None = None
    collector: str | None = None
    analyzer: str | None = None
    collection_run_id: str | None = None
    success: bool | None = None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _filtered(statement: Select, filters: CloudWatchUsageFilters) -> Select:
    if filters.date_from is not None:
        statement = statement.where(CloudWatchUsageEvent.occurred_at >= _utc(filters.date_from))
    if filters.date_to is not None:
        statement = statement.where(CloudWatchUsageEvent.occurred_at < _utc(filters.date_to))
    if filters.cloud_account_id is not None:
        statement = statement.where(
            CloudWatchUsageEvent.cloud_account_id == filters.cloud_account_id
        )
    if filters.aws_account_id is not None:
        statement = statement.where(CloudWatchUsageEvent.aws_account_id == filters.aws_account_id)
    if filters.region is not None:
        statement = statement.where(CloudWatchUsageEvent.region == filters.region)
    if filters.operation is not None:
        statement = statement.where(CloudWatchUsageEvent.operation == filters.operation)
    if filters.collector is not None:
        statement = statement.where(CloudWatchUsageEvent.collector == filters.collector)
    if filters.analyzer is not None:
        statement = statement.where(CloudWatchUsageEvent.analyzer == filters.analyzer)
    if filters.collection_run_id is not None:
        statement = statement.where(
            CloudWatchUsageEvent.collection_run_id == filters.collection_run_id
        )
    if filters.success is not None:
        statement = statement.where(CloudWatchUsageEvent.success.is_(filters.success))
    return statement


def list_usage_events(
    db: Session,
    filters: CloudWatchUsageFilters,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    count_statement = _filtered(select(func.count()).select_from(CloudWatchUsageEvent), filters)
    total = int(db.scalar(count_statement) or 0)
    statement = _filtered(select(CloudWatchUsageEvent), filters).order_by(
        CloudWatchUsageEvent.occurred_at.desc(), CloudWatchUsageEvent.id.desc()
    )
    items = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [serialize_usage_event(item) for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def usage_summary(
    db: Session,
    filters: CloudWatchUsageFilters,
    *,
    group_by: CloudWatchUsageGroup = "operation",
) -> dict:
    group_columns = {
        "operation": CloudWatchUsageEvent.operation,
        "account": CloudWatchUsageEvent.aws_account_id,
        "region": CloudWatchUsageEvent.region,
        "collector": CloudWatchUsageEvent.collector,
        "analyzer": CloudWatchUsageEvent.analyzer,
        "collection_run": CloudWatchUsageEvent.collection_run_id,
    }
    group = group_columns[group_by]
    statement = select(
        group.label("group"),
        func.count(CloudWatchUsageEvent.id).label("events"),
        func.coalesce(func.sum(CloudWatchUsageEvent.request_count), 0).label("requests"),
        func.coalesce(func.sum(CloudWatchUsageEvent.metric_query_count), 0).label("metric_queries"),
        func.coalesce(func.sum(CloudWatchUsageEvent.metrics_requested), 0).label(
            "metrics_requested"
        ),
        func.coalesce(
            func.sum(case((CloudWatchUsageEvent.success.is_(False), 1), else_=0)),
            0,
        ).label("failed_events"),
    ).group_by(group)
    rows = db.execute(_filtered(statement, filters).order_by(group)).all()
    return {
        "group_by": group_by,
        "items": [
            {
                "group": row.group,
                "events": int(row.events),
                "requests": int(row.requests),
                "metric_queries": int(row.metric_queries),
                "metrics_requested": int(row.metrics_requested),
                "failed_events": int(row.failed_events),
            }
            for row in rows
        ],
    }


def serialize_usage_event(event: CloudWatchUsageEvent) -> dict:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
        "provider": event.provider,
        "aws_service": event.aws_service,
        "cloud_account_id": event.cloud_account_id,
        "aws_account_id": event.aws_account_id,
        "region": event.region,
        "operation": event.operation,
        "collector": event.collector,
        "analyzer": event.analyzer,
        "collection_run_id": event.collection_run_id,
        "request_count": event.request_count,
        "retry_count": event.retry_count,
        "request_count_is_exact": event.request_count_is_exact,
        "metrics_requested": event.metrics_requested,
        "metric_query_count": event.metric_query_count,
        "metric_stat_query_count": event.metric_stat_query_count,
        "expression_query_count": event.expression_query_count,
        "metrics_insights_query_count": event.metrics_insights_query_count,
        "success": event.success,
        "error_type": event.error_type,
        "request_duration_ms": event.request_duration_ms,
        "aws_request_id": event.aws_request_id,
        "metadata": event.event_metadata,
    }
