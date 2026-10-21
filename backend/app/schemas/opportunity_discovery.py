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


class OpportunityRunChanges(BaseModel):
    collection_run_id: str
    baseline_run_id: str | None = None
    comparable: bool
    reason: str | None = None
    rules_version_changed: bool | None = None
    partial_coverage: bool = False
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
