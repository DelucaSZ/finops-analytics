from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OciCloudAdvisorIssue:
    category: str
    source: str
    operation: str
    message: str
    compartment_id: str | None = None
    region: str | None = None
    fatal: bool = False


@dataclass
class OciNativeRecommendation:
    recommendation_id: str
    name: str | None
    description: str | None
    category_id: str | None
    importance: str | None
    lifecycle_state: str | None
    status: str | None
    tenancy_id: str | None
    native_estimated_savings: float | None
    currency: str | None
    time_created: datetime | None
    time_updated: datetime | None
    time_status_begin: datetime | None
    time_status_end: datetime | None
    scope_match: str = "unknown"
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OciNativeResourceAction:
    resource_action_id: str
    recommendation_id: str | None
    name: str | None
    resource_id: str | None
    resource_type: str | None
    compartment_id: str | None
    compartment_name: str | None
    action: dict[str, Any] | str | None
    lifecycle_state: str | None
    status: str | None
    native_estimated_savings: float | None
    currency: str | None
    time_created: datetime | None
    time_updated: datetime | None
    time_status_begin: datetime | None
    time_status_end: datetime | None
    scope_match: str = "unknown"
    inventory_match: bool | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OciCloudAdvisorResult:
    status: str
    recommendations: list[OciNativeRecommendation]
    resource_actions: list[OciNativeResourceAction]
    recommendation_count: int | None
    resource_action_count: int | None
    warnings: list[OciCloudAdvisorIssue]
    errors: list[OciCloudAdvisorIssue]
    started_at: datetime
    completed_at: datetime
    coverage: dict[str, bool]
    pages: dict[str, int]

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"
