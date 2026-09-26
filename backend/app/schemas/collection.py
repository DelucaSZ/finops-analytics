from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ComparisonCategory = Literal["NEW", "PERSISTENT", "NO_LONGER_DETECTED", "CHANGED"]


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
