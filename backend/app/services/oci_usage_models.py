from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class OciUsageIssue:
    category: str
    source: str
    operation: str
    message: str
    fatal: bool = False


@dataclass
class OciUsageRecord:
    start_time: datetime | None
    end_time: datetime | None
    resource_id: str | None
    service: str | None
    region: str | None
    compartment_id: str | None
    sku_name: str | None
    sku_part_number: str | None
    unit: str | None
    usage_quantity: Decimal | None
    actual_cost: Decimal | None
    currency: str | None
    source: str = "oci_usage_api"
    scope_match: str = "unknown"
    inventory_match: bool | None = None
    native_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OciUsageResult:
    status: str
    period_start: datetime
    period_end: datetime
    records: list[OciUsageRecord]
    sku_usage_records: list[OciUsageRecord]
    totals_by_currency: dict[str, Decimal]
    warnings: list[OciUsageIssue]
    errors: list[OciUsageIssue]
    coverage: dict[str, bool]
    pages: dict[str, int]
    request_count: int
    started_at: datetime
    completed_at: datetime

    @property
    def currency(self) -> str | None:
        currencies = tuple(self.totals_by_currency)
        return currencies[0] if len(currencies) == 1 else None

    @property
    def total_cost(self) -> Decimal | None:
        if len(self.totals_by_currency) != 1:
            return None
        return next(iter(self.totals_by_currency.values()))

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"
