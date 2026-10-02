from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OciMonitoringIssue:
    category: str
    source: str
    operation: str
    message: str
    region: str | None = None
    compartment_id: str | None = None
    metric_name: str | None = None
    fatal: bool = False


@dataclass(frozen=True)
class OciMetricDatapoint:
    timestamp: datetime
    value: float


@dataclass
class OciMetricSeries:
    namespace: str
    metric_name: str
    resource_id: str | None
    region: str
    compartment_id: str
    dimensions: dict[str, str]
    unit: str | None
    period_start: datetime
    period_end: datetime
    statistic: str
    interval: str
    datapoints: list[OciMetricDatapoint]
    coverage: str
    inventory_match: bool | None = None

    @property
    def sample_count(self) -> int:
        return len(self.datapoints)

    @property
    def first_datapoint(self) -> datetime | None:
        return self.datapoints[0].timestamp if self.datapoints else None

    @property
    def last_datapoint(self) -> datetime | None:
        return self.datapoints[-1].timestamp if self.datapoints else None


@dataclass
class OciResourceMetrics:
    resource_id: str
    region: str | None
    compartment_id: str | None
    lifecycle_state: str | None
    resource_created_at: datetime | None
    cpu_mean: float | None = None
    cpu_p95: float | None = None
    cpu_max: float | None = None
    memory_mean: float | None = None
    memory_p95: float | None = None
    memory_max: float | None = None
    network_in_total_bytes: float | None = None
    network_out_total_bytes: float | None = None
    sample_counts: dict[str, int] = field(default_factory=dict)
    missing_metrics: list[str] = field(default_factory=list)
    coverage: str = "unavailable"
    coverage_reasons: list[str] = field(default_factory=list)
    metrics_available: bool = False


@dataclass
class OciMonitoringResult:
    status: str
    period_start: datetime
    period_end: datetime
    interval: str
    series: list[OciMetricSeries]
    resources: list[OciResourceMetrics]
    orphan_series: list[OciMetricSeries]
    warnings: list[OciMonitoringIssue]
    errors: list[OciMonitoringIssue]
    coverage: dict[str, bool]
    request_count: int
    started_at: datetime
    completed_at: datetime

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"
