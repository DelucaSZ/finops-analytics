from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any

from app.services.oci_cloud_advisor_models import OciCloudAdvisorResult
from app.services.oci_correlation_models import (
    OciAccountAnalysisContext,
    OciCorrelationResult,
    OciCorrelationSourceCoverage,
    OciCorrelationWarning,
    OciResourceAnalysisContext,
    OciResourceMonitoringContext,
    OciResourceRecommendationLink,
    OciResourceUsageContext,
)
from app.services.oci_discovery_models import OciDiscoveryResult
from app.services.oci_monitoring_models import OciMetricSeries, OciMonitoringResult
from app.services.oci_usage_models import OciUsageRecord, OciUsageResult


def _stable_token(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _stable_unique[T](items: list[T]) -> list[T]:
    by_token: dict[str, T] = {}
    for item in items:
        by_token.setdefault(_stable_token(item), item)
    return [by_token[token] for token in sorted(by_token)]


def _stable_unique_by_id[T](items: list[T], id_getter) -> list[T]:
    grouped: dict[str, list[T]] = {}
    without_id: list[T] = []
    for item in items:
        item_id = id_getter(item)
        if item_id:
            grouped.setdefault(str(item_id), []).append(item)
        else:
            without_id.append(item)
    selected = [min(group, key=_stable_token) for group in grouped.values()]
    ordered = sorted(
        selected,
        key=lambda item: (str(id_getter(item)), _stable_token(item)),
    )
    return ordered + _stable_unique(without_id)


def _totals_by_currency(records: list[OciUsageRecord]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for record in records:
        if record.actual_cost is None or record.currency is None:
            continue
        totals[record.currency] = totals.get(record.currency, Decimal("0")) + record.actual_cost
    return {currency: totals[currency] for currency in sorted(totals)}


def _time_alignment(usage: OciUsageResult, monitoring: OciMonitoringResult) -> str:
    if usage.period_start == monitoring.period_start and usage.period_end == monitoring.period_end:
        return "exact"
    if usage.period_start < monitoring.period_end and monitoring.period_start < usage.period_end:
        return "overlapping"
    return "disjoint"


def _coverage_map(result) -> dict[str, bool]:
    coverage = getattr(result, "coverage", None)
    if coverage is not None:
        return dict(sorted(coverage.items()))
    counts_by_type = getattr(result, "counts_by_type", None)
    if counts_by_type is not None:
        return {
            resource_type: count is not None
            for resource_type, count in sorted(counts_by_type.items())
        }
    return {}


def _source_coverage(result) -> OciCorrelationSourceCoverage:
    return OciCorrelationSourceCoverage(
        status=result.status,
        coverage=_coverage_map(result),
        warning_count=len(result.warnings),
        error_count=len(result.errors),
    )


def _context_source_status(result) -> str:
    if result.status == "success":
        return "complete"
    if result.status == "partial":
        return "partial"
    return "unavailable"


def correlate_oci_datasets(
    discovery: OciDiscoveryResult,
    advisor: OciCloudAdvisorResult,
    usage: OciUsageResult,
    monitoring: OciMonitoringResult,
) -> OciCorrelationResult:
    """Correlate normalized OCI datasets without network, persistence, or policy decisions."""

    inventory_by_id = {
        resource.resource_id: resource
        for resource in sorted(discovery.resources, key=lambda item: item.resource_id)
        if resource.resource_id
    }
    inventory_ids = set(inventory_by_id)

    recommendations = _stable_unique_by_id(
        list(advisor.recommendations), lambda item: item.recommendation_id
    )
    recommendations_by_id = {
        item.recommendation_id: item for item in recommendations if item.recommendation_id
    }
    actions = _stable_unique_by_id(
        list(advisor.resource_actions), lambda item: item.resource_action_id
    )
    actions_by_resource: dict[str, list] = {}
    actions_without_resource_id = []
    recommendation_ids_with_resource_action: set[str] = set()
    for action in actions:
        if action.resource_id:
            actions_by_resource.setdefault(action.resource_id, []).append(action)
            if action.recommendation_id:
                recommendation_ids_with_resource_action.add(action.recommendation_id)
        else:
            actions_without_resource_id.append(action)

    usage_records = _stable_unique(list(usage.records))
    sku_usage_records = _stable_unique(list(usage.sku_usage_records))
    usage_by_resource: dict[str, list[OciUsageRecord]] = {}
    sku_usage_by_resource: dict[str, list[OciUsageRecord]] = {}
    usage_without_resource_id = []
    sku_usage_without_resource_id = []
    for record in usage_records:
        if record.resource_id:
            usage_by_resource.setdefault(record.resource_id, []).append(record)
        else:
            usage_without_resource_id.append(record)
    for record in sku_usage_records:
        if record.resource_id:
            sku_usage_by_resource.setdefault(record.resource_id, []).append(record)
        else:
            sku_usage_without_resource_id.append(record)

    metric_summaries = _stable_unique_by_id(
        list(monitoring.resources), lambda item: item.resource_id
    )
    metrics_by_resource = {item.resource_id: item for item in metric_summaries if item.resource_id}
    all_series = _stable_unique(list(monitoring.series) + list(monitoring.orphan_series))
    series_by_resource: dict[str, list[OciMetricSeries]] = {}
    series_without_resource_id = []
    for series in all_series:
        if series.resource_id:
            series_by_resource.setdefault(series.resource_id, []).append(series)
        else:
            series_without_resource_id.append(series)

    relationships_by_resource: dict[str, list] = {}
    for relationship in _stable_unique(list(discovery.relationships)):
        relationships_by_resource.setdefault(relationship.source_id, []).append(relationship)
        if relationship.target_id != relationship.source_id:
            relationships_by_resource.setdefault(relationship.target_id, []).append(relationship)

    all_resource_ids = sorted(
        inventory_ids
        | set(actions_by_resource)
        | set(usage_by_resource)
        | set(sku_usage_by_resource)
        | set(metrics_by_resource)
        | set(series_by_resource)
    )

    contexts: list[OciResourceAnalysisContext] = []
    correlation_warnings: list[OciCorrelationWarning] = []
    for resource_id in all_resource_ids:
        inventory = inventory_by_id.get(resource_id)
        links = [
            OciResourceRecommendationLink(
                action=action,
                recommendation=recommendations_by_id.get(action.recommendation_id or ""),
            )
            for action in sorted(
                actions_by_resource.get(resource_id, []),
                key=lambda item: (item.resource_action_id, _stable_token(item)),
            )
        ]
        records = usage_by_resource.get(resource_id, [])
        sku_records = sku_usage_by_resource.get(resource_id, [])
        resource_series = sorted(
            series_by_resource.get(resource_id, []),
            key=lambda item: (
                item.metric_name,
                item.statistic,
                item.region,
                item.compartment_id,
                _stable_token(item),
            ),
        )
        warnings: list[OciCorrelationWarning] = []
        if inventory is not None:
            for link in links:
                action_type = link.action.resource_type
                if action_type and action_type != inventory.resource_type:
                    warnings.append(
                        OciCorrelationWarning(
                            category="resource_type_conflict",
                            message=(
                                "Inventory and Cloud Advisor report different resource types; "
                                "both values were preserved"
                            ),
                            resource_id=resource_id,
                            source="cloud_advisor",
                        )
                    )
        warnings = _stable_unique(warnings)
        correlation_warnings.extend(warnings)

        provenance: dict[str, tuple[str, ...]] = {}
        if inventory is not None:
            provenance["inventory"] = tuple(sorted(set(inventory.sources)))
        if links:
            provenance["advisor"] = ("oci_cloud_advisor",)
        if records or sku_records:
            provenance["usage"] = tuple(
                sorted({record.source for record in records + sku_records if record.source})
            )
        if resource_series or resource_id in metrics_by_resource:
            namespaces = {series.namespace for series in resource_series if series.namespace}
            provenance["monitoring"] = tuple(sorted(namespaces or {"oci_monitoring"}))

        contexts.append(
            OciResourceAnalysisContext(
                resource_id=resource_id,
                inventory=inventory,
                relationships=sorted(
                    relationships_by_resource.get(resource_id, []),
                    key=lambda item: (
                        item.relation_type,
                        item.source_id,
                        item.target_id,
                        item.source_type,
                        item.target_type,
                    ),
                ),
                native_recommendations=links,
                usage=OciResourceUsageContext(
                    records=records,
                    sku_usage_records=sku_records,
                    totals_by_currency=_totals_by_currency(records),
                    period_start=usage.period_start,
                    period_end=usage.period_end,
                ),
                monitoring=OciResourceMonitoringContext(
                    summary=metrics_by_resource.get(resource_id),
                    series=resource_series,
                    period_start=monitoring.period_start,
                    period_end=monitoring.period_end,
                    interval=monitoring.interval,
                ),
                coverage={
                    "inventory": _context_source_status(discovery),
                    "advisor": _context_source_status(advisor),
                    "usage": _context_source_status(usage),
                    "monitoring": _context_source_status(monitoring),
                },
                inventory_coverage={
                    resource_type: ("complete" if count is not None else "incomplete")
                    for resource_type, count in sorted(discovery.counts_by_type.items())
                },
                provenance=provenance,
                warnings=warnings,
            )
        )

    unallocated_recommendations = [
        item
        for item in recommendations
        if item.recommendation_id not in recommendation_ids_with_resource_action
    ]
    account_context = OciAccountAnalysisContext(
        recommendations=unallocated_recommendations,
        resource_actions_without_resource_id=actions_without_resource_id,
        usage_records_without_resource_id=usage_without_resource_id,
        sku_usage_records_without_resource_id=sku_usage_without_resource_id,
        metric_series_without_resource_id=series_without_resource_id,
    )

    unmatched = {
        "advisor": tuple(sorted(set(actions_by_resource) - inventory_ids)),
        "usage": tuple(
            sorted((set(usage_by_resource) | set(sku_usage_by_resource)) - inventory_ids)
        ),
        "monitoring": tuple(
            sorted((set(metrics_by_resource) | set(series_by_resource)) - inventory_ids)
        ),
    }
    coverage = {
        "inventory": _source_coverage(discovery),
        "advisor": _source_coverage(advisor),
        "usage": _source_coverage(usage),
        "monitoring": _source_coverage(monitoring),
    }
    source_results = {
        "inventory": discovery,
        "advisor": advisor,
        "usage": usage,
        "monitoring": monitoring,
    }
    statuses = {result.status for result in source_results.values()}
    status = (
        "success" if statuses == {"success"} else "failed" if statuses == {"failed"} else "partial"
    )

    return OciCorrelationResult(
        status=status,
        resource_contexts=contexts,
        account_context=account_context,
        unmatched_resource_ids_by_source=unmatched,
        coverage=coverage,
        source_warnings={
            source: tuple(sorted(result.warnings, key=_stable_token))
            for source, result in source_results.items()
        },
        source_errors={
            source: tuple(sorted(result.errors, key=_stable_token))
            for source, result in source_results.items()
        },
        warnings=_stable_unique(correlation_warnings),
        time_alignment=_time_alignment(usage, monitoring),
        source_freshness={source: result.completed_at for source, result in source_results.items()},
    )
