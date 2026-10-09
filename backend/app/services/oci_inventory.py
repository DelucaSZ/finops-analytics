from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.cloud import CloudProvider
from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory
from app.services.oci_discovery_models import (
    WAVE1_RESOURCE_TYPES,
    OciDiscoveredResource,
    OciDiscoveryScope,
)
from app.services.oci_discovery_operations import OciDiscoveryOperations
from app.services.oci_os import OciImageOperatingSystemResolver

RelationshipTuple = tuple[str, str, str, str, str]
UpsertResource = Callable[[OciDiscoveredResource, bool], int]


@dataclass
class OciWave1InventoryResult:
    relationships: set[RelationshipTuple] = field(default_factory=set)
    service_ids: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    coverage: dict[str, bool] = field(
        default_factory=lambda: {resource_type: True for resource_type in WAVE1_RESOURCE_TYPES}
    )
    lifecycle_conflicts: int = 0


def collect_wave1_inventory(
    snapshot: OciConnectionSnapshot,
    factory: OciClientFactory,
    scope: OciDiscoveryScope,
    operations: OciDiscoveryOperations,
    resources: dict[str, OciDiscoveredResource],
    upsert: UpsertResource,
) -> OciWave1InventoryResult:
    result = OciWave1InventoryResult()
    os_resolver = OciImageOperatingSystemResolver()

    for region in scope.regions:
        availability_domains, ad_complete = _availability_domains(
            snapshot,
            factory,
            operations,
            region,
        )
        observed_ads: set[str] = set()

        for compartment_id in scope.compartment_ids:
            instances, ok = _list_instances(factory, operations, region, compartment_id)
            if not ok:
                result.coverage["compute_instance"] = False
            for item in instances:
                resource = _compute_resource(item, region)
                if resource is None:
                    continue
                _enrich_compute_operating_system(
                    snapshot,
                    factory,
                    resource,
                    item,
                    region,
                    os_resolver,
                )
                result.lifecycle_conflicts += upsert(resource, True)
                result.service_ids["compute_instance"].add(resource.resource_id)
                if resource.availability_domain:
                    observed_ads.add(resource.availability_domain)

            volumes, ok = _list_block_volumes(factory, operations, region, compartment_id)
            if not ok:
                result.coverage["block_volume"] = False
            block_ids: list[str] = []
            for item in volumes:
                resource = _block_volume_resource(item, region)
                if resource is None:
                    continue
                result.lifecycle_conflicts += upsert(resource, True)
                result.service_ids["block_volume"].add(resource.resource_id)
                block_ids.append(resource.resource_id)
                if resource.availability_domain:
                    observed_ads.add(resource.availability_domain)

            boot_volumes, ok = _list_boot_volumes(factory, operations, region, compartment_id)
            if not ok:
                result.coverage["boot_volume"] = False
            boot_ids_by_ad: dict[str, list[str]] = defaultdict(list)
            for item in boot_volumes:
                resource = _boot_volume_resource(item, region)
                if resource is None:
                    continue
                result.lifecycle_conflicts += upsert(resource, True)
                result.service_ids["boot_volume"].add(resource.resource_id)
                availability_domain = resource.availability_domain
                if availability_domain:
                    observed_ads.add(availability_domain)
                    boot_ids_by_ad[availability_domain].append(resource.resource_id)

            _correlate_block_volume_attachments(
                factory,
                operations,
                region,
                compartment_id,
                block_ids,
                resources,
                result.relationships,
            )
            _correlate_boot_volume_attachments(
                factory,
                operations,
                region,
                compartment_id,
                boot_ids_by_ad,
                resources,
                result.relationships,
            )

        public_ip_ads = set(availability_domains)
        public_ip_ads.update(observed_ads)
        if not ad_complete:
            result.coverage["public_ip"] = False

        for compartment_id in scope.compartment_ids:
            public_ips, complete = _list_public_ips(
                factory,
                operations,
                region,
                compartment_id,
                sorted(public_ip_ads),
            )
            if not complete:
                result.coverage["public_ip"] = False
            for item in public_ips:
                resource = _public_ip_resource(item, region)
                if resource is None:
                    continue
                result.lifecycle_conflicts += upsert(resource, True)
                result.service_ids["public_ip"].add(resource.resource_id)
                assigned_entity_id = resource.attributes.get("assigned_entity_id")
                if assigned_entity_id:
                    result.relationships.add(
                        (
                            "public_ip_assignment",
                            resource.resource_id,
                            str(assigned_entity_id),
                            "public_ip",
                            str(
                                resource.attributes.get("assigned_entity_type") or "entity"
                            ).lower(),
                        )
                    )

    if not scope.complete:
        for resource_type in WAVE1_RESOURCE_TYPES:
            result.coverage[resource_type] = False
    return result


def _availability_domains(
    snapshot: OciConnectionSnapshot,
    factory: OciClientFactory,
    operations: OciDiscoveryOperations,
    region: str,
) -> tuple[list[str], bool]:
    identity = factory.identity(region)
    items, complete = operations.paged(
        source="identity_api",
        operation="list_availability_domains",
        region=region,
        compartment_id=snapshot.tenancy_ocid,
        call=identity.list_availability_domains,
        args=(snapshot.tenancy_ocid,),
    )
    domains = {getattr(item, "name", None) for item in items}
    return sorted(domain for domain in domains if domain), complete


def _list_instances(factory, operations, region, compartment_id):
    client = factory.compute(region)
    return operations.paged(
        source="compute_api",
        operation="list_instances",
        region=region,
        compartment_id=compartment_id,
        call=client.list_instances,
        args=(compartment_id,),
        resource_type="compute_instance",
    )


def _list_block_volumes(factory, operations, region, compartment_id):
    client = factory.blockstorage(region)
    return operations.paged(
        source="block_storage_api",
        operation="list_volumes",
        region=region,
        compartment_id=compartment_id,
        call=client.list_volumes,
        kwargs={"compartment_id": compartment_id},
        resource_type="block_volume",
    )


def _list_boot_volumes(factory, operations, region, compartment_id):
    client = factory.blockstorage(region)
    return operations.paged(
        source="block_storage_api",
        operation="list_boot_volumes",
        region=region,
        compartment_id=compartment_id,
        call=client.list_boot_volumes,
        kwargs={"compartment_id": compartment_id},
        resource_type="boot_volume",
    )


def _correlate_block_volume_attachments(
    factory,
    operations,
    region,
    compartment_id,
    volume_ids,
    resources,
    relationships,
) -> None:
    client = factory.compute(region)
    items, complete = operations.paged(
        source="compute_api",
        operation="list_volume_attachments",
        region=region,
        compartment_id=compartment_id,
        call=client.list_volume_attachments,
        args=(compartment_id,),
        resource_type="block_volume",
    )
    attached: dict[str, set[str]] = defaultdict(set)
    for item in items:
        volume_id = getattr(item, "volume_id", None)
        instance_id = getattr(item, "instance_id", None)
        if not volume_id or not instance_id or not _active_attachment(item):
            continue
        attached[volume_id].add(instance_id)
        relationships.add(
            ("volume_attachment", volume_id, instance_id, "block_volume", "compute_instance")
        )

    for volume_id in volume_ids:
        resource = resources.get(volume_id)
        if resource is None:
            continue
        if complete:
            instance_ids = sorted(attached.get(volume_id, set()))
            resource.attributes["attached_instance_ids"] = instance_ids
            resource.attributes["attachment_count"] = len(instance_ids)
            resource.attributes["attachment_coverage"] = "complete"
        else:
            resource.attributes["attachment_coverage"] = "incomplete"


def _correlate_boot_volume_attachments(
    factory,
    operations,
    region,
    compartment_id,
    volume_ids_by_ad,
    resources,
    relationships,
) -> None:
    client = factory.compute(region)
    for availability_domain, volume_ids in volume_ids_by_ad.items():
        items, complete = operations.paged(
            source="compute_api",
            operation="list_boot_volume_attachments",
            region=region,
            compartment_id=compartment_id,
            call=client.list_boot_volume_attachments,
            args=(availability_domain, compartment_id),
            resource_type="boot_volume",
        )
        attached: dict[str, set[str]] = defaultdict(set)
        for item in items:
            boot_volume_id = getattr(item, "boot_volume_id", None)
            instance_id = getattr(item, "instance_id", None)
            if not boot_volume_id or not instance_id or not _active_attachment(item):
                continue
            attached[boot_volume_id].add(instance_id)
            relationships.add(
                (
                    "boot_volume_attachment",
                    boot_volume_id,
                    instance_id,
                    "boot_volume",
                    "compute_instance",
                )
            )

        for volume_id in volume_ids:
            resource = resources.get(volume_id)
            if resource is None:
                continue
            if complete:
                instance_ids = sorted(attached.get(volume_id, set()))
                resource.attributes["attached_instance_ids"] = instance_ids
                resource.attributes["attachment_count"] = len(instance_ids)
                resource.attributes["attachment_coverage"] = "complete"
            else:
                resource.attributes["attachment_coverage"] = "incomplete"


def _list_public_ips(
    factory,
    operations,
    region,
    compartment_id,
    availability_domains,
):
    client = factory.virtual_network(region)
    all_items: list[Any] = []
    items, complete = operations.paged(
        source="virtual_network_api",
        operation="list_public_ips_region",
        region=region,
        compartment_id=compartment_id,
        call=client.list_public_ips,
        args=("REGION", compartment_id),
        resource_type="public_ip",
    )
    all_items.extend(items)

    for availability_domain in availability_domains:
        items, ok = operations.paged(
            source="virtual_network_api",
            operation="list_public_ips_availability_domain",
            region=region,
            compartment_id=compartment_id,
            call=client.list_public_ips,
            args=("AVAILABILITY_DOMAIN", compartment_id),
            kwargs={"availability_domain": availability_domain},
            resource_type="public_ip",
        )
        all_items.extend(items)
        complete = complete and ok

    deduped: dict[str, Any] = {}
    for item in all_items:
        resource_id = getattr(item, "id", None)
        if resource_id:
            deduped[resource_id] = item
    return list(deduped.values()), complete


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _tags(value: Any) -> dict:
    return dict(value or {})


def _active_attachment(item: Any) -> bool:
    state = str(getattr(item, "lifecycle_state", "") or "").upper()
    return state not in {"DETACHED", "DELETED"}


def _instance_image_id(item: Any) -> str | None:
    source_details = getattr(item, "source_details", None)
    source_type = str(getattr(source_details, "source_type", "") or "").casefold()
    if source_type == "image":
        image_id = getattr(source_details, "image_id", None)
        if image_id:
            return str(image_id)
    image_id = getattr(item, "image_id", None)
    return str(image_id) if image_id else None


def _enrich_compute_operating_system(
    snapshot: OciConnectionSnapshot,
    factory: OciClientFactory,
    resource: OciDiscoveredResource,
    item: Any,
    region: str,
    resolver: OciImageOperatingSystemResolver,
) -> None:
    image_id = _instance_image_id(item)
    if image_id:
        resource.attributes["image_id"] = image_id

    resolution = resolver.resolve(
        compute_client=factory.compute(region),
        region=region,
        image_id=image_id,
        cloud_account_id=snapshot.cloud_account_id,
        compartment_id=resource.compartment_id,
        instance_id=resource.resource_id,
    )
    resource.attributes["os_family"] = resolution.family.value
    resource.attributes["os_detection_source"] = resolution.source
    if resolution.raw_value is not None:
        resource.attributes["operating_system"] = resolution.raw_value
    if resolution.version is not None:
        resource.attributes["operating_system_version"] = resolution.version
    if resolution.source == "oci_image_metadata" and "compute_image_api" not in resource.sources:
        resource.sources.append("compute_image_api")


def _compute_resource(item: Any, region: str) -> OciDiscoveredResource | None:
    resource_id = getattr(item, "id", None)
    if not resource_id:
        return None
    shape_config = getattr(item, "shape_config", None)
    attributes: dict[str, Any] = {
        "shape": getattr(item, "shape", None),
        "fault_domain": getattr(item, "fault_domain", None),
        "time_created": _as_iso(getattr(item, "time_created", None)),
    }
    if shape_config is not None:
        attributes["ocpus"] = getattr(shape_config, "ocpus", None)
        attributes["memory_in_gbs"] = getattr(shape_config, "memory_in_gbs", None)
    return OciDiscoveredResource(
        provider=CloudProvider.OCI.value,
        resource_id=resource_id,
        resource_type="compute_instance",
        name=getattr(item, "display_name", None),
        region=region,
        compartment_id=getattr(item, "compartment_id", None),
        lifecycle_state=getattr(item, "lifecycle_state", None),
        availability_domain=getattr(item, "availability_domain", None),
        freeform_tags=_tags(getattr(item, "freeform_tags", None)),
        defined_tags=_tags(getattr(item, "defined_tags", None)),
        sources=["compute_api"],
        attributes={key: value for key, value in attributes.items() if value is not None},
    )


def _block_volume_resource(item: Any, region: str) -> OciDiscoveredResource | None:
    resource_id = getattr(item, "id", None)
    if not resource_id:
        return None
    attributes = {
        "size_in_gbs": getattr(item, "size_in_gbs", None),
        "vpus_per_gb": getattr(item, "vpus_per_gb", None),
        "is_auto_tune_enabled": getattr(item, "is_auto_tune_enabled", None),
        "time_created": _as_iso(getattr(item, "time_created", None)),
    }
    return OciDiscoveredResource(
        provider=CloudProvider.OCI.value,
        resource_id=resource_id,
        resource_type="block_volume",
        name=getattr(item, "display_name", None),
        region=region,
        compartment_id=getattr(item, "compartment_id", None),
        lifecycle_state=getattr(item, "lifecycle_state", None),
        availability_domain=getattr(item, "availability_domain", None),
        freeform_tags=_tags(getattr(item, "freeform_tags", None)),
        defined_tags=_tags(getattr(item, "defined_tags", None)),
        sources=["block_storage_api"],
        attributes={key: value for key, value in attributes.items() if value is not None},
    )


def _boot_volume_resource(item: Any, region: str) -> OciDiscoveredResource | None:
    resource_id = getattr(item, "id", None)
    if not resource_id:
        return None
    attributes = {
        "size_in_gbs": getattr(item, "size_in_gbs", None),
        "vpus_per_gb": getattr(item, "vpus_per_gb", None),
        "time_created": _as_iso(getattr(item, "time_created", None)),
    }
    return OciDiscoveredResource(
        provider=CloudProvider.OCI.value,
        resource_id=resource_id,
        resource_type="boot_volume",
        name=getattr(item, "display_name", None),
        region=region,
        compartment_id=getattr(item, "compartment_id", None),
        lifecycle_state=getattr(item, "lifecycle_state", None),
        availability_domain=getattr(item, "availability_domain", None),
        freeform_tags=_tags(getattr(item, "freeform_tags", None)),
        defined_tags=_tags(getattr(item, "defined_tags", None)),
        sources=["block_storage_api"],
        attributes={key: value for key, value in attributes.items() if value is not None},
    )


def _public_ip_resource(item: Any, region: str) -> OciDiscoveredResource | None:
    resource_id = getattr(item, "id", None)
    if not resource_id:
        return None
    assigned_entity_id = getattr(item, "assigned_entity_id", None)
    attributes = {
        "lifetime": getattr(item, "lifetime", None),
        "scope": getattr(item, "scope", None),
        "ip_address": getattr(item, "ip_address", None),
        "assigned_entity_id": assigned_entity_id,
        "assigned_entity_type": getattr(item, "assigned_entity_type", None),
        "is_associated": assigned_entity_id is not None,
        "time_created": _as_iso(getattr(item, "time_created", None)),
    }
    return OciDiscoveredResource(
        provider=CloudProvider.OCI.value,
        resource_id=resource_id,
        resource_type="public_ip",
        name=getattr(item, "display_name", None),
        region=region,
        compartment_id=getattr(item, "compartment_id", None),
        lifecycle_state=getattr(item, "lifecycle_state", None),
        availability_domain=getattr(item, "availability_domain", None),
        freeform_tags=_tags(getattr(item, "freeform_tags", None)),
        defined_tags=_tags(getattr(item, "defined_tags", None)),
        sources=["virtual_network_api"],
        attributes={key: value for key, value in attributes.items() if value is not None},
    )
