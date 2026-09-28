from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardScope(BaseModel):
    provider: str | None = None
    account_id: str | None = None
    valid_scope_count: int | None = None
    has_current_data: bool | None = None


class DashboardOpportunityTotals(BaseModel):
    open: int
    treated: int
    rejected: int
    new_since_previous: int


class DashboardSeverity(BaseModel):
    high: int
    medium: int
    low: int
    other: int = 0


class DashboardMoneyTotal(BaseModel):
    currency: str
    amount: Decimal


class DashboardFinancial(BaseModel):
    metric: str
    label: str
    period: str
    totals: list[DashboardMoneyTotal] = Field(default_factory=list)


class DashboardProviderDistribution(BaseModel):
    provider: str
    open: int
    estimated_monthly_savings: Decimal | None = None
    currency: str | None = None


class DashboardAccountDistribution(BaseModel):
    provider: str
    account_id: str
    account_name: str | None = None
    open: int
    estimated_monthly_savings: Decimal | None = None
    currency: str | None = None


class DashboardTopOpportunity(BaseModel):
    id: str
    title: str
    rule_key: str
    resource_id: str
    resource_name: str | None = None
    region: str | None
    provider: str
    account_id: str
    account_name: str | None = None
    collection_run_id: str
    severity: str
    estimated_monthly_savings: Decimal
    currency: str


class DashboardRecentChanges(BaseModel):
    new: int
    no_longer_detected: int
    changed: int | None = None
    changed_available: bool
    comparable_scopes: int
    scopes_without_baseline: int
    rules_version_changed_scopes: int
    rules_version_unknown_scopes: int


class DashboardSummary(BaseModel):
    scope: DashboardScope
    opportunities: DashboardOpportunityTotals
    severity: DashboardSeverity
    financial: DashboardFinancial
    by_provider: list[DashboardProviderDistribution] = Field(default_factory=list)
    by_account: list[DashboardAccountDistribution] = Field(default_factory=list)
    top_opportunities: list[DashboardTopOpportunity] = Field(default_factory=list)
    recent_changes: DashboardRecentChanges


class DashboardCollectionExecution(BaseModel):
    id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    has_warnings: bool = False


class DashboardValidCollection(BaseModel):
    id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    rules_version: str | None = None
    has_warnings: bool = False


class DashboardCollectionHealthItem(BaseModel):
    provider: str
    account_id: str
    account_name: str | None = None
    latest_execution: DashboardCollectionExecution
    latest_valid: DashboardValidCollection | None = None


class DashboardLatestExecutionCounts(BaseModel):
    failed: int
    running: int
    success: int


class DashboardOldestValidScope(BaseModel):
    provider: str
    account_id: str
    account_name: str | None = None
    started_at: datetime


class DashboardCollectionHealth(BaseModel):
    scope: DashboardScope
    total_scopes: int
    valid_scopes: int
    latest_execution: DashboardLatestExecutionCounts
    valid_with_warnings: int
    newest_valid_at: datetime | None = None
    oldest_valid_at: datetime | None = None
    oldest_valid_scope: DashboardOldestValidScope | None = None
    stale_policy_configured: bool
    items: list[DashboardCollectionHealthItem] = Field(default_factory=list)
