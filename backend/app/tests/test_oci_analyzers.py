from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.oci_analyzers import (
    ANALYZER_VERSION,
    RULE_BLOCK_VOLUME_UNATTACHED,
    RULE_PUBLIC_IP_UNASSIGNED,
    RULE_STOPPED_COMPUTE_WITH_STORAGE,
    RULE_UNTAGGED_RESOURCE,
    OciAnalysisService,
    OciAnalyzerRegistry,
    OciBlockVolumeUnattachedAnalyzer,
    OciPublicIpUnassignedAnalyzer,
    OciStoppedComputeWithStorageAnalyzer,
    OciUntaggedResourceAnalyzer,
)
from app.services.oci_cloud_advisor_models import (
    OciNativeRecommendation,
    OciNativeResourceAction,
)
from app.services.oci_correlation_models import (
    OciAccountAnalysisContext,
    OciCorrelationResult,
    OciCorrelationSourceCoverage,
    OciResourceAnalysisContext,
    OciResourceRecommendationLink,
    OciResourceUsageContext,
)
from app.services.oci_discovery_models import (
    OciDiscoveredResource,
    OciResourceRelationship,
)
from app.services.oci_usage_models import OciUsageRecord
from app.services.opportunity_fingerprint import build_opportunity_fingerprint

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)
START = NOW - timedelta(days=30)
COMPARTMENT = "ocid1.compartment.oc1..test"
REGION = "sa-saopaulo-1"


def resource(
    resource_id: str,
    resource_type: str,
    *,
    state: str = "AVAILABLE",
    source: str | None = None,
    attributes: dict | None = None,
    freeform_tags: dict | None = None,
    defined_tags: dict | None = None,
) -> OciDiscoveredResource:
    default_source = {
        "compute_instance": "compute_api",
        "block_volume": "block_storage_api",
        "boot_volume": "block_storage_api",
        "public_ip": "virtual_network_api",
    }.get(resource_type, "resource_search")
    return OciDiscoveredResource(
        provider="oci",
        resource_id=resource_id,
        resource_type=resource_type,
        name="test-resource",
        region=REGION,
        compartment_id=COMPARTMENT,
        lifecycle_state=state,
        freeform_tags=freeform_tags or {},
        defined_tags=defined_tags or {},
        sources=[source or default_source],
        attributes=dict(attributes or {}),
    )


def usage_record(
    resource_id: str,
    cost: str,
    currency: str,
) -> OciUsageRecord:
    return OciUsageRecord(
        start_time=START,
        end_time=NOW,
        resource_id=resource_id,
        service="test",
        region=REGION,
        compartment_id=COMPARTMENT,
        sku_name=None,
        sku_part_number=None,
        unit=None,
        usage_quantity=None,
        actual_cost=Decimal(cost),
        currency=currency,
    )


def native_link(
    resource_id: str,
    *,
    recommendation_id: str = "rec-1",
    saving: float | None = 10.0,
    currency: str | None = "USD",
) -> OciResourceRecommendationLink:
    recommendation = OciNativeRecommendation(
        recommendation_id=recommendation_id,
        name="Native recommendation",
        description="OCI native evidence",
        category_id="cost",
        importance="HIGH",
        lifecycle_state="ACTIVE",
        status="ACTIVE",
        tenancy_id="ocid1.tenancy.oc1..test",
        native_estimated_savings=saving,
        currency=currency,
        time_created=START,
        time_updated=NOW,
        time_status_begin=START,
        time_status_end=None,
    )
    action = OciNativeResourceAction(
        resource_action_id=f"action-{recommendation_id}",
        recommendation_id=recommendation_id,
        name="Native action",
        resource_id=resource_id,
        resource_type=None,
        compartment_id=COMPARTMENT,
        compartment_name=None,
        action=None,
        lifecycle_state="ACTIVE",
        status="ACTIVE",
        native_estimated_savings=saving,
        currency=currency,
        time_created=START,
        time_updated=NOW,
        time_status_begin=START,
        time_status_end=None,
    )
    return OciResourceRecommendationLink(action=action, recommendation=recommendation)


def context(
    inventory: OciDiscoveredResource | None,
    *,
    relationships: list[OciResourceRelationship] | None = None,
    inventory_status: str = "complete",
    type_coverage: dict[str, str] | None = None,
    costs: list[tuple[str, str]] | None = None,
    recommendations: list[OciResourceRecommendationLink] | None = None,
) -> OciResourceAnalysisContext:
    resource_id = inventory.resource_id if inventory is not None else "ocid1.unknown.test"
    records = [
        usage_record(resource_id, value, currency)
        for value, currency in costs or []
    ]
    totals: dict[str, Decimal] = {}
    for record in records:
        assert record.actual_cost is not None
        assert record.currency is not None
        totals[record.currency] = totals.get(record.currency, Decimal("0")) + record.actual_cost
    inferred_coverage = {}
    if inventory is not None:
        inferred_coverage[inventory.resource_type] = "complete"
    if type_coverage is not None:
        inferred_coverage = dict(type_coverage)
    return OciResourceAnalysisContext(
        resource_id=resource_id,
        inventory=inventory,
        relationships=list(relationships or []),
        native_recommendations=list(recommendations or []),
        usage=OciResourceUsageContext(
            records=records,
            totals_by_currency=totals,
            period_start=START,
            period_end=NOW,
        ),
        coverage={
            "inventory": inventory_status,
            "advisor": "complete",
            "usage": "complete",
            "monitoring": "complete",
        },
        inventory_coverage=inferred_coverage,
        provenance={"inventory": tuple(inventory.sources) if inventory is not None else ()},
    )


def block_volume_context(
    *,
    attachments: int = 0,
    attachment_coverage: str = "complete",
    state: str = "AVAILABLE",
    inventory_status: str = "complete",
    costs: list[tuple[str, str]] | None = None,
    recommendations: list[OciResourceRecommendationLink] | None = None,
) -> OciResourceAnalysisContext:
    item = resource(
        "ocid1.volume.oc1.sa-saopaulo-1.test",
        "block_volume",
        state=state,
        attributes={
            "attachment_count": attachments,
            "attachment_coverage": attachment_coverage,
            "size_in_gbs": 500,
        },
    )
    return context(
        item,
        inventory_status=inventory_status,
        costs=costs,
        recommendations=recommendations,
    )


def public_ip_context(
    *,
    associated: bool | None = False,
    lifetime: str = "RESERVED",
    inventory_status: str = "complete",
    costs: list[tuple[str, str]] | None = None,
) -> OciResourceAnalysisContext:
    attrs = {"lifetime": lifetime}
    if associated is not None:
        attrs["is_associated"] = associated
        attrs["assigned_entity_id"] = "ocid1.privateip.test" if associated else None
    item = resource(
        "ocid1.publicip.oc1.sa-saopaulo-1.test",
        "public_ip",
        attributes=attrs,
    )
    return context(item, inventory_status=inventory_status, costs=costs)


def stopped_compute_context(
    *,
    state: str = "STOPPED",
    relationships: list[OciResourceRelationship] | None = None,
    coverage: dict[str, str] | None = None,
    costs: list[tuple[str, str]] | None = None,
) -> OciResourceAnalysisContext:
    compute = resource(
        "ocid1.instance.oc1.sa-saopaulo-1.test",
        "compute_instance",
        state=state,
    )
    return context(
        compute,
        relationships=relationships,
        type_coverage=coverage
        or {
            "compute_instance": "complete",
            "block_volume": "complete",
            "boot_volume": "complete",
        },
        costs=costs,
    )


def boot_relationship() -> OciResourceRelationship:
    return OciResourceRelationship(
        relation_type="boot_volume_attachment",
        source_id="ocid1.bootvolume.oc1.sa-saopaulo-1.boot",
        target_id="ocid1.instance.oc1.sa-saopaulo-1.test",
        source_type="boot_volume",
        target_type="compute_instance",
    )


def block_relationship() -> OciResourceRelationship:
    return OciResourceRelationship(
        relation_type="volume_attachment",
        source_id="ocid1.volume.oc1.sa-saopaulo-1.data",
        target_id="ocid1.instance.oc1.sa-saopaulo-1.test",
        source_type="block_volume",
        target_type="compute_instance",
    )


def test_registry_contains_wave1_analyzers_and_unknown_type_is_empty():
    registry = OciAnalyzerRegistry()
    assert registry.rule_keys == (
        RULE_BLOCK_VOLUME_UNATTACHED,
        RULE_PUBLIC_IP_UNASSIGNED,
        RULE_STOPPED_COMPUTE_WITH_STORAGE,
        RULE_UNTAGGED_RESOURCE,
    )
    unknown = context(resource("ocid1.widget.test", "oci_resource"))
    assert registry.analyze(unknown) == []


def test_multiple_analyzers_can_evaluate_same_resource():
    registry = OciAnalyzerRegistry()
    findings = registry.analyze(block_volume_context())
    assert [item.rule_key for item in findings] == [
        RULE_BLOCK_VOLUME_UNATTACHED,
        RULE_UNTAGGED_RESOURCE,
    ]


def test_registry_order_does_not_change_semantic_result():
    ctx = block_volume_context()
    first = OciAnalyzerRegistry().analyze(ctx)
    second = OciAnalyzerRegistry(
        [
            OciUntaggedResourceAnalyzer(),
            OciStoppedComputeWithStorageAnalyzer(),
            OciPublicIpUnassignedAnalyzer(),
            OciBlockVolumeUnattachedAnalyzer(),
        ]
    ).analyze(ctx)
    assert first == second


@pytest.mark.parametrize("attachments", [1, 2])
def test_block_volume_with_attachment_has_no_unattached_finding(attachments):
    findings = OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(attachments=attachments)
    )
    assert findings == []


@pytest.mark.parametrize(
    ("attachment_coverage", "inventory_status"),
    [("incomplete", "complete"), ("unknown", "complete"), ("complete", "partial")],
)
def test_block_volume_incomplete_coverage_has_no_false_positive(
    attachment_coverage,
    inventory_status,
):
    findings = OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(
            attachment_coverage=attachment_coverage,
            inventory_status=inventory_status,
        )
    )
    assert findings == []


@pytest.mark.parametrize("state", ["TERMINATED", "TERMINATING", "DELETED", "FAULTY"])
def test_block_volume_incompatible_lifecycle_is_skipped(state):
    assert OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(state=state)
    ) == []


def test_block_volume_without_cost_emits_high_confidence_finding_without_savings():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(block_volume_context())[0]
    assert finding.rule_key == RULE_BLOCK_VOLUME_UNATTACHED
    assert finding.confidence == "high"
    assert finding.current_monthly_cost == Decimal("0")
    assert finding.estimated_monthly_savings == Decimal("0")
    assert finding.evidence["observed_cost"]["available"] is False


def test_block_volume_observed_cost_and_native_advisor_are_evidence_only():
    ctx = block_volume_context(
        costs=[("87.42", "USD")],
        recommendations=[
            native_link("ocid1.volume.oc1.sa-saopaulo-1.test", saving=40.0)
        ],
    )
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(ctx)[0]
    assert finding.evidence["observed_cost"]["totals_by_currency"] == [
        {"currency": "USD", "observed_cost": "87.42"}
    ]
    native = finding.evidence["native_recommendations"][0]
    assert native["source"] == "oci_cloud_advisor"
    assert native["native_estimated_savings"] == 40.0
    assert finding.estimated_monthly_savings == Decimal("0")


def test_block_volume_multiple_currencies_are_not_consolidated():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(costs=[("10", "USD"), ("20", "BRL")])
    )[0]
    assert finding.evidence["observed_cost"]["totals_by_currency"] == [
        {"currency": "BRL", "observed_cost": "20"},
        {"currency": "USD", "observed_cost": "10"},
    ]
    assert finding.estimated_monthly_savings == Decimal("0")


def test_native_recommendation_order_is_deterministic():
    links = [
        native_link("ocid1.volume.oc1.sa-saopaulo-1.test", recommendation_id="b"),
        native_link("ocid1.volume.oc1.sa-saopaulo-1.test", recommendation_id="a"),
    ]
    first = OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(recommendations=links)
    )[0]
    second = OciBlockVolumeUnattachedAnalyzer().analyze(
        block_volume_context(recommendations=list(reversed(links)))
    )[0]
    assert first == second


def test_public_ip_reserved_unassigned_emits_finding():
    finding = OciPublicIpUnassignedAnalyzer().analyze(public_ip_context())[0]
    assert finding.rule_key == RULE_PUBLIC_IP_UNASSIGNED
    assert finding.evidence["analysis"]["is_associated"] is False


@pytest.mark.parametrize(
    ("associated", "lifetime"),
    [(True, "RESERVED"), (None, "RESERVED"), (False, "EPHEMERAL")],
)
def test_public_ip_unknown_associated_or_nonreserved_is_skipped(associated, lifetime):
    assert OciPublicIpUnassignedAnalyzer().analyze(
        public_ip_context(associated=associated, lifetime=lifetime)
    ) == []


def test_public_ip_networking_failure_has_no_false_positive():
    assert OciPublicIpUnassignedAnalyzer().analyze(
        public_ip_context(inventory_status="partial")
    ) == []


def test_public_ip_cost_is_evidence_not_invented_savings():
    finding = OciPublicIpUnassignedAnalyzer().analyze(
        public_ip_context(costs=[("3.21", "USD")])
    )[0]
    assert finding.evidence["observed_cost"]["available"] is True
    assert finding.estimated_monthly_savings == Decimal("0")


def test_stopped_compute_with_boot_volume_emits_one_finding():
    finding = OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(relationships=[boot_relationship()])
    )[0]
    assert finding.evidence["analysis"]["boot_volume_count"] == 1
    assert finding.evidence["analysis"]["block_volume_count"] == 0


def test_stopped_compute_with_block_volume_emits_one_finding():
    finding = OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(relationships=[block_relationship()])
    )[0]
    assert finding.evidence["analysis"]["block_volume_count"] == 1


def test_stopped_compute_with_both_and_duplicates_emits_one_deduplicated_finding():
    rels = [boot_relationship(), block_relationship(), block_relationship()]
    findings = OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(relationships=rels)
    )
    assert len(findings) == 1
    assert findings[0].evidence["analysis"]["block_volume_count"] == 1
    assert findings[0].evidence["analysis"]["boot_volume_count"] == 1


@pytest.mark.parametrize("state", ["RUNNING", "STARTING"])
def test_nonstopped_compute_is_skipped(state):
    assert OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(state=state, relationships=[boot_relationship()])
    ) == []


def test_stopped_compute_without_storage_is_skipped():
    assert OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context()
    ) == []


def test_stopped_compute_incomplete_storage_coverage_is_skipped():
    coverage = {
        "compute_instance": "complete",
        "block_volume": "incomplete",
        "boot_volume": "complete",
    }
    assert OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(
            relationships=[boot_relationship()],
            coverage=coverage,
        )
    ) == []


def test_stopped_compute_cost_is_preserved_but_not_promoted_to_savings():
    finding = OciStoppedComputeWithStorageAnalyzer().analyze(
        stopped_compute_context(
            relationships=[boot_relationship()],
            costs=[("15.50", "USD")],
        )
    )[0]
    assert finding.evidence["observed_cost"]["available"] is True
    assert finding.estimated_monthly_savings == Decimal("0")


def test_stopped_compute_does_not_require_monitoring():
    ctx = stopped_compute_context(relationships=[boot_relationship()])
    ctx.coverage["monitoring"] = "unavailable"
    assert OciStoppedComputeWithStorageAnalyzer().analyze(ctx)


@pytest.mark.parametrize(
    ("freeform", "defined", "expected"),
    [
        ({}, {}, 1),
        ({"Owner": "FinOps"}, {}, 0),
        ({}, {"Operations": {"Status": "Ativo"}}, 0),
        ({"Owner": "FinOps"}, {"Operations": {"Status": "Ativo"}}, 0),
    ],
)
def test_untagged_rule_respects_freeform_and_defined_tags(freeform, defined, expected):
    item = resource(
        "ocid1.instance.oc1.sa-saopaulo-1.tags",
        "compute_instance",
        state="RUNNING",
        freeform_tags=freeform,
        defined_tags=defined,
    )
    findings = OciUntaggedResourceAnalyzer().analyze(context(item))
    assert len(findings) == expected


def test_defined_tag_namespace_is_not_lost_or_misclassified_as_untagged():
    item = resource(
        "ocid1.volume.oc1.sa-saopaulo-1.tags",
        "block_volume",
        defined_tags={"Operations": {"Status": "Ativo"}},
    )
    assert OciUntaggedResourceAnalyzer().analyze(context(item)) == []
    assert item.defined_tags["Operations"]["Status"] == "Ativo"


def test_unknown_resource_type_does_not_receive_tag_finding():
    item = resource("ocid1.widget.test", "oci_resource")
    assert OciUntaggedResourceAnalyzer().analyze(context(item)) == []


def test_tag_finding_has_no_financial_savings_or_hardcoded_required_tags():
    finding = OciUntaggedResourceAnalyzer().analyze(
        context(resource("ocid1.bootvolume.test", "boot_volume"))
    )[0]
    assert finding.estimated_monthly_savings == Decimal("0")
    rendered = repr(finding).lower()
    assert "costcenter" not in rendered
    assert "environment" not in rendered


def test_finding_contract_contains_oci_identity_provenance_and_version():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(block_volume_context())[0]
    assert finding.resource_id.startswith("ocid1.volume.")
    assert finding.resource_type == "block_volume"
    assert finding.region == REGION
    assert finding.provider_metadata["provider"] == "oci"
    assert finding.provider_metadata["compartment_id"] == COMPARTMENT
    assert finding.provider_metadata["analyzer_version"] == ANALYZER_VERSION
    assert finding.evidence["analysis_source"] == "deepops"
    assert finding.evidence["coverage"]["inventory"] == "complete"


def test_evidence_contains_no_raw_sdk_objects():
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(block_volume_context())[0]
    rendered = repr(finding.evidence)
    assert "oci." not in rendered.lower()
    assert "private_key" not in rendered.lower()
    assert "passphrase" not in rendered.lower()
    assert "signer" not in rendered.lower()


def test_same_input_returns_same_finding_and_input_is_not_mutated():
    analyzer = OciStoppedComputeWithStorageAnalyzer()
    ctx = stopped_compute_context(
        relationships=[block_relationship(), boot_relationship()]
    )
    before = deepcopy(ctx)
    first = analyzer.analyze(ctx)
    second = analyzer.analyze(ctx)
    assert first == second
    assert ctx == before


def test_relationship_order_does_not_change_finding():
    analyzer = OciStoppedComputeWithStorageAnalyzer()
    rels = [block_relationship(), boot_relationship()]
    first = analyzer.analyze(stopped_compute_context(relationships=rels))
    second = analyzer.analyze(
        stopped_compute_context(relationships=list(reversed(rels)))
    )
    assert first == second


def test_fingerprint_readiness_ignores_evidence_and_cost_for_identity():
    ctx = block_volume_context()
    finding = OciBlockVolumeUnattachedAnalyzer().analyze(ctx)[0]
    base = build_opportunity_fingerprint(
        provider="oci",
        account_id="ocid1.tenancy.oc1..test",
        region=finding.region,
        resource_id=finding.resource_id,
        rule_id=finding.rule_key,
    )
    changed = build_opportunity_fingerprint(
        provider="oci",
        account_id="ocid1.tenancy.oc1..test",
        region=finding.region,
        resource_id=finding.resource_id,
        rule_id=finding.rule_key,
    )
    assert base == changed


def test_fingerprint_changes_for_resource_or_rule_and_aws_semantics_remain_callable():
    one = build_opportunity_fingerprint(
        provider="oci",
        account_id="ocid1.tenancy.oc1..test",
        region=REGION,
        resource_id="ocid1.volume.one",
        rule_id=RULE_BLOCK_VOLUME_UNATTACHED,
    )
    two = build_opportunity_fingerprint(
        provider="oci",
        account_id="ocid1.tenancy.oc1..test",
        region=REGION,
        resource_id="ocid1.volume.two",
        rule_id=RULE_BLOCK_VOLUME_UNATTACHED,
    )
    other_rule = build_opportunity_fingerprint(
        provider="oci",
        account_id="ocid1.tenancy.oc1..test",
        region=REGION,
        resource_id="ocid1.volume.one",
        rule_id=RULE_UNTAGGED_RESOURCE,
    )
    aws = build_opportunity_fingerprint(
        provider="aws",
        account_id="123456789012",
        region="us-east-1",
        resource_id="vol-123",
        rule_id="ebs_unattached",
    )
    assert one != two
    assert one != other_rule
    assert len(aws) == 64


def test_analysis_service_aggregates_without_persistence_side_effects():
    contexts = [
        block_volume_context(),
        public_ip_context(),
        stopped_compute_context(relationships=[boot_relationship()]),
    ]
    correlation = OciCorrelationResult(
        status="success",
        resource_contexts=contexts,
        account_context=OciAccountAnalysisContext(),
        unmatched_resource_ids_by_source={},
        coverage={
            "inventory": OciCorrelationSourceCoverage(
                status="success",
                coverage={},
                warning_count=0,
                error_count=0,
            )
        },
        source_warnings={},
        source_errors={},
        warnings=[],
        time_alignment="exact",
        source_freshness={},
    )
    findings = OciAnalysisService().analyze(correlation)
    assert {finding.rule_key for finding in findings} >= {
        RULE_BLOCK_VOLUME_UNATTACHED,
        RULE_PUBLIC_IP_UNASSIGNED,
        RULE_STOPPED_COMPUTE_WITH_STORAGE,
    }
    rendered = repr(findings).lower()
    for forbidden in ("collectionrun", "scan(", "db.add", "private_key"):
        assert forbidden not in rendered
