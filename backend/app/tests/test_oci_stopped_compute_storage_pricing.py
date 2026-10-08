from __future__ import annotations

from decimal import Decimal

from app.services.oci_analyzers import (
    OciBlockVolumeUnattachedAnalyzer,
    OciPublicIpUnassignedAnalyzer,
    OciStoppedComputeWithStorageAnalyzer,
    OciUntaggedResourceAnalyzer,
)
from app.services.oci_correlation_models import (
    OciResourceAnalysisContext,
    OciResourceUsageContext,
)
from app.services.oci_discovery_models import OciDiscoveredResource, OciResourceRelationship
from app.services.oci_pricing import OCI_PRICING_SOURCE, OCI_PRICING_VERSION

REGION = "sa-saopaulo-1"
COMPARTMENT = "ocid1.compartment.oc1..task4"
COMPUTE_ID = "ocid1.instance.oc1.sa-saopaulo-1.task4"
BOOT_ID = "ocid1.bootvolume.oc1.sa-saopaulo-1.task4"
BLOCK_ID = "ocid1.volume.oc1.sa-saopaulo-1.task4"


def _resource(
    resource_id: str,
    resource_type: str,
    *,
    state: str = "AVAILABLE",
    source: str = "block_storage_api",
    attributes: dict | None = None,
) -> OciDiscoveredResource:
    return OciDiscoveredResource(
        provider="oci",
        resource_id=resource_id,
        resource_type=resource_type,
        name="task4-resource",
        region=REGION,
        compartment_id=COMPARTMENT,
        lifecycle_state=state,
        freeform_tags={},
        defined_tags={},
        sources=[source],
        attributes=dict(attributes or {}),
    )


def _relationship(resource: OciDiscoveredResource) -> OciResourceRelationship:
    relation_type = (
        "boot_volume_attachment" if resource.resource_type == "boot_volume" else "volume_attachment"
    )
    return OciResourceRelationship(
        relation_type=relation_type,
        source_id=resource.resource_id,
        target_id=COMPUTE_ID,
        source_type=resource.resource_type,
        target_type="compute_instance",
    )


def _compute_context(
    volumes: list[OciDiscoveredResource],
    *,
    duplicate_relationships: bool = False,
    compute_attributes: dict | None = None,
) -> tuple[OciResourceAnalysisContext, dict[str, OciDiscoveredResource]]:
    compute = _resource(
        COMPUTE_ID,
        "compute_instance",
        state="STOPPED",
        source="compute_api",
        attributes=compute_attributes,
    )
    relationships = [_relationship(volume) for volume in volumes]
    if duplicate_relationships and relationships:
        relationships.append(relationships[0])
    context = OciResourceAnalysisContext(
        resource_id=COMPUTE_ID,
        inventory=compute,
        relationships=relationships,
        usage=OciResourceUsageContext(),
        coverage={"inventory": "complete", "usage": "complete", "advisor": "complete"},
        inventory_coverage={
            "compute_instance": "complete",
            "boot_volume": "complete",
            "block_volume": "complete",
        },
        relationship_coverage={
            "boot_volume_attachment": "complete",
            "volume_attachment": "complete",
        },
        provenance={"inventory": ("compute_api",)},
    )
    inventory = {compute.resource_id: compute}
    inventory.update({volume.resource_id: volume for volume in volumes})
    return context, inventory


def _volume(
    resource_id: str,
    resource_type: str,
    *,
    size_in_gbs=100,
    vpus_per_gb=10,
) -> OciDiscoveredResource:
    return _resource(
        resource_id,
        resource_type,
        attributes={"size_in_gbs": size_in_gbs, "vpus_per_gb": vpus_per_gb},
    )


def _analyze(
    volumes: list[OciDiscoveredResource],
    *,
    duplicate_relationships: bool = False,
    compute_attributes: dict | None = None,
):
    context, inventory = _compute_context(
        volumes,
        duplicate_relationships=duplicate_relationships,
        compute_attributes=compute_attributes,
    )
    return OciStoppedComputeWithStorageAnalyzer().analyze(
        context,
        inventory_by_id=inventory,
    )[0]


def test_boot_volume_only_is_priced():
    finding = _analyze([_volume(BOOT_ID, "boot_volume")])
    assert finding.current_monthly_cost == Decimal("8.91")
    assert finding.estimated_monthly_savings == Decimal("8.91")
    assert finding.currency == "BRL"
    assert finding.provider_metadata["financial_value_populated"] is True


def test_block_volume_only_is_priced():
    finding = _analyze([_volume(BLOCK_ID, "block_volume", size_in_gbs=500)])
    assert finding.current_monthly_cost == Decimal("44.55")
    assert finding.estimated_monthly_savings == Decimal("44.55")


def test_boot_plus_block_matches_approved_example():
    finding = _analyze(
        [
            _volume(BOOT_ID, "boot_volume", size_in_gbs=100),
            _volume(BLOCK_ID, "block_volume", size_in_gbs=500),
        ]
    )
    assert finding.current_monthly_cost == Decimal("53.46")
    assert finding.estimated_monthly_savings == Decimal("53.46")
    pricing = finding.evidence["pricing"]
    assert pricing["status"] == "priced"
    assert pricing["source"] == OCI_PRICING_SOURCE
    assert pricing["version"] == OCI_PRICING_VERSION
    assert pricing["currency"] == "BRL"
    assert pricing["persistent_storage_monthly_cost"] == "53.46"
    assert pricing["boot_volume_count"] == 1
    assert pricing["block_volume_count"] == 1


def test_multiple_block_volumes_are_summed():
    finding = _analyze(
        [
            _volume(BLOCK_ID, "block_volume", size_in_gbs=500),
            _volume(f"{BLOCK_ID}.two", "block_volume", size_in_gbs=100),
        ]
    )
    assert finding.current_monthly_cost == Decimal("53.46")


def test_zero_vpu_prices_storage_component_only():
    finding = _analyze([_volume(BOOT_ID, "boot_volume", vpus_per_gb=0)])
    assert finding.current_monthly_cost == Decimal("5.31")
    assert finding.provider_metadata["financial_value_populated"] is True


def test_missing_size_marks_pricing_incomplete():
    finding = _analyze([_volume(BOOT_ID, "boot_volume", size_in_gbs=None)])
    assert finding.current_monthly_cost == Decimal("0")
    assert finding.estimated_monthly_savings == Decimal("0")
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["status"] == "incomplete"
    assert finding.evidence["pricing"]["unpriced_resources"] == [
        {"resource_id": BOOT_ID, "reason": "missing_size_in_gbs"}
    ]


def test_missing_vpu_does_not_assume_default():
    finding = _analyze([_volume(BLOCK_ID, "block_volume", vpus_per_gb=None)])
    assert finding.current_monthly_cost == Decimal("0")
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["unpriced_resources"] == [
        {"resource_id": BLOCK_ID, "reason": "missing_vpus_per_gb"}
    ]


def test_partial_pricing_is_not_promoted_to_main_saving():
    finding = _analyze(
        [
            _volume(BOOT_ID, "boot_volume", size_in_gbs=100),
            _volume(BLOCK_ID, "block_volume", size_in_gbs=500),
            _volume(f"{BLOCK_ID}.missing", "block_volume", size_in_gbs=100, vpus_per_gb=None),
        ]
    )
    assert finding.current_monthly_cost == Decimal("0")
    assert finding.estimated_monthly_savings == Decimal("0")
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["priced_monthly_subtotal"] == "53.46"
    assert finding.evidence["pricing"]["persistent_storage_monthly_cost"] is None


def test_duplicate_relationship_does_not_double_count_volume():
    finding = _analyze(
        [_volume(BLOCK_ID, "block_volume", size_in_gbs=500)],
        duplicate_relationships=True,
    )
    assert finding.current_monthly_cost == Decimal("44.55")
    assert finding.evidence["analysis"]["block_volume_count"] == 1


def test_compute_shape_ocpu_and_memory_do_not_change_storage_price():
    volume = _volume(BLOCK_ID, "block_volume", size_in_gbs=500)
    first = _analyze(
        [volume],
        compute_attributes={"shape": "VM.Standard.E4.Flex", "ocpus": 4, "memory_in_gbs": 64},
    )
    second = _analyze(
        [volume],
        compute_attributes={"shape": "VM.Standard.E5.Flex", "ocpus": 64, "memory_in_gbs": 1024},
    )
    assert first.current_monthly_cost == second.current_monthly_cost == Decimal("44.55")


def test_public_ip_and_untagged_resource_remain_without_automatic_pricing():
    public_ip = _resource(
        "ocid1.publicip.oc1.sa-saopaulo-1.task4",
        "public_ip",
        source="virtual_network_api",
        attributes={"lifetime": "RESERVED", "is_associated": False},
    )
    public_context = OciResourceAnalysisContext(
        resource_id=public_ip.resource_id,
        inventory=public_ip,
        coverage={"inventory": "complete"},
        inventory_coverage={"public_ip": "complete"},
    )
    public_finding = OciPublicIpUnassignedAnalyzer().analyze(public_context)[0]

    untagged = _resource(BOOT_ID, "boot_volume", attributes={})
    untagged_context = OciResourceAnalysisContext(
        resource_id=untagged.resource_id,
        inventory=untagged,
        coverage={"inventory": "complete"},
        inventory_coverage={"boot_volume": "complete"},
    )
    untagged_finding = OciUntaggedResourceAnalyzer().analyze(untagged_context)[0]

    for finding in (public_finding, untagged_finding):
        assert finding.current_monthly_cost == Decimal("0")
        assert finding.estimated_monthly_savings == Decimal("0")
        assert finding.provider_metadata["financial_value_populated"] is False
        assert "pricing" not in finding.evidence


def test_unattached_block_volume_task3_pricing_regression():
    block = _resource(
        BLOCK_ID,
        "block_volume",
        attributes={
            "attachment_count": 0,
            "attachment_coverage": "complete",
            "size_in_gbs": 500,
            "vpus_per_gb": 10,
        },
    )
    context = OciResourceAnalysisContext(
        resource_id=block.resource_id,
        inventory=block,
        coverage={"inventory": "complete"},
        inventory_coverage={"block_volume": "complete"},
    )
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(context)[0]
    assert finding.current_monthly_cost == Decimal("44.55")
    assert finding.estimated_monthly_savings == Decimal("44.55")
    assert finding.currency == "BRL"
    assert finding.provider_metadata["financial_value_populated"] is True


def test_missing_related_inventory_resource_is_incomplete_not_zero_priced():
    boot = _volume(BOOT_ID, "boot_volume")
    context, inventory = _compute_context([boot])
    inventory.pop(BOOT_ID)
    finding = OciStoppedComputeWithStorageAnalyzer().analyze(
        context,
        inventory_by_id=inventory,
    )[0]
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["status"] == "incomplete"
    assert finding.evidence["pricing"]["unpriced_resources"] == [
        {"resource_id": BOOT_ID, "reason": "missing_inventory_resource"}
    ]
