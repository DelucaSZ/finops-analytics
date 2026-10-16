from datetime import datetime

from pydantic import BaseModel, Field


class CloudWatchUsageEventRead(BaseModel):
    id: str
    occurred_at: datetime
    provider: str
    aws_service: str
    cloud_account_id: int | None
    aws_account_id: str
    region: str
    operation: str
    collector: str | None
    analyzer: str | None
    collection_run_id: str | None
    request_count: int
    retry_count: int | None
    request_count_is_exact: bool
    metrics_requested: int | None
    metric_query_count: int | None
    metric_stat_query_count: int | None
    expression_query_count: int | None
    metrics_insights_query_count: int | None
    success: bool
    error_type: str | None
    request_duration_ms: int | None
    aws_request_id: str | None
    metadata: dict = Field(default_factory=dict)


class CloudWatchUsagePage(BaseModel):
    items: list[CloudWatchUsageEventRead]
    page: int
    page_size: int
    total: int


class CloudWatchUsageSummaryItem(BaseModel):
    group: str | None
    events: int
    requests: int
    metric_queries: int
    metrics_requested: int
    failed_events: int


class CloudWatchUsageSummary(BaseModel):
    group_by: str
    items: list[CloudWatchUsageSummaryItem]
