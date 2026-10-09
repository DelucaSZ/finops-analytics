from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.finding import OpportunityPresenceStatus

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


class EvidenceMetric(BaseModel):
    key: str
    label: str
    value: int | float | str | bool
    unit: str | None = None
    kind: str = "observed"


class EvidenceCriterion(BaseModel):
    key: str
    label: str
    observed_value: int | float | str | bool | None = None
    operator: str
    threshold_value: int | float | str | bool
    unit: str | None = None


class EvidenceContributor(BaseModel):
    key: str
    label: str
    previous_value: float | None = None
    current_value: float | None = None
    delta: float
    unit: str | None = None


class RuleExplanation(BaseModel):
    key: str
    name: str
    description: str


class OpportunityEvidence(BaseModel):
    schema_version: int = 1
    summary: str
    metrics: list[EvidenceMetric] = Field(default_factory=list)
    criteria: list[EvidenceCriterion] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rule: RuleExplanation
    source: str
    notes: list[str] = Field(default_factory=list)
    contributors: list[EvidenceContributor] = Field(default_factory=list)
    evaluated_at: str | None = None


class OpportunityListItem(BaseModel):
    id: str
    fingerprint: str
    provider: str
    account_id: str
    account_name: str | None = None
    legacy_account_id: int | None = None
    rule_key: str
    service: str
    region: str | None
    resource_id: str
    resource_name: str | None
    resource_type: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    title: str
    description: str
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    currency: str
    confidence: str
    severity: str
    status: str
    presence_status: OpportunityPresenceStatus
    missing_since_at: datetime | None = None
    resolved_externally_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    total_occurrence_count: int
    needs_review: bool


class ObservationRead(BaseModel):
    id: str
    collection_run_id: str
    observed_at: datetime
    severity: str
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    currency: str
    confidence: str
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: OpportunityEvidence
    collection_provider: str
    collection_account_id: str
    collection_started_at: datetime
    collection_finished_at: datetime | None
    collection_status: str


class OpportunityDetail(OpportunityListItem):
    scan_id: str | None
    treated_at: datetime | None = None
    treated_by: str | None = None
    treatment_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    rejection_note: str | None = None
    rule: RuleExplanation
    latest_observation: ObservationRead | None = None
    latest_evidence: OpportunityEvidence | None = None


class OpportunityPage(BaseModel):
    items: list[OpportunityListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class OpportunityAccountOption(BaseModel):
    provider: str
    account_id: str
    account_name: str | None = None


class OpportunityOptions(BaseModel):
    providers: list[str] = Field(default_factory=list)
    accounts: list[OpportunityAccountOption] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    resource_types: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class OpportunityStats(BaseModel):
    open: int = 0
    treated: int = 0
    rejected: int = 0


class ObservationPage(BaseModel):
    items: list[ObservationRead]
    page: int
    page_size: int
    total: int
    total_pages: int
    retained_total: int
    total_occurrence_count: int
    history_complete: bool
    retention_enabled: bool
    retention_days: int
    retention_cutoff: datetime


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
