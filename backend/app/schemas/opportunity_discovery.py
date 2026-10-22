from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DiscoveryType = Literal[
    "observed",
    "first_seen",
    "new_vs_previous",
    "reappeared",
    "continued",
    "no_longer_detected",
]


class OpportunityRunChangeCounts(BaseModel):
    observed: int = 0
    first_seen: int = 0
    new_vs_previous: int = 0
    reappeared: int = 0
    continued: int = 0
    no_longer_detected: int = 0
    operational_new_vs_previous: int = 0


class OpportunityRunWarning(BaseModel):
    code: str
    message: str


class OpportunityRunCoverage(BaseModel):
    total_scopes: int = 0
    successful_scopes: int = 0
    failed_scopes: int = 0
    skipped_scopes: int = 0
    comparable_scopes: int = 0


class OpportunityRunReference(BaseModel):
    id: str
    provider: str
    account_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    analyzer_version: str | None = None
    detailed_observations_available: bool


class OpportunityRunScopeIssue(BaseModel):
    provider: str
    account_id: str
    region: str
    service: str | None = None
    rule_key: str
    status: str
    error_detail: str | None = None


class OpportunityRunChanges(BaseModel):
    collection_run_id: str
    status: str
    comparison_status: str
    baseline_run_id: str | None = None
    baseline: OpportunityRunReference | None = None
    comparable: bool
    reason: str | None = None
    target_details_available: bool = True
    comparison_details_available: bool = False
    rules_version_changed: bool | None = None
    partial_coverage: bool = False
    coverage: OpportunityRunCoverage
    scope_issues: list[OpportunityRunScopeIssue] = Field(default_factory=list)
    summary: OpportunityRunChangeCounts
    warnings: list[OpportunityRunWarning] = Field(default_factory=list)


class RunOpportunityItem(BaseModel):
    id: str
    fingerprint: str
    provider: str
    account_id: str
    rule_key: str
    service: str
    region: str | None = None
    resource_id: str
    resource_name: str | None = None
    resource_type: str | None = None
    title: str
    severity: str
    status: str
    presence_status: str
    first_seen_at: datetime
    last_seen_at: datetime
    first_seen_collection_run_id: str | None = None
    last_seen_collection_run_id: str | None = None
    archived_at: datetime | None = None


class RunOpportunityPage(BaseModel):
    collection_run_id: str
    baseline_run_id: str | None = None
    comparable: bool
    reason: str | None = None
    discovery_type: DiscoveryType
    items: list[RunOpportunityItem]
    page: int
    page_size: int
    total: int
    total_pages: int
