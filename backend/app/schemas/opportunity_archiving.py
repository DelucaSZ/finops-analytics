from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MAX_BULK_ARCHIVE_IDS = 500


class OpportunityArchiveFilters(BaseModel):
    provider: str | None = None
    account_id: str | None = None
    region: str | None = None
    service: str | None = None
    resource_type: str | None = None
    status: Literal["open", "treated", "rejected"] | None = None
    presence_status: Literal["active", "missing", "resolved_externally"] | None = None
    severity: Literal["low", "medium", "high"] | None = None
    rule: str | None = None
    collection_run_id: str | None = None
    resource_id: str | None = None
    search: str | None = None
    current: bool = False

    def meaningful(self) -> dict[str, str | bool]:
        values = self.model_dump(mode="python")
        result: dict[str, str | bool] = {}
        for key, value in values.items():
            if value is None or value is False:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            result[key] = value
        return result

    @property
    def is_empty(self) -> bool:
        return not self.meaningful()


class BulkArchiveRequest(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_ARCHIVE_IDS)


class ArchiveScopeRequest(BaseModel):
    filters: OpportunityArchiveFilters = Field(default_factory=OpportunityArchiveFilters)
    archive_all: bool = False


class ArchiveMoneyTotal(BaseModel):
    currency: str
    current_monthly_cost: Decimal = Decimal("0")
    estimated_monthly_savings: Decimal = Decimal("0")


class ArchivePreviewResponse(BaseModel):
    matched: int
    to_archive: int
    already_archived: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_provider: dict[str, int] = Field(default_factory=dict)
    by_account: dict[str, int] = Field(default_factory=dict)
    account_count: int = 0
    currencies: list[ArchiveMoneyTotal] = Field(default_factory=list)
    filter_hash: str
    generated_at: datetime
    archive_all: bool = False


class ArchiveOperationResponse(BaseModel):
    requested: int
    matched: int
    archived: int
    already_archived: int
    failed: int = 0
    correlation_id: str
    cycle_id: str | None = None
    sample_ids: list[str] = Field(default_factory=list)
    ids_truncated: bool = False
    filter_hash: str | None = None


class PeriodCloseRequest(ArchiveScopeRequest):
    cycle_id: str


class PeriodClosePreviewResponse(BaseModel):
    cycle_id: str
    label: str
    period_start: datetime
    period_end: datetime
    cycle_status: str
    snapshots_to_create: int
    collection_runs: int
    failed_collection_runs: int
    running_collection_runs: int
    archive: ArchivePreviewResponse


class PeriodCloseResponse(BaseModel):
    cycle_closed: bool
    cycle_id: str
    snapshots_created: int
    collection_runs: int
    failed_collection_runs: int
    matched: int
    archived: int
    already_archived: int
    failed: int = 0
    correlation_id: str
    sample_ids: list[str] = Field(default_factory=list)
    ids_truncated: bool = False
    filter_hash: str | None = None
