"""Public HTTP contracts for the provider-neutral Inventory query API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InventorySortField(StrEnum):
    NAME = "name"
    PROVIDER = "provider"
    ACCOUNT = "account"
    RESOURCE_TYPE = "resource_type"
    SERVICE = "service"
    REGION = "region"
    LIFECYCLE_STATUS = "lifecycle_status"
    PRESENCE_STATUS = "presence_status"
    FIRST_SEEN_AT = "first_seen_at"
    LAST_SEEN_AT = "last_seen_at"


class InventorySortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class InventoryResourceResponse(BaseModel):
    """Explicit current-state resource representation used by list endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: int
    provider: str
    cloud_account_id: int
    native_account_id: str
    account_name: str | None

    resource_id: str
    resource_type: str
    native_resource_type: str | None
    service: str | None

    name: str | None
    region: str | None
    availability_zone: str | None

    lifecycle_status: str
    native_status: str | None
    presence_status: str

    tags: dict[str, Any]
    attributes: dict[str, Any]

    first_seen_at: datetime
    last_seen_at: datetime
    last_seen_collection_run_id: str | None = None


class InventoryResourceDetailResponse(InventoryResourceResponse):
    first_seen_collection_run_id: str | None = None


class InventoryResourceListResponse(BaseModel):
    items: list[InventoryResourceResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class InventoryAccountOption(BaseModel):
    id: int
    name: str
    native_account_id: str
    provider: str


class InventoryOptionsResponse(BaseModel):
    providers: list[str]
    accounts: list[InventoryAccountOption]
    regions: list[str]
    resource_types: list[str]
    services: list[str]
    lifecycle_statuses: list[str]
    presence_statuses: list[str]
