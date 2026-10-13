import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.base import utcnow

PricingStatus = Literal["active", "inactive", "future", "expired", "all"]


class PricingItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    service: str
    sku: str
    description: str
    unit: str
    price: Decimal
    currency: str
    effective_from: datetime
    effective_until: datetime | None
    enabled: bool
    source: str
    created_at: datetime
    updated_at: datetime


class PricingListRead(BaseModel):
    items: list[PricingItemRead]
    total: int
    limit: int
    offset: int


class PricingMetadataRead(BaseModel):
    provider: str
    currency: str
    services: list[str]
    units: list[str]
    sources: list[str]


class PricingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    price: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    effective_from: datetime = Field(default_factory=utcnow)
    effective_until: datetime | None = None
    enabled: bool = True

    @field_validator("service", "sku", "description", "unit")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned

    @field_validator("service")
    @classmethod
    def normalize_service(cls, value: str) -> str:
        return value.lower()

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", normalized):
            raise ValueError("unit must be an uppercase pricing unit identifier")
        return normalized

    @model_validator(mode="after")
    def validate_interval(self) -> "PricingCreate":
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be after effective_from")
        return self


class PricingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=8)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    effective_from: datetime | None = None

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("description cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_changes(self) -> "PricingUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one change is required")
        if "price" in self.model_fields_set and self.price is None:
            raise ValueError("price cannot be null")
        if "description" in self.model_fields_set and self.description is None:
            raise ValueError("description cannot be null")
        if "effective_from" in self.model_fields_set and self.effective_from is None:
            raise ValueError("effective_from cannot be null")
        if self.effective_from is not None and self.price is None:
            raise ValueError("effective_from requires a new price")
        return self
