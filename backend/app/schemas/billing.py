from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


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


class BillingDataStatus(StrEnum):
    """Temporal provenance of a billing value.

    ACTUAL and ESTIMATED are emitted from AWS GetCostAndUsage using the
    ResultsByTime[].Estimated flag. FORECAST is reserved for values produced by
    an explicit forecast source and must never be inferred from dates alone.
    Aggregate values can expose the two mixed states without pretending the
    complete amount has one homogeneous provenance.
    """

    ACTUAL = "ACTUAL"
    ESTIMATED = "ESTIMATED"
    PARTIALLY_ESTIMATED = "PARTIALLY_ESTIMATED"
    FORECAST = "FORECAST"
    INCLUDES_FORECAST = "INCLUDES_FORECAST"


class BillingStatusModel(BaseModel):
    status: BillingDataStatus

    @computed_field
    @property
    def estimated(self) -> bool:
        """Backward-compatible flag derived from the canonical status.

        Consumers should use ``status``. Keeping this computed field avoids a
        contradictory pair of independently writable ``status``/``estimated``
        values while existing clients migrate.
        """

        return self.status in {
            BillingDataStatus.ESTIMATED,
            BillingDataStatus.PARTIALLY_ESTIMATED,
        }


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


def _validate_account_ids(value: list[int]) -> list[int]:
    if any(account_id <= 0 for account_id in value):
        raise ValueError("account_ids must contain positive DeepOps account IDs")
    if len(value) != len(set(value)):
        raise ValueError("account_ids must not contain duplicates")
    return value


def _validate_record_types(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("exclude_record_types must not contain empty values")
    unknown = sorted(set(cleaned) - AWS_RECORD_TYPES)
    if unknown:
        raise ValueError(f"Unsupported AWS record type(s): {', '.join(unknown)}")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("exclude_record_types must not contain duplicates")
    return cleaned


class _BillingRequestScope(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date

    @field_validator("account_ids")
    @classmethod
    def unique_account_ids(cls, value: list[int]) -> list[int]:
        return _validate_account_ids(value)

    @model_validator(mode="after")
    def valid_period(self) -> _BillingRequestScope:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class AwsBillingApiRequest(_BillingRequestScope):
    """Public query contract. Optional methodology fields are runtime overrides."""

    profile_id: str | None = None
    granularity: BillingGranularity | None = None
    metric: BillingMetric | None = None
    group_by: BillingGroupBy | None = None
    exclude_record_types: list[str] | None = Field(default=None, max_length=100)

    @field_validator("exclude_record_types")
    @classmethod
    def valid_record_types(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_record_types(value)


class AwsBillingRequest(_BillingRequestScope):
    """Canonical resolved request consumed by the AWS Billing service."""

    granularity: BillingGranularity = BillingGranularity.DAILY
    metric: BillingMetric = BillingMetric.AMORTIZED_COST
    group_by: BillingGroupBy = BillingGroupBy.NONE
    exclude_record_types: list[str] = Field(default_factory=lambda: ["Credit"], max_length=100)

    @field_validator("exclude_record_types")
    @classmethod
    def valid_record_types(cls, value: list[str]) -> list[str]:
        return _validate_record_types(value)


class BillingProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    granularity: BillingGranularity = BillingGranularity.DAILY
    metric: BillingMetric = BillingMetric.AMORTIZED_COST
    group_by: BillingGroupBy = BillingGroupBy.NONE
    exclude_record_types: list[str] = Field(default_factory=lambda: ["Credit"], max_length=100)
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("exclude_record_types")
    @classmethod
    def valid_record_types(cls, value: list[str]) -> list[str]:
        return _validate_record_types(value)


class BillingProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    granularity: BillingGranularity | None = None
    metric: BillingMetric | None = None
    group_by: BillingGroupBy | None = None
    exclude_record_types: list[str] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("exclude_record_types")
    @classmethod
    def valid_record_types(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_record_types(value)


class BillingProfileRead(BaseModel):
    id: str
    name: str
    description: str | None
    granularity: BillingGranularity
    metric: BillingMetric
    group_by: BillingGroupBy
    exclude_record_types: list[str]
    is_default: bool
    enabled: bool
    is_system: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResolvedBillingOptions(BaseModel):
    granularity: BillingGranularity
    metric: BillingMetric
    group_by: BillingGroupBy
    exclude_record_types: list[str]


class BillingProfileMetadata(BaseModel):
    profile_id: str | None = None
    profile_name: str | None = None
    resolved_options: ResolvedBillingOptions | None = None


class BillingSummaryTotal(BillingStatusModel):
    amount: Decimal
    currency: str


class BillingSummaryResponse(BillingProfileMetadata):
    metric: BillingMetric
    start_date: date
    end_date: date
    totals: list[BillingSummaryTotal]


class BillingSeriesGroup(BillingStatusModel):
    key: str
    label: str
    amount: Decimal
    currency: str
    deepops_account_id: int | None = None
    aws_account_id: str | None = None
    display_name: str | None = None


class BillingSeriesPoint(BillingStatusModel):
    start_date: date
    end_date: date
    amount: Decimal
    currency: str
    groups: list[BillingSeriesGroup] = Field(default_factory=list)


class BillingTimeSeriesResponse(BillingProfileMetadata):
    metric: BillingMetric
    granularity: BillingGranularity
    group_by: BillingGroupBy
    start_date: date
    end_date: date
    points: list[BillingSeriesPoint]


class BillingBreakdownItem(BillingStatusModel):
    key: str
    label: str
    amount: Decimal
    currency: str
    deepops_account_id: int | None = None
    aws_account_id: str | None = None
    display_name: str | None = None


class BillingBreakdownResponse(BillingProfileMetadata):
    metric: BillingMetric
    group_by: BillingGroupBy
    start_date: date
    end_date: date
    items: list[BillingBreakdownItem]
