from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class FinOpsLedgerManualCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_type: Literal["SAVING", "REALLOCATION", "ADJUSTMENT"]
    direction: Literal["CREDIT", "DEBIT"] | None = None
    provider: str = Field(min_length=1, max_length=16)
    cloud_account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    currency: Literal["BRL", "USD"]
    effective_date: date
    periodicity: Literal["ONE_TIME", "MONTHLY"] = "ONE_TIME"
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    description: str = Field(min_length=3, max_length=2000)
    manual_entry_request_id: UUID

    @field_validator("provider")
    @classmethod
    def normalize_provider_input(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("provider is required")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("description must contain at least 3 characters")
        return normalized

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.entry_type == "SAVING" and self.direction not in {None, "CREDIT"}:
            raise ValueError("SAVING entries must use CREDIT direction")
        if self.entry_type == "REALLOCATION" and self.direction not in {None, "DEBIT"}:
            raise ValueError("REALLOCATION entries must use DEBIT direction")
        if self.entry_type == "ADJUSTMENT" and self.direction is None:
            raise ValueError("ADJUSTMENT entries require direction")
        if self.reference_period_end is not None and self.reference_period_start is None:
            raise ValueError("reference_period_end requires reference_period_start")
        if (
            self.reference_period_start is not None
            and self.reference_period_end is not None
            and self.reference_period_end < self.reference_period_start
        ):
            raise ValueError("reference_period_end cannot precede reference_period_start")
        return self


class FinOpsLedgerReverse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("reason must contain at least 3 characters")
        return normalized


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
    is_reversed: bool = False
    reversed_by_id: str | None = None

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
