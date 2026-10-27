"""Pure adapter from the existing OCI discovery dataset to the transversal Inventory domain."""

from __future__ import annotations

from copy import deepcopy

from app.core.inventory import (
    DiscoveredInventoryResource,
    InventoryCoverage,
    InventoryCoverageStatus,
    InventoryDiscoveryIssue,
    InventoryDiscoveryResult,
)
from app.services.oci_discovery_models import WAVE1_RESOURCE_TYPES, OciDiscoveryResult

_OCI_SERVICE_BY_TYPE = {
    "compute_instance": "Compute",
    "block_volume": "Block Storage",
    "boot_volume": "Block Storage",
    "public_ip": "Networking",
}


def normalize_oci_lifecycle_status(native_status: str | None) -> str:
    value = str(native_status or "").strip().upper()
    mapping = {
        "RUNNING": "running",
        "ACTIVE": "running",
        "AVAILABLE": "available",
        "ASSIGNED": "associated",
        "UNASSIGNED": "available",
        "PROVISIONING": "creating",
        "CREATING": "creating",
        "STARTING": "starting",
        "STOPPING": "stopping",
        "STOPPED": "stopped",
        "TERMINATING": "terminating",
        "TERMINATED": "terminated",
        "DELETING": "deleting",
        "DELETED": "deleted",
        "RESTORING": "creating",
        "FAULTY": "error",
        "FAILED": "error",
        "INACTIVE": "stopped",
    }
    return mapping.get(value, "unknown")


def _issue_from_oci(issue) -> InventoryDiscoveryIssue:
    category = str(getattr(issue, "category", None) or "provider_error")
    source = str(getattr(issue, "source", None) or "oci")
    operation = str(getattr(issue, "operation", None) or "discovery")
    return InventoryDiscoveryIssue(
        provider="oci",
        resource_type=getattr(issue, "resource_type", None),
        region=getattr(issue, "region", None),
        category=category,
        code=source,
        # Keep this sanitized and deterministic; provider SDK exception payloads are not copied.
        message=f"OCI {source}/{operation} inventory discovery issue ({category})",
    )


def _issue_matches_scope(issue, resource_type: str, region: str | None) -> bool:
    issue_type = getattr(issue, "resource_type", None)
    issue_region = getattr(issue, "region", None)
    if issue_type and str(issue_type) != resource_type:
        return False
    if issue_region and region and str(issue_region) != region:
        return False
    if issue_region and region is None:
        return False
    return True


def adapt_oci_inventory(
    discovery: OciDiscoveryResult,
    *,
    cloud_account_id: int,
) -> InventoryDiscoveryResult:
    """Adapt one already-executed OCI discovery result; never performs provider I/O."""

    resources: list[DiscoveredInventoryResource] = []
    for resource in discovery.resources:
        attributes = deepcopy(resource.attributes)
        if resource.compartment_id:
            attributes["compartment_id"] = resource.compartment_id
        if resource.sources:
            attributes["sources"] = list(resource.sources)

        tags = {
            "freeform": deepcopy(resource.freeform_tags),
            "defined": deepcopy(resource.defined_tags),
        }
        resources.append(
            DiscoveredInventoryResource(
                provider="oci",
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                native_resource_type=resource.resource_type,
                service=_OCI_SERVICE_BY_TYPE.get(resource.resource_type),
                name=resource.name,
                region=resource.region,
                availability_zone=resource.availability_domain,
                lifecycle_status=normalize_oci_lifecycle_status(resource.lifecycle_state),
                native_status=resource.lifecycle_state,
                tags=tags,
                attributes=attributes,
            )
        )

    coverage: list[InventoryCoverage] = []
    regions = tuple(discovery.regions_scanned) or (None,)
    for resource_type in WAVE1_RESOURCE_TYPES:
        aggregate_complete = discovery.counts_by_type.get(resource_type) is not None
        observed_count = int(discovery.observed_counts_by_type.get(resource_type, 0) or 0)
        for region in regions:
            if aggregate_complete:
                status = InventoryCoverageStatus.COMPLETE
                code = None
                message = None
            else:
                matching_errors = [
                    issue
                    for issue in discovery.errors
                    if _issue_matches_scope(issue, resource_type, region)
                ]
                if discovery.status == "failed" or (matching_errors and observed_count == 0):
                    status = InventoryCoverageStatus.FAILED
                else:
                    status = InventoryCoverageStatus.PARTIAL
                first = matching_errors[0] if matching_errors else None
                code = str(getattr(first, "category", None) or "incomplete_scope")
                message = f"OCI {resource_type} discovery scope is {status.value}"

            coverage.append(
                InventoryCoverage(
                    provider="oci",
                    cloud_account_id=cloud_account_id,
                    resource_type=resource_type,
                    region=region,
                    status=status,
                    error_code=code,
                    error_message=message,
                )
            )

    return InventoryDiscoveryResult(
        resources=tuple(resources),
        coverage=tuple(coverage),
        warnings=tuple(_issue_from_oci(issue) for issue in discovery.warnings),
        errors=tuple(_issue_from_oci(issue) for issue in discovery.errors),
    )
