from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import oci
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider
from app.services.oci_auth import OciConnectionError, OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory, OciDiscoveryClientConfigurationError
from app.services.oci_credentials import resolve_oci_signing_credentials
from app.services.oci_discovery_models import (
    WAVE1_RESOURCE_TYPES,
    OciDiscoveredResource,
    OciDiscoveryIssue,
    OciDiscoveryResult,
    OciResourceRelationship,
)
from app.services.oci_discovery_operations import (
    OciDiscoveryOperations,
    OciFatalDiscoveryAbort,
)
from app.services.oci_inventory import OciWave1InventoryResult, collect_wave1_inventory
from app.services.oci_scope import resolve_oci_discovery_scope

_SEARCH_TYPE_MAP = {
    "instance": "compute_instance",
    "computeinstance": "compute_instance",
    "volume": "block_volume",
    "blockvolume": "block_volume",
    "bootvolume": "boot_volume",
    "publicip": "public_ip",
}
_SERVICE_SOURCES = {"compute_api", "block_storage_api", "virtual_network_api"}


def _now() -> datetime:
    return datetime.now(UTC)


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _tags(value: Any) -> dict:
    return dict(value or {})


def _normalize_search_type(value: Any) -> str:
    native = str(value or "").strip()
    token = re.sub(r"[^a-z0-9]", "", native.lower())
    return _SEARCH_TYPE_MAP.get(token, "oci_resource")


def _search_items(data: Any) -> list[Any]:
    return list(getattr(data, "items", []) or [])


class OciDiscoveryService:
    """Read-only OCI Discovery/Inventory layer. It is intentionally not a scan executor."""

    def __init__(
        self,
        *,
        credential_resolver: Callable[[Session, int], OciConnectionSnapshot] | None = None,
        client_factory_cls: type[OciClientFactory] = OciClientFactory,
    ) -> None:
        self._credential_resolver = credential_resolver or resolve_oci_signing_credentials
        self._client_factory_cls = client_factory_cls

    def discover_account(self, db: Session, cloud_account_id: int) -> OciDiscoveryResult:
        started_at = _now()
        try:
            snapshot = self._credential_resolver(db, cloud_account_id)
        except OciConnectionError as exc:
            return self._failed_result(
                started_at,
                [
                    OciDiscoveryIssue(
                        category=exc.internal_code or exc.code,
                        source="credentials",
                        operation="resolve_signing_credentials",
                        message=exc.safe_message,
                        fatal=True,
                    )
                ],
            )
        except Exception:
            return self._failed_result(
                started_at,
                [
                    OciDiscoveryIssue(
                        category="credential_resolution_failed",
                        source="credentials",
                        operation="resolve_signing_credentials",
                        message="OCI signing credentials could not be resolved",
                        fatal=True,
                    )
                ],
            )
        return self.discover(snapshot, started_at=started_at)

    def discover(
        self,
        snapshot: OciConnectionSnapshot,
        *,
        started_at: datetime | None = None,
    ) -> OciDiscoveryResult:
        started_at = started_at or _now()
        resources: dict[str, OciDiscoveredResource] = {}
        warnings: list[OciDiscoveryIssue] = []
        errors: list[OciDiscoveryIssue] = []
        operations = OciDiscoveryOperations(snapshot, errors)
        search_ids: set[str] = set()
        search_complete = True
        inventory = OciWave1InventoryResult()
        regions = tuple(snapshot.scope_regions)
        compartments: tuple[str, ...] = ()

        try:
            factory = self._client_factory_cls(snapshot)
            scope = resolve_oci_discovery_scope(snapshot, factory, operations)
            regions = scope.regions
            compartments = scope.compartment_ids

            if scope.regions and scope.compartment_ids:
                search_complete = self._discover_search(
                    snapshot,
                    factory,
                    operations,
                    scope.regions,
                    scope.compartment_ids,
                    resources,
                    search_ids,
                )
                inventory = collect_wave1_inventory(
                    snapshot,
                    factory,
                    scope,
                    operations,
                    resources,
                    lambda resource, authoritative: self._upsert(
                        resources,
                        resource,
                        authoritative=authoritative,
                    ),
                )

            self._add_consistency_warnings(
                resources,
                search_ids=search_ids,
                service_ids=inventory.service_ids,
                coverage=inventory.coverage,
                search_complete=search_complete,
                lifecycle_conflicts=inventory.lifecycle_conflicts,
                warnings=warnings,
            )
        except OciFatalDiscoveryAbort as exc:
            errors.append(exc.issue)
            return self._build_result(
                status="failed",
                resources=resources,
                relationships=inventory.relationships,
                regions=regions,
                compartments=compartments,
                coverage={resource_type: False for resource_type in WAVE1_RESOURCE_TYPES},
                warnings=warnings,
                errors=errors,
                started_at=started_at,
            )
        except OciDiscoveryClientConfigurationError:
            errors.append(
                OciDiscoveryIssue(
                    category="local_configuration_invalid",
                    source="client_factory",
                    operation="build_client",
                    message="OCI signing configuration is invalid for discovery",
                    fatal=True,
                )
            )
            return self._build_result(
                status="failed",
                resources=resources,
                relationships=inventory.relationships,
                regions=regions,
                compartments=compartments,
                coverage={resource_type: False for resource_type in WAVE1_RESOURCE_TYPES},
                warnings=warnings,
                errors=errors,
                started_at=started_at,
            )

        return self._build_result(
            status="partial" if errors else "success",
            resources=resources,
            relationships=inventory.relationships,
            regions=regions,
            compartments=compartments,
            coverage=inventory.coverage,
            warnings=warnings,
            errors=errors,
            started_at=started_at,
        )

    def _discover_search(
        self,
        snapshot: OciConnectionSnapshot,
        factory: OciClientFactory,
        operations: OciDiscoveryOperations,
        regions: tuple[str, ...],
        compartment_ids: tuple[str, ...],
        resources: dict[str, OciDiscoveredResource],
        search_ids: set[str],
    ) -> bool:
        region = regions[0]
        client = factory.resource_search(region)
        details = oci.resource_search.models.StructuredSearchDetails(query="query all resources")
        items, complete = operations.paged(
            source="resource_search",
            operation="search_resources",
            region=region,
            compartment_id=None,
            call=client.search_resources,
            kwargs={
                "search_details": details,
                "tenant_id": snapshot.tenancy_ocid,
            },
            item_extractor=_search_items,
        )
        allowed_regions = set(regions)
        allowed_compartments = set(compartment_ids)
        for item in items:
            item_region = getattr(item, "region", None)
            compartment_id = getattr(item, "compartment_id", None)
            if item_region and item_region not in allowed_regions:
                continue
            if compartment_id not in allowed_compartments:
                continue
            resource = self._search_resource(item)
            if resource is None:
                continue
            search_ids.add(resource.resource_id)
            self._upsert(resources, resource, authoritative=False)
        return complete

    @staticmethod
    def _failed_result(
        started_at: datetime,
        errors: list[OciDiscoveryIssue],
    ) -> OciDiscoveryResult:
        return OciDiscoveryResult(
            status="failed",
            resources=[],
            relationships=[],
            regions_scanned=(),
            compartments_scanned=(),
            observed_counts_by_type={},
            counts_by_type={resource_type: None for resource_type in WAVE1_RESOURCE_TYPES},
            warnings=[],
            errors=errors,
            started_at=started_at,
            completed_at=_now(),
        )

    @staticmethod
    def _build_result(
        *,
        status: str,
        resources: dict[str, OciDiscoveredResource],
        relationships: set[tuple[str, str, str, str, str]],
        regions: tuple[str, ...],
        compartments: tuple[str, ...],
        coverage: dict[str, bool],
        warnings: list[OciDiscoveryIssue],
        errors: list[OciDiscoveryIssue],
        started_at: datetime,
    ) -> OciDiscoveryResult:
        ordered_resources = sorted(resources.values(), key=lambda item: item.resource_id)
        observed: dict[str, int] = defaultdict(int)
        for resource in ordered_resources:
            observed[resource.resource_type] += 1
        counts = {
            resource_type: observed.get(resource_type, 0) if coverage[resource_type] else None
            for resource_type in WAVE1_RESOURCE_TYPES
        }
        ordered_relationships = [
            OciResourceRelationship(*relationship) for relationship in sorted(relationships)
        ]
        return OciDiscoveryResult(
            status=status,
            resources=ordered_resources,
            relationships=ordered_relationships,
            regions_scanned=regions,
            compartments_scanned=compartments,
            observed_counts_by_type=dict(observed),
            counts_by_type=counts,
            warnings=warnings,
            errors=errors,
            started_at=started_at,
            completed_at=_now(),
        )

    @staticmethod
    def _search_resource(item: Any) -> OciDiscoveredResource | None:
        resource_id = getattr(item, "identifier", None)
        if not resource_id:
            return None
        native_type = str(getattr(item, "resource_type", "") or "")
        attributes: dict[str, Any] = {"native_resource_type": native_type}
        time_created = _as_iso(getattr(item, "time_created", None))
        if time_created:
            attributes["time_created"] = time_created
        return OciDiscoveredResource(
            provider=CloudProvider.OCI.value,
            resource_id=resource_id,
            resource_type=_normalize_search_type(native_type),
            name=getattr(item, "display_name", None),
            region=getattr(item, "region", None),
            compartment_id=getattr(item, "compartment_id", None),
            lifecycle_state=getattr(item, "lifecycle_state", None),
            availability_domain=getattr(item, "availability_domain", None),
            freeform_tags=_tags(getattr(item, "freeform_tags", None)),
            defined_tags=_tags(getattr(item, "defined_tags", None)),
            sources=["resource_search"],
            attributes=attributes,
        )

    @staticmethod
    def _upsert(
        resources: dict[str, OciDiscoveredResource],
        incoming: OciDiscoveredResource,
        *,
        authoritative: bool,
    ) -> int:
        existing = resources.get(incoming.resource_id)
        if existing is None:
            resources[incoming.resource_id] = incoming
            return 0

        for source in incoming.sources:
            if source not in existing.sources:
                existing.sources.append(source)
        if not authoritative:
            return 0

        conflict = 0
        if (
            existing.lifecycle_state
            and incoming.lifecycle_state
            and existing.lifecycle_state != incoming.lifecycle_state
            and "resource_search" in existing.sources
        ):
            existing.attributes["search_lifecycle_state"] = existing.lifecycle_state
            existing.attributes["discovery_state_conflict"] = True
            conflict = 1

        existing.resource_type = incoming.resource_type
        for field_name in (
            "name",
            "region",
            "compartment_id",
            "lifecycle_state",
            "availability_domain",
        ):
            value = getattr(incoming, field_name)
            if value is not None:
                setattr(existing, field_name, value)
        existing.freeform_tags = incoming.freeform_tags
        existing.defined_tags = incoming.defined_tags
        existing.attributes.update(incoming.attributes)
        return conflict

    @staticmethod
    def _add_consistency_warnings(
        resources: dict[str, OciDiscoveredResource],
        *,
        search_ids: set[str],
        service_ids: dict[str, set[str]],
        coverage: dict[str, bool],
        search_complete: bool,
        lifecycle_conflicts: int,
        warnings: list[OciDiscoveryIssue],
    ) -> None:
        if search_complete:
            for resource_type in WAVE1_RESOURCE_TYPES:
                if not coverage[resource_type]:
                    continue
                typed_service_ids = service_ids.get(resource_type, set())
                service_only = typed_service_ids - search_ids
                search_only = {
                    resource.resource_id
                    for resource in resources.values()
                    if resource.resource_type == resource_type
                    and "resource_search" in resource.sources
                    and not (_SERVICE_SOURCES & set(resource.sources))
                }
                for resource_id in service_only:
                    resources[resource_id].attributes["discovery_consistency"] = "service_only"
                for resource_id in search_only:
                    resources[resource_id].attributes["discovery_consistency"] = "search_only"
                if service_only:
                    warnings.append(
                        OciDiscoveryIssue(
                            category="search_eventual_consistency",
                            source="resource_search",
                            operation="reconcile_with_service_api",
                            message=(
                                f"{len(service_only)} {resource_type} resources were returned by "
                                "the service API but were not present in Resource Search"
                            ),
                            resource_type=resource_type,
                        )
                    )
                if search_only:
                    warnings.append(
                        OciDiscoveryIssue(
                            category="search_eventual_consistency",
                            source="resource_search",
                            operation="reconcile_with_service_api",
                            message=(
                                f"{len(search_only)} {resource_type} resources were present in "
                                "Resource Search but were not confirmed by the service API"
                            ),
                            resource_type=resource_type,
                        )
                    )

        if lifecycle_conflicts:
            warnings.append(
                OciDiscoveryIssue(
                    category="search_service_state_conflict",
                    source="resource_search",
                    operation="reconcile_with_service_api",
                    message=(
                        f"{lifecycle_conflicts} resources had lifecycle state differences; "
                        "service API values were retained"
                    ),
                )
            )
