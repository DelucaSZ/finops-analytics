from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.schemas.finops_ledger import FinOpsLedgerEntryRead


class FinOpsFlowSummaryItem(BaseModel):
    currency: str
    basis: Literal["ONE_TIME", "MONTHLY"]
    recognized_savings: Decimal
    reallocated: Decimal
    adjustment_net: Decimal
    balance: Decimal

    @field_serializer(
        "recognized_savings",
        "reallocated",
        "adjustment_net",
        "balance",
        when_used="json",
    )
    def serialize_money(self, value: Decimal) -> str:
        return format(value, "f")


class FinOpsFlowTimeseriesPoint(BaseModel):
    currency: str
    basis: Literal["ONE_TIME", "MONTHLY"]
    bucket: str
    recognized_savings: Decimal
    reallocated: Decimal
    adjustment_net: Decimal
    balance_delta: Decimal
    cumulative_balance: Decimal

    @field_serializer(
        "recognized_savings",
        "reallocated",
        "adjustment_net",
        "balance_delta",
        "cumulative_balance",
        when_used="json",
    )
    def serialize_money(self, value: Decimal) -> str:
        return format(value, "f")


class FinOpsFlowAccountBreakdownItem(BaseModel):
    currency: str
    basis: Literal["ONE_TIME", "MONTHLY"]
    account_id: str
    account_name: str | None = None
    recognized_savings: Decimal

    @field_serializer("recognized_savings", when_used="json")
    def serialize_money(self, value: Decimal) -> str:
        return format(value, "f")


class FinOpsFlowSourceBreakdownItem(BaseModel):
    currency: str
    basis: Literal["ONE_TIME", "MONTHLY"]
    source: str
    recognized_savings: Decimal

    @field_serializer("recognized_savings", when_used="json")
    def serialize_money(self, value: Decimal) -> str:
        return format(value, "f")


class FinOpsFlowBreakdowns(BaseModel):
    by_account: list[FinOpsFlowAccountBreakdownItem]
    by_source: list[FinOpsFlowSourceBreakdownItem]


class FinOpsFlowEntryRead(FinOpsLedgerEntryRead):
    account_name: str | None = None
    created_by_name: str | None = None
    opportunity_title: str | None = None
    opportunity_service: str | None = None
    opportunity_resource_id: str | None = None
    logical_entry_type: str
    logical_source: str
    is_reversal: bool = False


class FinOpsFlowEntryPage(BaseModel):
    items: list[FinOpsFlowEntryRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class FinOpsFlowOptions(BaseModel):
    currencies: list[str]
    periodicities: list[str]
    providers: list[str]
    sources: list[str]


class FinOpsFlowMeta(BaseModel):
    generated_at: datetime
    granularity: Literal["day", "month"]
