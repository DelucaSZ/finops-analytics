from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

CycleStatus = Literal["OPEN", "CLOSED"]
SnapshotSort = Literal[
    "estimated_savings",
    "current_cost",
    "severity",
    "first_observed_in_cycle_at",
    "last_observed_in_cycle_at",
    "status",
    "resource",
    "account",
]
SortOrder = Literal["asc", "desc"]


class MoneyTotal(BaseModel):
    currency: str
    amount: Decimal


class CollectionCoverage(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    running: int = 0


class OpportunityHistoryCycleRead(BaseModel):
    id: str
    label: str
    period_start: datetime
    period_end: datetime
    status: CycleStatus
    timezone: str
    created_at: datetime
    closed_at: datetime | None = None
    closed_by: str | None = None
    close_reason: str | None = None
    snapshot_count: int = 0
    totals: dict[str, Any] = Field(default_factory=dict)
    coverage: CollectionCoverage = Field(default_factory=CollectionCoverage)


class OpportunityHistoryCyclePage(BaseModel):
    items: list[OpportunityHistoryCycleRead]
    total: int


class OpportunityHistorySnapshotRead(BaseModel):
    id: str
    cycle_id: str
    opportunity_id: str | None
    fingerprint: str
    provider: str
    account_id: str
    account_name: str | None
    region: str | None
    service: str
    resource_type: str | None
    resource_id: str
    resource_name: str | None
    rule_key: str
    title: str
    description: str
    status: str
    presence_status: str
    needs_review: bool
    archived: bool
    archive_reason: str | None
    treated_at: datetime | None
    rejected_at: datetime | None
    resolved_externally_at: datetime | None
    treatment_note: str | None
    rejection_reason: str | None
    rejection_note: str | None
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    currency: str
    severity: str
    confidence: str
    first_seen_at: datetime
    last_seen_at: datetime
    first_observed_in_cycle_at: datetime
    last_observed_in_cycle_at: datetime
    occurrence_count_in_cycle: int
    total_occurrence_count: int
    first_collection_run_id_in_cycle: str | None
    last_collection_run_id_in_cycle: str | None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime
    capture_reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpportunityHistorySnapshotPage(BaseModel):
    items: list[OpportunityHistorySnapshotRead]
    total: int
    page: int
    page_size: int
    total_pages: int
