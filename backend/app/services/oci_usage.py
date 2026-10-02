from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

import oci

from app.services.oci_clients import (
    OciClientFactory,
    OciDiscoveryClientConfigurationError,
    OciPageFailure,
    classify_oci_failure,
    list_all_pages,
)
from app.services.oci_credentials import (
    OciCredentialResolutionError,
    resolve_oci_signing_credentials,
)
from app.services.oci_discovery_models import OciDiscoveryResult
from app.services.oci_discovery_operations import OciDiscoveryOperations, OciFatalDiscoveryAbort
from app.services.oci_scope import resolve_oci_discovery_scope
from app.services.oci_usage_models import OciUsageIssue, OciUsageRecord, OciUsageResult

logger = logging.getLogger(__name__)

MAX_DAILY_WINDOW_DAYS = 90
DEFAULT_COMPLETE_DAYS = 30
PRIMARY_GROUP_BY = ("resourceId", "service", "region", "compartmentId")
SKU_USAGE_GROUP_BY = ("resourceId", "service", "skuPartNumber", "unit")


def default_usage_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    end = current.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return end - timedelta(days=DEFAULT_COMPLETE_DAYS), end


def validate_usage_window(start_time: datetime, end_time: datetime) -> tuple[datetime, datetime]:
    if start_time.tzinfo is None or end_time.tzinfo is None:
        raise ValueError("OCI usage window must use timezone-aware timestamps")
    start = start_time.astimezone(UTC)
    end = end_time.astimezone(UTC)
    if end <= start:
        raise ValueError("OCI usage window end_time must be after start_time")
    if any((start.hour, start.minute, start.second, start.microsecond)):
        raise ValueError("OCI DAILY usage start_time must be aligned to UTC midnight")
    if any((end.hour, end.minute, end.second, end.microsecond)):
        raise ValueError("OCI DAILY usage end_time must be aligned to UTC midnight")
    if end - start > timedelta(days=MAX_DAILY_WINDOW_DAYS):
        raise ValueError("OCI DAILY usage window cannot exceed 90 days")
    return start, end


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _normalize_service(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "_")


class OciUsageService:
    """Read-only OCI Usage API acquisition layer. It never creates DeepOps findings."""

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
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        inventory: OciDiscoveryResult | None = None,
        now: datetime | None = None,
    ) -> OciUsageResult:
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        if start_time is None and end_time is None:
            period_start, period_end = default_usage_window(now)
        elif start_time is None or end_time is None:
            raise ValueError("start_time and end_time must be provided together")
        else:
            period_start, period_end = validate_usage_window(start_time, end_time)

        warnings: list[OciUsageIssue] = []
        errors: list[OciUsageIssue] = []
        coverage = {"scope": False, "resource_cost": False, "sku_usage": False}
        pages = {"resource_cost": 0, "sku_usage": 0}
        request_count = 0

        try:
            snapshot = self._credential_resolver(db, cloud_account_id)
            factory = self._client_factory_cls(snapshot)
        except OciCredentialResolutionError as exc:
            errors.append(
                OciUsageIssue(
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
                [],
                [],
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )
        except OciDiscoveryClientConfigurationError:
            errors.append(
                OciUsageIssue(
                    category="local_configuration_invalid",
                    source="usage_api",
                    operation="create_client",
                    message="OCI SDK rejected the local Usage API client configuration",
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                [],
                [],
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )

        scope_regions = tuple(dict.fromkeys(snapshot.scope_regions))
        scope_compartments = tuple(dict.fromkeys(snapshot.compartment_ocids))
        try:
            discovery_errors = []
            operations = OciDiscoveryOperations(snapshot, discovery_errors)
            scope = resolve_oci_discovery_scope(snapshot, factory, operations)
            scope_regions = scope.regions
            scope_compartments = scope.compartment_ids
            coverage["scope"] = scope.complete
            for issue in discovery_errors:
                warnings.append(
                    OciUsageIssue(
                        category=issue.category,
                        source="identity_api",
                        operation=issue.operation,
                        message=issue.message,
                        fatal=False,
                    )
                )
        except OciFatalDiscoveryAbort as exc:
            errors.append(
                OciUsageIssue(
                    category=exc.issue.category,
                    source="identity_api",
                    operation=exc.issue.operation,
                    message=exc.issue.message,
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                [],
                [],
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )

        inventory_ids = (
            {resource.resource_id for resource in inventory.resources}
            if inventory is not None
            else None
        )

        try:
            client = factory.usage(snapshot.region)
        except OciDiscoveryClientConfigurationError:
            errors.append(
                OciUsageIssue(
                    category="local_configuration_invalid",
                    source="usage_api",
                    operation="create_client",
                    message="OCI SDK rejected the local Usage API client configuration",
                    fatal=True,
                )
            )
            return self._result(
                "failed",
                period_start,
                period_end,
                [],
                [],
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )

        records: list[OciUsageRecord] = []
        sku_records: list[OciUsageRecord] = []

        primary, primary_pages, primary_ok, primary_fatal = self._query(
            client,
            snapshot.tenancy_ocid,
            period_start,
            period_end,
            PRIMARY_GROUP_BY,
            "resource_cost",
            errors,
        )
        request_count += max(primary_pages, 1)
        pages["resource_cost"] = primary_pages
        records = self._normalize(primary, scope_regions, scope_compartments, inventory_ids)
        coverage["resource_cost"] = primary_ok
        if primary_fatal:
            return self._result(
                "failed",
                period_start,
                period_end,
                records,
                [],
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )

        auxiliary, auxiliary_pages, auxiliary_ok, auxiliary_fatal = self._query(
            client,
            snapshot.tenancy_ocid,
            period_start,
            period_end,
            SKU_USAGE_GROUP_BY,
            "sku_usage",
            errors,
        )
        request_count += max(auxiliary_pages, 1)
        pages["sku_usage"] = auxiliary_pages
        sku_records = self._normalize(auxiliary, scope_regions, scope_compartments, inventory_ids)
        coverage["sku_usage"] = auxiliary_ok
        if auxiliary_fatal:
            return self._result(
                "failed",
                period_start,
                period_end,
                records,
                sku_records,
                warnings,
                errors,
                coverage,
                pages,
                request_count,
                started_at,
            )

        status = "success" if all(coverage.values()) and not errors else "partial"
        result = self._result(
            status,
            period_start,
            period_end,
            records,
            sku_records,
            warnings,
            errors,
            coverage,
            pages,
            request_count,
            started_at,
        )
        logger.info(
            "OCI usage cloud_account_id=%s provider=oci operation=request_summarized_usages "
            "period_start=%s period_end=%s records=%s pages=%s status=%s duration_ms=%s",
            cloud_account_id,
            period_start.isoformat(),
            period_end.isoformat(),
            len(records),
            sum(pages.values()),
            result.status,
            round((perf_counter() - started_perf) * 1000),
        )
        return result

    def _query(
        self,
        client,
        tenancy_ocid: str,
        start_time: datetime,
        end_time: datetime,
        group_by: tuple[str, ...],
        operation: str,
        errors: list[OciUsageIssue],
    ) -> tuple[list[Any], int, bool, bool]:
        if len(group_by) > 4:
            raise ValueError("OCI Usage API supports at most four groupBy dimensions")
        details = oci.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=tenancy_ocid,
            time_usage_started=start_time,
            time_usage_ended=end_time,
            granularity="DAILY",
            query_type="COST",
            group_by=list(group_by),
            is_aggregate_by_time=False,
        )
        try:
            page_result = list_all_pages(
                client.request_summarized_usages,
                details,
                item_extractor=lambda data: list(getattr(data, "items", []) or []),
            )
            return page_result.items, page_result.pages, True, False
        except OciPageFailure as exc:
            classification = classify_oci_failure(exc.cause)
            errors.append(
                OciUsageIssue(
                    category=classification.category,
                    source="usage_api",
                    operation=operation,
                    message=classification.message,
                    fatal=classification.authentication_fatal,
                )
            )
            return (
                exc.items,
                exc.pages,
                False,
                classification.authentication_fatal,
            )

    def _normalize(
        self,
        items: list[Any],
        scope_regions: tuple[str, ...],
        scope_compartments: tuple[str, ...],
        inventory_ids: set[str] | None,
    ) -> list[OciUsageRecord]:
        records: list[OciUsageRecord] = []
        seen: set[tuple[Any, ...]] = set()
        for item in items:
            resource_id = getattr(item, "resource_id", None)
            region = getattr(item, "region", None)
            compartment_id = getattr(item, "compartment_id", None)
            record = OciUsageRecord(
                start_time=getattr(item, "time_usage_started", None),
                end_time=getattr(item, "time_usage_ended", None),
                resource_id=resource_id,
                service=getattr(item, "service", None),
                region=region,
                compartment_id=compartment_id,
                sku_name=getattr(item, "sku_name", None),
                sku_part_number=getattr(item, "sku_part_number", None),
                unit=getattr(item, "unit", None),
                usage_quantity=_decimal(getattr(item, "computed_quantity", None)),
                actual_cost=_decimal(getattr(item, "computed_amount", None)),
                currency=getattr(item, "currency", None),
                scope_match=self._scope_match(
                    region, compartment_id, scope_regions, scope_compartments
                ),
                inventory_match=(
                    None
                    if resource_id is None or inventory_ids is None
                    else resource_id in inventory_ids
                ),
                native_metadata={
                    "service_normalized": _normalize_service(getattr(item, "service", None)),
                    "subscription_id": getattr(item, "subscription_id", None),
                    "resource_name": getattr(item, "resource_name", None),
                },
            )
            key = (
                record.start_time,
                record.end_time,
                record.resource_id,
                record.service,
                record.region,
                record.compartment_id,
                record.sku_name,
                record.sku_part_number,
                record.unit,
                record.currency,
                record.actual_cost,
                record.usage_quantity,
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
        return records

    @staticmethod
    def _scope_match(
        region: str | None,
        compartment_id: str | None,
        scope_regions: tuple[str, ...],
        scope_compartments: tuple[str, ...],
    ) -> str:
        if region is None or compartment_id is None:
            return "unknown"
        if not scope_regions or not scope_compartments:
            return "out"
        if region not in scope_regions or compartment_id not in scope_compartments:
            return "out"
        return "in"

    @staticmethod
    def _result(
        status: str,
        period_start: datetime,
        period_end: datetime,
        records: list[OciUsageRecord],
        sku_records: list[OciUsageRecord],
        warnings: list[OciUsageIssue],
        errors: list[OciUsageIssue],
        coverage: dict[str, bool],
        pages: dict[str, int],
        request_count: int,
        started_at: datetime,
    ) -> OciUsageResult:
        totals: dict[str, Decimal] = {}
        for record in records:
            if record.scope_match == "out" or record.actual_cost is None:
                continue
            if record.currency is None:
                continue
            totals[record.currency] = totals.get(record.currency, Decimal("0")) + record.actual_cost
        return OciUsageResult(
            status=status,
            period_start=period_start,
            period_end=period_end,
            records=records,
            sku_usage_records=sku_records,
            totals_by_currency=totals,
            warnings=warnings,
            errors=errors,
            coverage=coverage,
            pages=pages,
            request_count=request_count,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
