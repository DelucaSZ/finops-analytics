from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class FinOpsLedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entry_type: str
    direction: str
    provider: str
    cloud_account_id: int
    account_id: str
    amount: Decimal
    currency: str
    effective_at: datetime
    source: str
    source_reference: str | None = None
    opportunity_id: str | None = None
    source_event_id: str | None = None
    idempotency_key: str | None = None
    description: str | None = None
    context: dict[str, Any]
    periodicity: str
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    created_by: str | None = None
    created_at: datetime
    reversal_of_id: str | None = None

    @field_serializer("amount", when_used="json")
    def serialize_amount(self, value: Decimal) -> str:
        return format(value, "f")


class FinOpsLedgerPage(BaseModel):
    items: list[FinOpsLedgerEntryRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class FinOpsLedgerBalance(BaseModel):
    credits: Decimal
    debits: Decimal
    balance: Decimal

    @field_serializer("credits", "debits", "balance", when_used="json")
    def serialize_money(self, value: Decimal) -> str:
        return format(value, "f")
