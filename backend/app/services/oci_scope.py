from __future__ import annotations

from collections import deque

from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory
from app.services.oci_discovery_models import OciDiscoveryScope
from app.services.oci_discovery_operations import OciDiscoveryOperations


def resolve_oci_discovery_scope(
    snapshot: OciConnectionSnapshot,
    factory: OciClientFactory,
    operations: OciDiscoveryOperations,
) -> OciDiscoveryScope:
    """Resolve only the persisted regions and compartment branches configured for the account."""
    regions = tuple(dict.fromkeys(region for region in snapshot.scope_regions if region))
    roots = list(dict.fromkeys(ocid for ocid in snapshot.compartment_ocids if ocid))
    if snapshot.include_root_compartment and snapshot.tenancy_ocid not in roots:
        roots.append(snapshot.tenancy_ocid)

    if not snapshot.include_subcompartments or not roots or not regions:
        return OciDiscoveryScope(
            regions=regions,
            compartment_ids=tuple(roots),
            include_root_compartment=snapshot.include_root_compartment,
            include_subcompartments=snapshot.include_subcompartments,
            complete=True,
        )

    identity = factory.identity(regions[0])
    resolved = list(roots)
    seen = set(roots)
    complete = True

    for root_id in roots:
        if root_id == snapshot.tenancy_ocid:
            items, ok = operations.paged(
                source="identity_api",
                operation="list_compartments",
                region=regions[0],
                compartment_id=root_id,
                call=identity.list_compartments,
                args=(root_id,),
                kwargs={
                    "access_level": "ACCESSIBLE",
                    "compartment_id_in_subtree": True,
                    "lifecycle_state": "ACTIVE",
                },
            )
            complete = complete and ok
            _append_new_compartments(items, resolved, seen)
            continue

        queue = deque([root_id])
        expanded: set[str] = set()
        while queue:
            parent_id = queue.popleft()
            if parent_id in expanded:
                continue
            expanded.add(parent_id)
            items, ok = operations.paged(
                source="identity_api",
                operation="list_compartments",
                region=regions[0],
                compartment_id=parent_id,
                call=identity.list_compartments,
                args=(parent_id,),
                kwargs={
                    "access_level": "ACCESSIBLE",
                    "lifecycle_state": "ACTIVE",
                },
            )
            complete = complete and ok
            for item in items:
                child_id = getattr(item, "id", None)
                if not child_id:
                    continue
                if child_id not in seen:
                    seen.add(child_id)
                    resolved.append(child_id)
                if child_id not in expanded:
                    queue.append(child_id)

    return OciDiscoveryScope(
        regions=regions,
        compartment_ids=tuple(resolved),
        include_root_compartment=snapshot.include_root_compartment,
        include_subcompartments=snapshot.include_subcompartments,
        complete=complete,
    )


def _append_new_compartments(items, resolved: list[str], seen: set[str]) -> None:
    for item in items:
        child_id = getattr(item, "id", None)
        if child_id and child_id not in seen:
            seen.add(child_id)
            resolved.append(child_id)
