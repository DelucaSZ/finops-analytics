from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

import oci

from app.services.oci_clients import (
    OciClientFactory,
    OciDiscoveryClientConfigurationError,
    classify_oci_failure,
)
from app.services.oci_credentials import (
    OciCredentialResolutionError,
    resolve_oci_signing_credentials,
)
from app.services.oci_discovery_models import OciDiscoveryResult
from app.services.oci_discovery_operations import OciDiscoveryOperations, OciFatalDiscoveryAbort
from app.services.oci_monitoring_models import (
    OciMetricDatapoint,
    OciMetricSeries,
    OciMonitoringIssue,
    OciMonitoringResult,
    OciResourceMetrics,
)
from app.services.oci_scope import resolve_oci_discovery_scope

logger = logging.getLogger(__name__)

COMPUTE_NAMESPACE = "oci_computeagent"
DEFAULT_MONITORING_DAYS = 30
DEFAULT_INTERVAL = "1h"
MAX_MONITORING_WINDOW_DAYS = 90

_QUERY_DEFINITIONS = (
    ("CpuUtilization", "mean"),
    ("CpuUtilization", "max"),
    ("MemoryUtilization", "mean"),
    ("MemoryUtilization", "max"),
    ("NetworksBytesIn", "increment"),
    ("NetworksBytesOut", "increment"),
)


def default_monitoring_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    end = current.astimezone(UTC)
    return end - timedelta(days=DEFAULT_MONITORING_DAYS), end


def validate_monitoring_window(
    start_time: datetime,
    end_time: datetime,
) -> tuple[datetime, datetime]:
    if start_time.tzinfo is None or end_time.tzinfo is None:
        raise ValueError("OCI Monitoring window must use timezone-aware timestamps")
    start = start_time.astimezone(UTC)
    end = end_time.astimezone(UTC)
    if end <= start:
        raise ValueError("OCI Monitoring window end_time must be after start_time")
    if end - start > timedelta(days=MAX_MONITORING_WINDOW_DAYS):
        raise ValueError("OCI Monitoring window cannot exceed 90 days")
    return start, end


def build_compute_query(metric_name: str, statistic: str, *, interval: str = DEFAULT_INTERVAL) -> str:
    allowed = set(_QUERY_DEFINITIONS)
    if (metric_name, statistic) not in allowed:
        raise ValueError("Unsupported OCI compute metric/statistic")
    if interval != DEFAULT_INTERVAL:
        raise ValueError("Unsupported OCI compute Monitoring interval")
    return f"{metric_name}[{interval}].groupBy(resourceId).{statistic}()"


def _unit(metric_data: Any) -> str | None:
    metadata = dict(getattr(metric_data, "metadata", {}) or {})
    value = metadata.get("unit")
    return str(value) if value is not None else None


def _safe_dimensions(metric_data: Any) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in dict(getattr(metric_data, "dimensions", {}) or {}).items()
        if key is not None and value is not None
    }


def _datapoints(metric_data: Any) -> list[OciMetricDatapoint]:
    normalized: list[OciMetricDatapoint] = []
    for item in list(getattr(metric_data, "aggregated_datapoints", []) or []):
        timestamp = getattr(item, "timestamp", None)
        value = getattr(item, "value", None)
        if timestamp is None or value is None:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = timestamp.astimezone(UTC)
        numeric = float(value)
        if not math.isfinite(numeric):
            continue
        normalized.append(OciMetricDatapoint(timestamp=timestamp, value=numeric))
    normalized.sort(key=lambda item: item.timestamp)
    return normalized


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _parse_resource_created_at(resource: Any) -> datetime | None:
    raw = dict(getattr(resource, "attributes", {}) or {}).get("time_created")
    if not raw:
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OciMonitoringService:
    """Read-only OCI Monitoring/MQL acquisition layer for Compute metrics."""

    def __init__(
        self,
        *,
        credential_resolver=resolve_oci_signing_credentials,
        client_factory_cls=OciClientFactory,
    ) -> None:
        self._credential_resolver = credential_resolver
        self._client_factory_cls = client_factory_cls

    def collect_account(
        self,
        db,
        cloud_account_id: int,
        *,
        inventory: OciDiscoveryResult | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        now: datetime | None = None,
    ) -> OciMonitoringResult:
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        if start_time is None and end_time is None:
            period_start, period_end = default_monitoring_window(now)
        elif start_time is None or end_time is None:
            raise ValueError("start_time and end_time must be provided together")
        else:
            period_start, period_end = validate_monitoring_window(start_time, end_time)

        warnings: list[OciMonitoringIssue] = []
        errors: list[OciMonitoringIssue] = []
        coverage = {
            "scope": False,
            "cpu": False,
            "memory": False,
            "network_in": False,
            "network_out": False,
        }
        series: list[OciMetricSeries] = []
        request_count = 0

        try:
            snapshot = self._credential_resolver(db, cloud_account_id)
            factory = self._client_factory_cls(snapshot)
        except OciCredentialResolutionError as exc:
            errors.append(
                OciMonitoringIssue(
                    category=exc.internal_code or exc.code,
                    source="credentials",
                    operation="resolve",
                    message=exc.safe_message,
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                series,
                [],
                [],
                warnings,
                errors,
                coverage,
                request_count,
                started_at,
            )
        except OciDiscoveryClientConfigurationError:
            errors.append(
                OciMonitoringIssue(
                    category="local_configuration_invalid",
                    source="monitoring_api",
                    operation="create_client",
                    message="OCI SDK rejected the local Monitoring client configuration",
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                series,
                [],
                [],
                warnings,
                errors,
                coverage,
                request_count,
                started_at,
            )

        try:
            scope_errors = []
            operations = OciDiscoveryOperations(snapshot, scope_errors)
            scope = resolve_oci_discovery_scope(snapshot, factory, operations)
            coverage["scope"] = scope.complete
            for issue in scope_errors:
                warnings.append(
                    OciMonitoringIssue(
                        category=issue.category,
                        source="identity_api",
                        operation=issue.operation,
                        message=issue.message,
                        region=issue.region,
                        compartment_id=issue.compartment_id,
                    )
                )
        except OciFatalDiscoveryAbort as exc:
            issue = exc.issue
            errors.append(
                OciMonitoringIssue(
                    category=issue.category,
                    source="identity_api",
                    operation=issue.operation,
                    message=issue.message,
                    region=issue.region,
                    compartment_id=issue.compartment_id,
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                series,
                [],
                [],
                warnings,
                errors,
                coverage,
                request_count,
                started_at,
            )

        inventory_by_id = self._inventory_index(inventory)
        metric_success = defaultdict(lambda: True)
        fatal = False

        for region in scope.regions:
            try:
                client = factory.monitoring(region)
            except OciDiscoveryClientConfigurationError:
                errors.append(
                    OciMonitoringIssue(
                        category="local_configuration_invalid",
                        source="monitoring_api",
                        operation="create_client",
                        message="OCI SDK rejected the local Monitoring client configuration",
                        region=region,
                        fatal=True,
                    )
                )
                fatal = True
                break

            for compartment_id in scope.compartment_ids:
                for metric_name, statistic in _QUERY_DEFINITIONS:
                    metric_key = self._coverage_key(metric_name)
                    request_count += 1
                    collected, ok, auth_fatal = self._query(
                        client=client,
                        region=region,
                        compartment_id=compartment_id,
                        metric_name=metric_name,
                        statistic=statistic,
                        period_start=period_start,
                        period_end=period_end,
                        inventory_by_id=inventory_by_id,
                        errors=errors,
                    )
                    series.extend(collected)
                    metric_success[metric_key] = metric_success[metric_key] and ok
                    if auth_fatal:
                        fatal = True
                        break
                if fatal:
                    break
            if fatal:
                break

        coverage["cpu"] = bool(metric_success["cpu"]) if request_count else False
        coverage["memory"] = bool(metric_success["memory"]) if request_count else False
        coverage["network_in"] = bool(metric_success["network_in"]) if request_count else False
        coverage["network_out"] = bool(metric_success["network_out"]) if request_count else False

        resources = self._aggregate_resources(
            inventory,
            series,
            period_start=period_start,
            query_coverage=coverage,
        )
        orphan_series = [item for item in series if item.inventory_match is False]
        status = (
            "failed"
            if fatal
            else ("success" if all(coverage.values()) and not errors else "partial")
        )
        result = self._result(
            status,
            period_start,
            period_end,
            series,
            resources,
            orphan_series,
            warnings,
            errors,
            coverage,
            request_count,
            started_at,
        )
        logger.info(
            "OCI monitoring cloud_account_id=%s provider=oci namespace=%s "
            "period_start=%s period_end=%s interval=%s series_count=%s resource_count=%s "
            "requests=%s status=%s duration_ms=%s",
            cloud_account_id,
            COMPUTE_NAMESPACE,
            period_start.isoformat(),
            period_end.isoformat(),
            DEFAULT_INTERVAL,
            len(series),
            len(resources),
            request_count,
            result.status,
            round((perf_counter() - started_perf) * 1000),
        )
        return result

    def _query(
        self,
        *,
        client,
        region: str,
        compartment_id: str,
        metric_name: str,
        statistic: str,
        period_start: datetime,
        period_end: datetime,
        inventory_by_id: dict[str, Any] | None,
        errors: list[OciMonitoringIssue],
    ) -> tuple[list[OciMetricSeries], bool, bool]:
        query = build_compute_query(metric_name, statistic)
        details = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace=COMPUTE_NAMESPACE,
            query=query,
            start_time=period_start,
            end_time=period_end,
        )
        try:
            response = client.summarize_metrics_data(
                compartment_id,
                details,
            )
        except Exception as exc:
            classification = classify_oci_failure(exc)
            errors.append(
                OciMonitoringIssue(
                    category=classification.category,
                    source="monitoring_api",
                    operation="summarize_metrics_data",
                    message=classification.message,
                    region=region,
                    compartment_id=compartment_id,
                    metric_name=metric_name,
                    fatal=classification.authentication_fatal,
                )
            )
            return [], False, classification.authentication_fatal

        normalized: list[OciMetricSeries] = []
        for item in list(getattr(response, "data", []) or []):
            dimensions = _safe_dimensions(item)
            resource_id = dimensions.get("resourceId")
            points = _datapoints(item)
            normalized.append(
                OciMetricSeries(
                    namespace=str(
                        getattr(item, "namespace", COMPUTE_NAMESPACE) or COMPUTE_NAMESPACE
                    ),
                    metric_name=str(getattr(item, "name", metric_name) or metric_name),
                    resource_id=resource_id,
                    region=region,
                    compartment_id=str(
                        getattr(item, "compartment_id", compartment_id) or compartment_id
                    ),
                    dimensions=dimensions,
                    unit=_unit(item),
                    period_start=period_start,
                    period_end=period_end,
                    statistic=statistic,
                    interval=DEFAULT_INTERVAL,
                    datapoints=points,
                    coverage="available" if points else "no_datapoints",
                    inventory_match=(
                        None
                        if resource_id is None or inventory_by_id is None
                        else resource_id in inventory_by_id
                    ),
                )
            )
        return normalized, True, False

    @staticmethod
    def _coverage_key(metric_name: str) -> str:
        if metric_name == "CpuUtilization":
            return "cpu"
        if metric_name == "MemoryUtilization":
            return "memory"
        if metric_name == "NetworksBytesIn":
            return "network_in"
        if metric_name == "NetworksBytesOut":
            return "network_out"
        raise ValueError("Unknown OCI Monitoring metric")

    @staticmethod
    def _inventory_index(inventory: OciDiscoveryResult | None) -> dict[str, Any] | None:
        if inventory is None:
            return None
        return {
            resource.resource_id: resource
            for resource in inventory.resources
            if resource.resource_type == "compute_instance"
        }

    def _aggregate_resources(
        self,
        inventory: OciDiscoveryResult | None,
        series: list[OciMetricSeries],
        *,
        period_start: datetime,
        query_coverage: dict[str, bool],
    ) -> list[OciResourceMetrics]:
        inventory_by_id = self._inventory_index(inventory) or {}
        grouped: dict[str, list[OciMetricSeries]] = defaultdict(list)
        for item in series:
            if item.resource_id:
                grouped[item.resource_id].append(item)

        results: list[OciResourceMetrics] = []
        for resource_id, resource in inventory_by_id.items():
            resource_series = grouped.get(resource_id, [])
            metric_map = {
                (item.metric_name, item.statistic): item
                for item in resource_series
                if item.datapoints
            }
            cpu_mean_values = self._values(metric_map.get(("CpuUtilization", "mean")))
            cpu_max_values = self._values(metric_map.get(("CpuUtilization", "max")))
            memory_mean_values = self._values(metric_map.get(("MemoryUtilization", "mean")))
            memory_max_values = self._values(metric_map.get(("MemoryUtilization", "max")))
            network_in_values = self._values(metric_map.get(("NetworksBytesIn", "increment")))
            network_out_values = self._values(metric_map.get(("NetworksBytesOut", "increment")))

            missing = []
            if not cpu_mean_values:
                missing.append("cpu")
            if not memory_mean_values:
                missing.append("memory")
            if not network_in_values:
                missing.append("network_in")
            if not network_out_values:
                missing.append("network_out")

            reasons = []
            created_at = _parse_resource_created_at(resource)
            if created_at is not None and created_at > period_start:
                reasons.append("resource_created_within_window")
            lifecycle = getattr(resource, "lifecycle_state", None)
            if str(lifecycle or "").upper() == "STOPPED" and "cpu" in missing:
                reasons.append("resource_not_running")
            for key in ("cpu", "memory", "network_in", "network_out"):
                if not query_coverage.get(key, False):
                    reasons.append(f"{key}_query_incomplete")

            metrics_available = bool(resource_series)
            if not metrics_available:
                resource_coverage = "unavailable"
            elif missing or reasons:
                resource_coverage = "partial"
            else:
                resource_coverage = "complete"

            results.append(
                OciResourceMetrics(
                    resource_id=resource_id,
                    region=getattr(resource, "region", None),
                    compartment_id=getattr(resource, "compartment_id", None),
                    lifecycle_state=lifecycle,
                    resource_created_at=created_at,
                    cpu_mean=_mean(cpu_mean_values),
                    cpu_p95=_percentile(cpu_mean_values, 0.95),
                    cpu_max=max(cpu_max_values) if cpu_max_values else None,
                    memory_mean=_mean(memory_mean_values),
                    memory_p95=_percentile(memory_mean_values, 0.95),
                    memory_max=max(memory_max_values) if memory_max_values else None,
                    network_in_total_bytes=sum(network_in_values) if network_in_values else None,
                    network_out_total_bytes=(
                        sum(network_out_values) if network_out_values else None
                    ),
                    sample_counts={
                        "cpu_mean": len(cpu_mean_values),
                        "cpu_max": len(cpu_max_values),
                        "memory_mean": len(memory_mean_values),
                        "memory_max": len(memory_max_values),
                        "network_in_increment": len(network_in_values),
                        "network_out_increment": len(network_out_values),
                    },
                    missing_metrics=missing,
                    coverage=resource_coverage,
                    coverage_reasons=sorted(set(reasons)),
                    metrics_available=metrics_available,
                )
            )
        return results

    @staticmethod
    def _values(series: OciMetricSeries | None) -> list[float]:
        if series is None:
            return []
        return [point.value for point in series.datapoints]

    @staticmethod
    def _result(
        status: str,
        period_start: datetime,
        period_end: datetime,
        series: list[OciMetricSeries],
        resources: list[OciResourceMetrics],
        orphan_series: list[OciMetricSeries],
        warnings: list[OciMonitoringIssue],
        errors: list[OciMonitoringIssue],
        coverage: dict[str, bool],
        request_count: int,
        started_at: datetime,
    ) -> OciMonitoringResult:
        return OciMonitoringResult(
            status=status,
            period_start=period_start,
            period_end=period_end,
            interval=DEFAULT_INTERVAL,
            series=series,
            resources=resources,
            orphan_series=orphan_series,
            warnings=warnings,
            errors=errors,
            coverage=coverage,
            request_count=request_count,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
