from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class BillingGranularity(StrEnum):
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class BillingMetric(StrEnum):
    AMORTIZED_COST = "AMORTIZED_COST"
    NET_AMORTIZED_COST = "NET_AMORTIZED_COST"
    UNBLENDED_COST = "UNBLENDED_COST"


class BillingGroupBy(StrEnum):
    NONE = "NONE"
    SERVICE = "SERVICE"
    ACCOUNT = "ACCOUNT"


AWS_RECORD_TYPES = frozenset(
    {
        "Credit",
        "DiscountedUsage",
        "Fee",
        "Refund",
        "RIFee",
        "SavingsPlanCoveredUsage",
        "SavingsPlanNegation",
        "SavingsPlanRecurringFee",
        "SavingsPlanUpfrontFee",
        "Tax",
        "Usage",
    }
)


class AwsBillingRequest(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    granularity: BillingGranularity = BillingGranularity.DAILY
    metric: BillingMetric = BillingMetric.AMORTIZED_COST
    group_by: BillingGroupBy = BillingGroupBy.NONE
    exclude_record_types: list[str] = Field(default_factory=lambda: ["Credit"], max_length=100)

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, value: list[int]) -> list[int]:
        if any(account_id <= 0 for account_id in value):
            raise ValueError("account_ids must contain positive DeepOps account IDs")
        if len(value) != len(set(value)):
            raise ValueError("account_ids must not contain duplicates")
        return value

    @field_validator("exclude_record_types")
    @classmethod
    def valid_record_types(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("exclude_record_types must not contain empty values")
        unknown = sorted(set(cleaned) - AWS_RECORD_TYPES)
        if unknown:
            raise ValueError(f"Unsupported AWS record type(s): {', '.join(unknown)}")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("exclude_record_types must not contain duplicates")
        return cleaned

    @model_validator(mode="after")
    def valid_period(self) -> "AwsBillingRequest":
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class BillingSummaryTotal(BaseModel):
    amount: Decimal
    currency: str
    estimated: bool


class BillingSummaryResponse(BaseModel):
    metric: BillingMetric
    start_date: date
    end_date: date
    totals: list[BillingSummaryTotal]


class BillingSeriesPoint(BaseModel):
    start_date: date
    end_date: date
    amount: Decimal
    currency: str
    estimated: bool


class BillingTimeSeriesResponse(BaseModel):
    metric: BillingMetric
    granularity: BillingGranularity
    start_date: date
    end_date: date
    points: list[BillingSeriesPoint]


class BillingBreakdownItem(BaseModel):
    key: str
    label: str
    amount: Decimal
    currency: str
    estimated: bool
    deepops_account_id: int | None = None
    aws_account_id: str | None = None
    display_name: str | None = None


class BillingBreakdownResponse(BaseModel):
    metric: BillingMetric
    group_by: BillingGroupBy
    start_date: date
    end_date: date
    items: list[BillingBreakdownItem]
