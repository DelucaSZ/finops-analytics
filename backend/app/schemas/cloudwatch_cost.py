from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CloudWatchCostComponent(BaseModel):
    pricing_rule_id: str
    usage_quantity: Decimal
    unit_price: Decimal
    unit_quantity: Decimal
    pricing_unit: str
    currency: str
    effective_from: datetime
    effective_until: datetime | None
    source: str
    source_reference: str
    pricing_verified_at: datetime


class CloudWatchCostItem(BaseModel):
    group: str | None = None
    period: str | None = None
    currency: str
    gross_estimated_cost: Decimal
    usage_quantity: Decimal
    priced_events: int
    inexact_request_events: int
    failed_events: int
    components: list[CloudWatchCostComponent] = Field(default_factory=list)


class CloudWatchCostTotal(BaseModel):
    currency: str
    gross_estimated_cost: Decimal
    usage_quantity: Decimal


class CloudWatchUnpricedUsage(BaseModel):
    operation: str
    region: str
    events: int
    requests: int
    reason: str


class CloudWatchCostResponse(BaseModel):
    group_by: str | None
    granularity: str | None
    items: list[CloudWatchCostItem]
    totals: list[CloudWatchCostTotal]
    priced_events: int
    unpriced_events: int
    unpriced_usage: list[CloudWatchUnpricedUsage]
    is_complete: bool
    request_count_is_exact: bool
    inexact_request_events: int
    failed_events: int
    free_tier_applied: bool
    pricing_sources: list[str]
    pricing_verified_at: datetime | None
    estimation_basis: str
