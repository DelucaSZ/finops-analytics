from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.finding import OpportunityPresenceStatus
from app.models.opportunity_presence_history import OpportunityPresenceReason


class PresenceHistoryRead(BaseModel):
    id: str
    from_status: OpportunityPresenceStatus
    to_status: OpportunityPresenceStatus
    reason: OpportunityPresenceReason
    occurred_at: datetime
    missing_count: int
    missing_threshold: int | None = None
    collection_run_id: str | None = None
    collection_scope_execution_id: str | None = None
    collection_provider: str | None = None
    collection_account_id: str | None = None
    collection_started_at: datetime | None = None
    scope_region: str | None = None
    scope_rule_key: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class PresenceHistoryPage(BaseModel):
    items: list[PresenceHistoryRead]
    page: int
    page_size: int
    total: int
    total_pages: int
