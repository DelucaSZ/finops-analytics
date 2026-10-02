from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.oci_cloud_advisor_models import (
    OciCloudAdvisorIssue,
    OciCloudAdvisorResult,
    OciNativeRecommendation,
    OciNativeResourceAction,
)
from app.services.oci_correlation import correlate_oci_datasets
from app.services.oci_discovery_models import (
    OciDiscoveredResource,
    OciDiscoveryIssue,
    OciDiscoveryResult,
    OciResourceRelationship,
)
from app.services.oci_monitoring_models import (
    OciMetricDatapoint,
    OciMetricSeries,
    OciMonitoringIssue,
    OciMonitoringResult,
    OciResourceMetrics,
)
from app.services.oci_usage_models import OciUsageRecord, OciUsageResult

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)
START = NOW - timedelta(days=30)


def resource(resource_id, *, name="resource", resource_type="compute_instance", state="RUNNING"):
    return OciDiscoveredResource(
        provider="oci",
        resource_id=resource_id,
        resource_type=resource_type,
        name=name,
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.test",
        lifecycle_state=state,
        sources=["compute_api"],
        attributes={"shape": "VM.Standard.E5.Flex"},
    )


def discovery(resources=None, *, relationships=None, status="success", errors=None):
    return OciDiscoveryResult(
        status=status,
        resources=list(resources or []),
        relationships=list(relationships or []),
        regions_scanned=("sa-saopaulo-1",),
        compartments_scanned=("ocid1.compartment.test",),
        observed_counts_by_type={},
        counts_by_type={},
        warnings=[],
        errors=list(errors or []),
        started_at=START,
        completed_at=NOW,
    )


def recommendation(rec_id="rec-1", *, status="ACTIVE", saving=100.0, currency="USD"):
    return OciNativeRecommendation(
        recommendation_id=rec_id,
        name="Right size",
        description="native recommendation",
        category_id="cost",
        importance="HIGH",
        lifecycle_state="ACTIVE",
        status=status,
        tenancy_id="ocid1.tenancy.test",
        native_estimated_savings=saving,
        currency=currency,
        time_created=START,
        time_updated=NOW,
        time_status_begin=START,
        time_status_end=None,
        scope_match="in",
    )


def action(
    action_id="action-1",
    *,
    rec_id="rec-1",
    resource_id="ocid1.instance.a",
    resource_type="compute_instance",
):
    return OciNativeResourceAction(
        resource_action_id=action_id,
        recommendation_id=rec_id,
        name="Resize",
        resource_id=resource_id,
        resource_type=resource_type,
        compartment_id="ocid1.compartment.test",
        compartment_name="test",
        action={"ocpus": 4},
        lifecycle_state="ACTIVE",
        status="PENDING",
        native_estimated_savings=50.0,
        currency="USD",
        time_created=START,
        time_updated=NOW,
        time_status_begin=START,
        time_status_end=None,
        scope_match="in",
    )


def advisor(recommendations=None, actions=None, *, status="success", errors=None):
    recs = list(recommendations or [])
    acts = list(actions or [])
    return OciCloudAdvisorResult(
        status=status,
        recommendations=recs,
        resource_actions=acts,
        recommendation_count=len(recs),
        resource_action_count=len(acts),
        warnings=[],
        errors=list(errors or []),
        started_at=START,
        completed_at=NOW,
        coverage={
            "recommendations": status == "success",
            "resource_actions": status == "success",
        },
        pages={},
    )


def usage_record(resource_id, cost, currency="USD", *, sku="SKU-A", start=START, end=NOW):
    return OciUsageRecord(
        start_time=start,
        end_time=end,
        resource_id=resource_id,
        service="Compute",
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.test",
        sku_name=sku,
        sku_part_number=sku,
        unit="OCPU hour",
        usage_quantity=Decimal("1"),
        actual_cost=Decimal(cost),
        currency=currency,
        scope_match="in",
    )


def usage(records=None, sku_records=None, *, status="success", start=START, end=NOW):
    records = list(records or [])
    totals = {}
    for row in records:
        if row.actual_cost is not None and row.currency is not None:
            totals[row.currency] = totals.get(row.currency, Decimal("0")) + row.actual_cost
    return OciUsageResult(
        status=status,
        period_start=start,
        period_end=end,
        records=records,
        sku_usage_records=list(sku_records or []),
        totals_by_currency=totals,
        warnings=[],
        errors=[],
        coverage={"usage": status == "success"},
        pages={},
        request_count=1,
        started_at=start,
        completed_at=end,
    )


def metric_series(
    resource_id,
    metric="CpuUtilization",
    *,
    statistic="mean",
    start=START,
    end=NOW,
):
    return OciMetricSeries(
        namespace="oci_computeagent",
        metric_name=metric,
        resource_id=resource_id,
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.test",
        dimensions={} if resource_id is None else {"resourceId": resource_id},
        unit="percent",
        period_start=start,
        period_end=end,
        statistic=statistic,
        interval="1h",
        datapoints=[OciMetricDatapoint(timestamp=end, value=10.0)],
        coverage="complete",
    )


def metric_summary(resource_id, *, coverage="complete"):
    return OciResourceMetrics(
        resource_id=resource_id,
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.test",
        lifecycle_state="RUNNING",
        resource_created_at=START,
        cpu_mean=7.0,
        cpu_p95=14.0,
        cpu_max=52.0,
        memory_mean=20.0,
        memory_p95=31.0,
        memory_max=40.0,
        sample_counts={"cpu_mean": 720},
        missing_metrics=[] if coverage == "complete" else ["memory"],
        coverage=coverage,
        coverage_reasons=[] if coverage == "complete" else ["memory_query_incomplete"],
        metrics_available=True,
    )


def monitoring(
    resources=None,
    series=None,
    orphan=None,
    *,
    status="success",
    start=START,
    end=NOW,
    errors=None,
):
    return OciMonitoringResult(
        status=status,
        period_start=start,
        period_end=end,
        interval="1h",
        series=list(series or []),
        resources=list(resources or []),
        orphan_series=list(orphan or []),
        warnings=[],
        errors=list(errors or []),
        coverage={"cpu": status == "success", "memory": status == "success"},
        request_count=1,
        started_at=start,
        completed_at=end,
    )


def correlate(d=None, a=None, u=None, m=None):
    return correlate_oci_datasets(
        d or discovery(),
        a or advisor(),
        u or usage(),
        m or monitoring(),
    )


def test_inventory_is_anchor_and_exact_ocid_is_only_identity_key():
    first = resource("ocid1.instance.a", name="APP01")
    second = resource("ocid1.instance.b", name="APP01")
    result = correlate(
        discovery([first, second]),
        advisor([recommendation()], [action(resource_id="ocid1.instance.a")]),
    )
    assert [item.resource_id for item in result.resource_contexts] == [
        "ocid1.instance.a",
        "ocid1.instance.b",
    ]
    assert len(result.resource_contexts[0].native_recommendations) == 1
    assert result.resource_contexts[1].native_recommendations == []


def test_same_ocid_correlates_with_different_names_and_unknown_resource_type():
    rid = "ocid1.autonomousdatabase.a"
    result = correlate(
        discovery([resource(rid, name="inventory-name", resource_type="autonomousdatabase")]),
        advisor(
            [recommendation()],
            [action(resource_id=rid, resource_type="autonomousdatabase")],
        ),
    )
    assert result.resource_contexts[0].resource_type == "autonomousdatabase"
    assert result.resource_contexts[0].name == "inventory-name"


def test_full_context_preserves_all_sources_relationships_and_provenance():
    rid = "ocid1.instance.a"
    volume = "ocid1.volume.a"
    relationship = OciResourceRelationship(
        relation_type="attached_volume",
        source_id=rid,
        target_id=volume,
        source_type="compute_instance",
        target_type="block_volume",
    )
    result = correlate(
        discovery(
            [resource(rid), resource(volume, resource_type="block_volume")],
            relationships=[relationship],
        ),
        advisor([recommendation()], [action(resource_id=rid)]),
        usage(
            [usage_record(rid, "310")],
            [usage_record(rid, "310", sku="SKU-A")],
        ),
        monitoring([metric_summary(rid)], [metric_series(rid)]),
    )
    context = next(item for item in result.resource_contexts if item.resource_id == rid)
    assert context.lifecycle_state == "RUNNING"
    assert context.relationships == [relationship]
    assert context.native_recommendations[0].recommendation.recommendation_id == "rec-1"
    assert context.usage.totals_by_currency == {"USD": Decimal("310")}
    assert context.monitoring.summary.cpu_p95 == 14.0
    assert context.provenance["inventory"] == ("compute_api",)
    assert context.provenance["advisor"] == ("oci_cloud_advisor",)


def test_multiple_recommendations_preserve_resource_action_parent_and_native_status():
    rid = "ocid1.instance.a"
    rec1 = recommendation("rec-1", status="ACTIVE")
    rec2 = recommendation("rec-2", status="DISMISSED")
    result = correlate(
        discovery([resource(rid)]),
        advisor(
            [rec2, rec1],
            [
                action("a2", rec_id="rec-2", resource_id=rid),
                action("a1", rec_id="rec-1", resource_id=rid),
            ],
        ),
    )
    links = result.resource_contexts[0].native_recommendations
    assert [link.action.resource_action_id for link in links] == ["a1", "a2"]
    assert [link.recommendation.status for link in links] == ["ACTIVE", "DISMISSED"]


def test_data_without_resource_id_stays_account_level_without_synthetic_ocid():
    rec = recommendation("account-rec")
    no_resource = action("account-action", rec_id="account-rec", resource_id=None)
    usage_row = usage_record(None, "75")
    series = metric_series(None)
    result = correlate(
        a=advisor([rec], [no_resource]),
        u=usage([usage_row]),
        m=monitoring(series=[series]),
    )
    assert result.resource_contexts == []
    assert result.account_context.recommendations == [rec]
    assert result.account_context.resource_actions_without_resource_id == [no_resource]
    assert result.account_context.usage_records_without_resource_id == [usage_row]
    assert result.account_context.metric_series_without_resource_id == [series]


def test_resource_absent_from_inventory_is_preserved_as_unmatched_context():
    deleted = "ocid1.instance.deleted"
    result = correlate(
        u=usage([usage_record(deleted, "12")]),
        a=advisor([recommendation()], [action(resource_id=deleted)]),
        m=monitoring(orphan=[metric_series(deleted)]),
    )
    context = result.resource_contexts[0]
    assert context.resource_id == deleted
    assert context.has_inventory is False
    assert result.unmatched_resource_ids_by_source == {
        "advisor": (deleted,),
        "usage": (deleted,),
        "monitoring": (deleted,),
    }


def test_usage_preserves_skus_negative_zero_and_currency_safe_totals():
    rid = "ocid1.instance.a"
    rows = [
        usage_record(rid, "100", "USD", sku="A"),
        usage_record(rid, "-10", "USD", sku="B"),
        usage_record(rid, "0", "BRL", sku="C"),
        usage_record(rid, "50", "BRL", sku="D"),
    ]
    result = correlate(d=discovery([resource(rid)]), u=usage(rows, rows))
    context = result.resource_contexts[0]
    assert context.usage.totals_by_currency == {
        "BRL": Decimal("50"),
        "USD": Decimal("90"),
    }
    assert len(context.usage.records) == 4
    assert len(context.usage.sku_usage_records) == 4


def test_monitoring_preserves_multiple_series_partial_coverage_and_missing_memory():
    rid = "ocid1.instance.a"
    summary = metric_summary(rid, coverage="partial")
    summary.memory_mean = None
    summary.memory_p95 = None
    series = [
        metric_series(rid, "CpuUtilization", statistic="mean"),
        metric_series(rid, "CpuUtilization", statistic="max"),
        metric_series(rid, "NetworksBytesIn", statistic="increment"),
    ]
    result = correlate(
        d=discovery([resource(rid)]),
        m=monitoring([summary], series),
    )
    context = result.resource_contexts[0]
    assert len(context.monitoring.series) == 3
    assert context.monitoring.summary.coverage == "partial"
    assert context.monitoring.summary.memory_mean is None


def test_temporal_alignment_exact_overlapping_and_disjoint():
    exact = correlate()
    overlap = correlate(
        u=usage(start=START, end=NOW),
        m=monitoring(start=START + timedelta(days=1), end=NOW + timedelta(days=1)),
    )
    disjoint = correlate(
        u=usage(start=START, end=START + timedelta(days=1)),
        m=monitoring(start=NOW - timedelta(days=1), end=NOW),
    )
    assert exact.time_alignment == "exact"
    assert overlap.time_alignment == "overlapping"
    assert disjoint.time_alignment == "disjoint"


def test_source_failures_remain_distinct_from_empty_datasets_and_coverage_is_partial():
    advisor_error = OciCloudAdvisorIssue(
        category="authorization_failed",
        source="optimizer",
        operation="list",
        message="denied",
    )
    monitoring_error = OciMonitoringIssue(
        category="authorization_failed",
        source="monitoring",
        operation="query",
        message="denied",
    )
    failed_advisor = advisor(status="failed", errors=[advisor_error])
    partial_monitoring = monitoring(status="partial", errors=[monitoring_error])
    result = correlate(
        d=discovery([resource("ocid1.instance.a")]),
        a=failed_advisor,
        m=partial_monitoring,
    )
    assert result.status == "partial"
    assert result.coverage["advisor"].status == "failed"
    assert result.source_errors["advisor"] == (advisor_error,)
    assert result.source_errors["monitoring"] == (monitoring_error,)
    assert result.resource_contexts[0].coverage["advisor"] == "unavailable"


def test_discovery_partial_is_preserved_in_context_coverage():
    error = OciDiscoveryIssue(
        category="authorization_failed",
        source="compute_api",
        operation="list_instances",
        message="denied",
    )
    result = correlate(
        d=discovery([resource("ocid1.instance.a")], status="partial", errors=[error])
    )
    assert result.coverage["inventory"].status == "partial"
    assert result.resource_contexts[0].coverage["inventory"] == "partial"


def test_inventory_advisor_conflict_preserves_both_facts_and_warning():
    rid = "ocid1.instance.a"
    result = correlate(
        d=discovery([resource(rid, resource_type="compute_instance")]),
        a=advisor(
            [recommendation()],
            [action(resource_id=rid, resource_type="block_volume")],
        ),
    )
    context = result.resource_contexts[0]
    assert context.resource_type == "compute_instance"
    assert context.native_recommendations[0].action.resource_type == "block_volume"
    assert context.warnings[0].category == "resource_type_conflict"


def test_determinism_order_independence_and_exact_duplicate_deduplication():
    rid = "ocid1.instance.a"
    recs = [recommendation("r2"), recommendation("r1")]
    actions = [
        action("a2", rec_id="r2", resource_id=rid),
        action("a1", rec_id="r1", resource_id=rid),
    ]
    rows = [usage_record(rid, "1", sku="A"), usage_record(rid, "2", sku="B")]
    series = [
        metric_series(rid, "MemoryUtilization"),
        metric_series(rid, "CpuUtilization"),
    ]
    first = correlate(
        discovery([resource(rid)]),
        advisor(recs, actions),
        usage(rows + [rows[0]]),
        monitoring([metric_summary(rid)], series + [series[0]]),
    )
    second = correlate(
        discovery([resource(rid)]),
        advisor(list(reversed(recs)), list(reversed(actions))),
        usage(list(reversed(rows)) + [rows[0]]),
        monitoring([metric_summary(rid)], list(reversed(series)) + [series[0]]),
    )
    assert first == second
    assert len(first.resource_contexts[0].usage.records) == 2
    assert len(first.resource_contexts[0].monitoring.series) == 2


def test_inputs_are_not_mutated_and_no_decision_entities_are_created():
    rid = "ocid1.instance.a"
    inputs = (
        discovery([resource(rid)]),
        advisor([recommendation()], [action(resource_id=rid)]),
        usage([usage_record(rid, "10")]),
        monitoring([metric_summary(rid)], [metric_series(rid)]),
    )
    before = deepcopy(inputs)
    result = correlate_oci_datasets(*inputs)
    assert inputs == before
    rendered = repr(result).lower()
    for forbidden in (
        "opportunity",
        "finding",
        "confidence",
        "severity",
        "deepops_estimated_savings",
    ):
        assert forbidden not in rendered


def test_large_dataset_uses_indexed_resource_identity_and_preserves_1000_resources():
    count = 1000
    resources = [resource(f"ocid1.instance.{index}") for index in range(count)]
    rows = [usage_record(f"ocid1.instance.{index}", "1") for index in range(count)]
    metrics = [metric_summary(f"ocid1.instance.{index}") for index in range(count)]
    actions = [
        action(f"action-{index}", resource_id=f"ocid1.instance.{index}") for index in range(count)
    ]
    result = correlate(
        discovery(resources),
        advisor([recommendation()], actions),
        usage(rows),
        monitoring(metrics),
    )
    assert len(result.resource_contexts) == count
    assert result.resource_contexts[0].resource_id == "ocid1.instance.0"
    assert result.resource_contexts[-1].resource_id == "ocid1.instance.999"


def test_source_freshness_comes_from_source_timestamps_not_wall_clock():
    result = correlate()
    assert result.source_freshness == {
        "inventory": NOW,
        "advisor": NOW,
        "usage": NOW,
        "monitoring": NOW,
    }
