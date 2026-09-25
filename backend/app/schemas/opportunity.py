from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

OpportunityStatus = Literal["open", "treated", "rejected"]
OpportunitySeverity = Literal["low", "medium", "high"]
SortOrder = Literal["asc", "desc"]
OpportunitySort = Literal[
    "created_at",
    "first_seen_at",
    "last_seen_at",
    "severity",
    "estimated_savings",
    "status",
]
RejectionReason = Literal[
    "FALSE_POSITIVE",
    "OPERATIONAL_EXCEPTION",
    "ACCEPTABLE_COST",
    "RESOURCE_REQUIRED",
    "RISK_ACCEPTED",
    "OTHER",
]


class OpportunityListItem(BaseModel):
    id: str
    fingerprint: str
    provider: str
    account_id: str
    account_name: str
    legacy_account_id: int
    rule_key: str
    service: str
    region: str
    resource_id: str
    resource_name: str | None
    title: str
    description: str
    evidence: dict
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    confidence: str
    severity: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    needs_review: bool


class OpportunityDetail(OpportunityListItem):
    scan_id: str
    treated_at: datetime | None = None
    treated_by: str | None = None
    treatment_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    rejection_note: str | None = None


class OpportunityPage(BaseModel):
    items: list[OpportunityListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class OpportunityStats(BaseModel):
    open: int = 0
    treated: int = 0
    rejected: int = 0


class ObservationRead(BaseModel):
    id: str
    collection_run_id: str
    observed_at: datetime
    severity: str
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    confidence: str
    evidence: dict
    collection_provider: str
    collection_account_id: str
    collection_started_at: datetime
    collection_finished_at: datetime | None
    collection_status: str


class ObservationPage(BaseModel):
    items: list[ObservationRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class StatusHistoryRead(BaseModel):
    id: str
    from_status: str
    to_status: str
    action: str
    reason: str | None
    note: str | None
    changed_by: str | None
    changed_by_name: str | None
    changed_at: datetime


class StatusHistoryPage(BaseModel):
    items: list[StatusHistoryRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class BulkTransitionBase(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


class BulkReject(BulkTransitionBase):
    reason: RejectionReason

    @model_validator(mode="after")
    def require_other_note(self):
        if self.reason == "OTHER" and not (self.note or "").strip():
            raise ValueError("Uma observação é obrigatória para o motivo Outro.")
        return self


class BulkTransitionResult(BaseModel):
    requested: int
    updated: int
    failed: int = 0
    updated_ids: list[str]
    errors: list[dict] = Field(default_factory=list)
