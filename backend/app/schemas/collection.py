from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.collection_errors import sanitize_collection_error

CollectionSort = Literal["started_at", "opportunities_found"]


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str | None
    provider: str
    account_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    resources_analyzed: int
    opportunities_found: int
    analyzer_version: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("error_detail", mode="before")
    @classmethod
    def safe_error(cls, value):
        return sanitize_collection_error(value)

    @field_validator("started_at", "finished_at", "created_at", "updated_at")
    @classmethod
    def utc_dates(cls, value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class CollectionItem(CollectionRunRead):
    account_name: str | None = None
    duration_seconds: float | None = None
    resources_analyzed_available: bool = False
    has_warnings: bool = False


class CollectionAccountSummary(BaseModel):
    latest_run: CollectionItem | None
    latest_success: CollectionItem | None


class CollectionPage(BaseModel):
    items: list[CollectionItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    account_summary: CollectionAccountSummary | None = None


class CollectionDetail(CollectionItem):
    opportunities_observed: int
    warning_detail: str | None = None
    trigger: str | None = None


class CollectionAccountOption(BaseModel):
    provider: str
    account_id: str
    account_name: str | None


class CollectionOptions(BaseModel):
    providers: list[str]
    accounts: list[CollectionAccountOption]
    has_more_accounts: bool


ComparisonCategory = Literal["NEW", "PERSISTENT", "NO_LONGER_DETECTED", "CHANGED"]


class CollectionComparisonRun(BaseModel):
    id: str
    provider: str
    account_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    rules_version: str | None


class CollectionComparisonWarning(BaseModel):
    code: str
    message: str


class CollectionComparisonSummary(BaseModel):
    baseline_total: int
    target_total: int
    new: int
    persistent: int
    no_longer_detected: int
    changed: int


class CollectionComparisonFinancialSummary(BaseModel):
    metric: Literal["estimated_monthly_savings"]
    label: str
    currency: Literal["USD"]
    period: Literal["month"]
    baseline_total: Decimal
    target_total: Decimal
    delta: Decimal
    delta_percent: Decimal | None


class CollectionComparisonObservation(BaseModel):
    observed_at: datetime
    severity: str
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    confidence: str
    evidence_summary: str | None


class CollectionComparisonChange(BaseModel):
    type: str
    label: str
    baseline: Any = None
    target: Any = None
    unit: str | None = None


class CollectionComparisonItem(BaseModel):
    category: ComparisonCategory
    opportunity_id: str
    fingerprint: str
    title: str
    rule_key: str
    service: str
    region: str
    resource_id: str
    resource_name: str | None
    lifecycle_status: str
    first_seen_at: datetime
    baseline: CollectionComparisonObservation | None
    target: CollectionComparisonObservation | None
    change_types: list[str] = Field(default_factory=list)
    changes: list[CollectionComparisonChange] = Field(default_factory=list)


class CollectionComparisonResponse(BaseModel):
    available: bool
    reason: str | None = None
    message: str | None = None
    baseline: CollectionComparisonRun | None
    target: CollectionComparisonRun
    summary: CollectionComparisonSummary | None
    financial_summary: CollectionComparisonFinancialSummary | None
    rules_version_warning: CollectionComparisonWarning | None
    warnings: list[CollectionComparisonWarning] = Field(default_factory=list)
    category: ComparisonCategory
    items: list[CollectionComparisonItem] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    total_pages: int
