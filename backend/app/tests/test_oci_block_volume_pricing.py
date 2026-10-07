from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.oci_analyzers import (
    OciBlockVolumeUnattachedAnalyzer,
    OciPublicIpUnassignedAnalyzer,
    OciUntaggedResourceAnalyzer,
)
from app.services.oci_correlation_models import (
    OciResourceAnalysisContext,
    OciResourceUsageContext,
)
from app.services.oci_discovery_models import OciDiscoveredResource
from app.services.oci_pricing import (
    OCI_PRICING_CURRENCY,
    OCI_PRICING_SOURCE,
    OCI_PRICING_VERSION,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)
START = NOW - timedelta(days=30)
COMPARTMENT = "ocid1.compartment.oc1..pricing"
REGION = "sa-saopaulo-1"


def _resource(
    resource_id: str,
    resource_type: str,
    *,
    state: str,
    source: str,
    attributes: dict,
) -> OciDiscoveredResource:
    return OciDiscoveredResource(
        provider="oci",
        resource_id=resource_id,
        resource_type=resource_type,
        name="pricing-test-resource",
        region=REGION,
        compartment_id=COMPARTMENT,
        lifecycle_state=state,
        freeform_tags={},
        defined_tags={},
        sources=[source],
        attributes=attributes,
    )


def _context(
    inventory: OciDiscoveredResource,
    *,
    inventory_coverage: dict[str, str] | None = None,
) -> OciResourceAnalysisContext:
    return OciResourceAnalysisContext(
        resource_id=inventory.resource_id,
        inventory=inventory,
        relationships=[],
        native_recommendations=[],
        usage=OciResourceUsageContext(
            records=[],
            totals_by_currency={},
            period_start=START,
            period_end=NOW,
        ),
        coverage={
            "inventory": "complete",
            "advisor": "complete",
            "usage": "complete",
            "monitoring": "complete",
        },
        inventory_coverage=inventory_coverage or {inventory.resource_type: "complete"},
        relationship_coverage={
            "volume_attachment": "complete",
            "boot_volume_attachment": "complete",
            "public_ip_assignment": "complete",
        },
        provenance={"inventory": tuple(inventory.sources)},
    )


def _block_volume_context(
    *,
    size_in_gbs=500,
    vpus_per_gb=10,
) -> OciResourceAnalysisContext:
    return _context(
        _resource(
            "ocid1.volume.oc1.sa-saopaulo-1.pricing",
            "block_volume",
            state="AVAILABLE",
            source="block_storage_api",
            attributes={
                "attachment_count": 0,
                "attachment_coverage": "complete",
                "size_in_gbs": size_in_gbs,
                "vpus_per_gb": vpus_per_gb,
            },
        )
    )


def test_unattached_block_volume_500_gb_vpu_10_is_priced_at_full_savings():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(_block_volume_context())[0]

    assert finding.current_monthly_cost == Decimal("44.55")
    assert finding.estimated_monthly_savings == Decimal("44.55")
    assert finding.currency == "BRL"
    assert finding.provider_metadata["financial_value_populated"] is True


def test_unattached_block_volume_vpu_zero_prices_storage_only():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(
        _block_volume_context(size_in_gbs=100, vpus_per_gb=0)
    )[0]

    assert finding.current_monthly_cost == Decimal("5.31")
    assert finding.estimated_monthly_savings == Decimal("5.31")
    assert finding.currency == "BRL"
    assert finding.provider_metadata["financial_value_populated"] is True


@pytest.mark.parametrize(
    ("size_in_gbs", "vpus_per_gb", "missing_field"),
    [
        (None, 10, "size_in_gbs"),
        (500, None, "vpus_per_gb"),
    ],
)
def test_missing_block_volume_pricing_input_keeps_finding_unpriced(
    size_in_gbs,
    vpus_per_gb,
    missing_field,
):
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(
        _block_volume_context(size_in_gbs=size_in_gbs, vpus_per_gb=vpus_per_gb)
    )[0]

    assert finding.current_monthly_cost == Decimal("0")
    assert finding.estimated_monthly_savings == Decimal("0")
    assert finding.currency == "BRL"
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["status"] == "missing_pricing_input"
    assert finding.evidence["pricing"]["missing_fields"] == [missing_field]


@pytest.mark.parametrize(
    ("size_in_gbs", "vpus_per_gb"),
    [(-1, 10), (500, -1), ("invalid", 10)],
)
def test_invalid_block_volume_pricing_input_never_produces_negative_or_valid_savings(
    size_in_gbs,
    vpus_per_gb,
):
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(
        _block_volume_context(size_in_gbs=size_in_gbs, vpus_per_gb=vpus_per_gb)
    )[0]

    assert finding.current_monthly_cost == Decimal("0")
    assert finding.estimated_monthly_savings == Decimal("0")
    assert finding.provider_metadata["financial_value_populated"] is False
    assert finding.evidence["pricing"]["status"] == "invalid_pricing_input"


def test_priced_block_volume_evidence_identifies_internal_catalog_and_inputs():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(_block_volume_context())[0]
    pricing = finding.evidence["pricing"]

    assert pricing == {
        "status": "priced",
        "source": OCI_PRICING_SOURCE,
        "version": OCI_PRICING_VERSION,
        "currency": OCI_PRICING_CURRENCY,
        "resource_type": "block_volume",
        "size_gb": 500,
        "vpus_per_gb": 10,
        "monthly_cost": "44.55",
        "financial_value_populated": True,
    }


def test_public_ip_and_untagged_analyzers_remain_financially_unpopulated():
    public_ip = _context(
        _resource(
            "ocid1.publicip.oc1.sa-saopaulo-1.regression",
            "public_ip",
            state="AVAILABLE",
            source="virtual_network_api",
            attributes={
                "lifetime": "RESERVED",
                "is_associated": False,
                "assigned_entity_id": None,
            },
        )
    )
    public_ip_finding = OciPublicIpUnassignedAnalyzer().analyze(public_ip)[0]

    untagged = _context(
        _resource(
            "ocid1.bootvolume.oc1.sa-saopaulo-1.regression",
            "boot_volume",
            state="AVAILABLE",
            source="block_storage_api",
            attributes={},
        )
    )
    untagged_finding = OciUntaggedResourceAnalyzer().analyze(untagged)[0]

    for finding in (public_ip_finding, untagged_finding):
        assert finding.current_monthly_cost == Decimal("0")
        assert finding.estimated_monthly_savings == Decimal("0")
        assert finding.provider_metadata["financial_value_populated"] is False
        assert "pricing" not in finding.evidence
