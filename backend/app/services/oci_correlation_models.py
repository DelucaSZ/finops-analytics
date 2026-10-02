from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.services.oci_cloud_advisor_models import (
    OciCloudAdvisorIssue,
    OciNativeRecommendation,
    OciNativeResourceAction,
)
from app.services.oci_discovery_models import (
    OciDiscoveredResource,
    OciDiscoveryIssue,
    OciResourceRelationship,
)
from app.services.oci_monitoring_models import (
    OciMetricSeries,
    OciMonitoringIssue,
    OciResourceMetrics,
)
from app.services.oci_usage_models import OciUsageIssue, OciUsageRecord


@dataclass(frozen=True)
class OciCorrelationWarning:
    category: str
    message: str
    resource_id: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class OciResourceRecommendationLink:
    action: OciNativeResourceAction
    recommendation: OciNativeRecommendation | None


@dataclass
class OciResourceUsageContext:
    records: list[OciUsageRecord] = field(default_factory=list)
    sku_usage_records: list[OciUsageRecord] = field(default_factory=list)
    totals_by_currency: dict[str, Decimal] = field(default_factory=dict)
    period_start: datetime | None = None
    period_end: datetime | None = None


@dataclass
class OciResourceMonitoringContext:
    summary: OciResourceMetrics | None = None
    series: list[OciMetricSeries] = field(default_factory=list)
    period_start: datetime | None = None
    period_end: datetime | None = None
    interval: str | None = None


@dataclass
class OciResourceAnalysisContext:
    resource_id: str
    inventory: OciDiscoveredResource | None = None
    relationships: list[OciResourceRelationship] = field(default_factory=list)
    native_recommendations: list[OciResourceRecommendationLink] = field(default_factory=list)
    usage: OciResourceUsageContext = field(default_factory=OciResourceUsageContext)
    monitoring: OciResourceMonitoringContext = field(default_factory=OciResourceMonitoringContext)
    coverage: dict[str, str] = field(default_factory=dict)
    inventory_coverage: dict[str, str] = field(default_factory=dict)
    relationship_coverage: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, tuple[str, ...]] = field(default_factory=dict)
    warnings: list[OciCorrelationWarning] = field(default_factory=list)

    @property
    def resource_type(self) -> str | None:
        if self.inventory is not None:
            return self.inventory.resource_type
        for link in self.native_recommendations:
            if link.action.resource_type:
                return link.action.resource_type
        return None

    @property
    def name(self) -> str | None:
        return self.inventory.name if self.inventory is not None else None

    @property
    def region(self) -> str | None:
        if self.inventory is not None:
            return self.inventory.region
        if self.monitoring.summary is not None:
            return self.monitoring.summary.region
        for record in self.usage.records:
            if record.region:
                return record.region
        return None

    @property
    def compartment_id(self) -> str | None:
        if self.inventory is not None:
            return self.inventory.compartment_id
        if self.monitoring.summary is not None:
            return self.monitoring.summary.compartment_id
        for link in self.native_recommendations:
            if link.action.compartment_id:
                return link.action.compartment_id
        for record in self.usage.records:
            if record.compartment_id:
                return record.compartment_id
        return None

    @property
    def lifecycle_state(self) -> str | None:
        return self.inventory.lifecycle_state if self.inventory is not None else None

    @property
    def has_inventory(self) -> bool:
        return self.inventory is not None


@dataclass
class OciAccountAnalysisContext:
    recommendations: list[OciNativeRecommendation] = field(default_factory=list)
    resource_actions_without_resource_id: list[OciNativeResourceAction] = field(
        default_factory=list
    )
    usage_records_without_resource_id: list[OciUsageRecord] = field(default_factory=list)
    sku_usage_records_without_resource_id: list[OciUsageRecord] = field(default_factory=list)
    metric_series_without_resource_id: list[OciMetricSeries] = field(default_factory=list)


@dataclass(frozen=True)
class OciCorrelationSourceCoverage:
    status: str
    coverage: dict[str, bool]
    warning_count: int
    error_count: int


@dataclass
class OciCorrelationResult:
    status: str
    resource_contexts: list[OciResourceAnalysisContext]
    account_context: OciAccountAnalysisContext
    unmatched_resource_ids_by_source: dict[str, tuple[str, ...]]
    coverage: dict[str, OciCorrelationSourceCoverage]
    source_warnings: dict[
        str,
        tuple[OciDiscoveryIssue | OciCloudAdvisorIssue | OciUsageIssue | OciMonitoringIssue, ...],
    ]
    source_errors: dict[
        str,
        tuple[OciDiscoveryIssue | OciCloudAdvisorIssue | OciUsageIssue | OciMonitoringIssue, ...],
    ]
    warnings: list[OciCorrelationWarning]
    time_alignment: str
    source_freshness: dict[str, datetime]
