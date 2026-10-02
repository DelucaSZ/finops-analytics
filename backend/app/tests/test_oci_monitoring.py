from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import oci
import pytest
from requests import exceptions as requests_exceptions

from app.services.collection_executors import has_collection_executor
from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_clients import OciClientFactory
from app.services.oci_credentials import OciCredentialResolutionError
from app.services.oci_monitoring import (
    COMPUTE_NAMESPACE,
    DEFAULT_INTERVAL,
    OciMonitoringService,
    build_compute_query,
    default_monitoring_window,
    validate_monitoring_window,
)
from app.services.provider_capabilities import get_provider_capabilities

TENANCY = "ocid1.tenancy.oc1..example"
COMP_A = "ocid1.compartment.oc1..a"
COMP_B = "ocid1.compartment.oc1..b"
REGION = "sa-saopaulo-1"
OTHER_REGION = "us-ashburn-1"
PRIVATE_KEY = "PRIVATE-KEY-MONITORING-MARKER"
PASSPHRASE = "MONITORING-PASSPHRASE-MARKER"


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def snapshot(*, regions=(REGION,), compartments=(COMP_A,)):
    return OciConnectionSnapshot(
        cloud_account_id=7,
        configuration_revision=1,
        tenancy_ocid=TENANCY,
        user_ocid="ocid1.user.oc1..example",
        fingerprint="aa:bb",
        region=REGION,
        scope_regions=tuple(regions),
        compartment_ocids=tuple(compartments),
        include_root_compartment=False,
        include_subcompartments=False,
        private_key_pem=PRIVATE_KEY,
        private_key_password=PASSPHRASE,
    )


def compute_resource(
    resource_id,
    *,
    region=REGION,
    compartment=COMP_A,
    state="RUNNING",
    created_at=None,
    name="compute",
):
    attrs = {}
    if created_at is not None:
        attrs["time_created"] = created_at.isoformat()
    return obj(
        resource_id=resource_id,
        resource_type="compute_instance",
        region=region,
        compartment_id=compartment,
        lifecycle_state=state,
        name=name,
        attributes=attrs,
    )


def inventory(resources):
    return obj(resources=resources)


def metric_data(
    metric_name,
    resource_id,
    values,
    *,
    compartment=COMP_A,
    unit="percent",
    start=datetime(2026, 9, 2, tzinfo=UTC),
):
    points = [
        obj(timestamp=start + timedelta(hours=index + 1), value=value)
        for index, value in enumerate(values)
    ]
    return obj(
        namespace=COMPUTE_NAMESPACE,
        name=metric_name,
        compartment_id=compartment,
        dimensions={"resourceId": resource_id},
        metadata={"unit": unit},
        aggregated_datapoints=points,
    )


def service_error(status, code="Error"):
    return oci.exceptions.ServiceError(status, code, {}, "raw-sensitive-monitoring-message")


class FakeMonitoringClient:
    def __init__(self, data=None, errors=None):
        self.data = data or {}
        self.errors = errors or {}
        self.calls = []

    def summarize_metrics_data(self, compartment_id, details):
        self.calls.append((compartment_id, details))
        for token, error in self.errors.items():
            if token in details.query:
                raise error
        return obj(data=list(self.data.get(details.query, [])))


class FakeFactory:
    clients = {}
    seen_regions = []

    def __init__(self, _snapshot):
        pass

    def monitoring(self, region):
        self.seen_regions.append(region)
        return self.clients[region]


def query(metric, statistic):
    return build_compute_query(metric, statistic)


def run(
    clients,
    *,
    resources=None,
    snap=None,
    start=None,
    end=None,
):
    snap = snap or snapshot()
    FakeFactory.clients = clients
    FakeFactory.seen_regions = []
    service = OciMonitoringService(
        credential_resolver=lambda _db, _id: snap,
        client_factory_cls=FakeFactory,
    )
    kwargs = {}
    if start is not None or end is not None:
        kwargs.update(start_time=start, end_time=end)
    return service.collect_account(
        None,
        7,
        inventory=inventory(resources or []),
        now=datetime(2026, 10, 2, 12, tzinfo=UTC),
        **kwargs,
    )


def test_default_window_is_30_days_and_timezone_aware():
    start, end = default_monitoring_window(datetime(2026, 10, 2, 12, tzinfo=UTC))
    assert start == datetime(2026, 9, 2, 12, tzinfo=UTC)
    assert end == datetime(2026, 10, 2, 12, tzinfo=UTC)


def test_custom_window_normalizes_to_utc_and_rejects_invalid_boundaries():
    start, end = validate_monitoring_window(
        datetime.fromisoformat("2026-09-01T00:00:00-03:00"),
        datetime.fromisoformat("2026-10-01T00:00:00-03:00"),
    )
    assert start.tzinfo is UTC
    assert end.tzinfo is UTC

    with pytest.raises(ValueError):
        validate_monitoring_window(datetime(2026, 9, 1), datetime(2026, 10, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        validate_monitoring_window(
            datetime(2026, 10, 2, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
        )


def test_query_builders_use_group_by_resource_and_validated_fixed_vocabulary():
    assert query("CpuUtilization", "mean") == "CpuUtilization[1h].groupBy(resourceId).mean()"
    assert query("MemoryUtilization", "max") == "MemoryUtilization[1h].groupBy(resourceId).max()"
    assert query("NetworksBytesIn", "increment").endswith(".increment()")
    assert PRIVATE_KEY not in query("CpuUtilization", "mean")
    with pytest.raises(ValueError):
        build_compute_query('CpuUtilization{resourceId="unsafe"}', "mean")


def test_cpu_mean_max_and_local_p95_use_returned_hourly_points():
    rid = "ocid1.instance.cpu"
    client = FakeMonitoringClient(
        {
            query("CpuUtilization", "mean"): [metric_data("CpuUtilization", rid, [10, 20, 30, 40])],
            query("CpuUtilization", "max"): [metric_data("CpuUtilization", rid, [30, 50, 60, 70])],
        }
    )
    result = run({REGION: client}, resources=[compute_resource(rid)])
    resource = result.resources[0]
    assert resource.cpu_mean == pytest.approx(25.0)
    assert resource.cpu_p95 == pytest.approx(38.5)
    assert resource.cpu_max == 70
    assert resource.sample_counts["cpu_mean"] == 4


def test_memory_and_network_are_normalized_without_inventing_percent_capacity():
    rid = "ocid1.instance.metrics"
    client = FakeMonitoringClient(
        {
            query("MemoryUtilization", "mean"): [
                metric_data("MemoryUtilization", rid, [40, 50], unit="percent")
            ],
            query("MemoryUtilization", "max"): [
                metric_data("MemoryUtilization", rid, [55, 65], unit="percent")
            ],
            query("NetworksBytesIn", "increment"): [
                metric_data("NetworksBytesIn", rid, [100, 200], unit="bytes")
            ],
            query("NetworksBytesOut", "increment"): [
                metric_data("NetworksBytesOut", rid, [50, 75], unit="bytes")
            ],
        }
    )
    result = run({REGION: client}, resources=[compute_resource(rid)])
    resource = result.resources[0]
    assert resource.memory_mean == 45
    assert resource.memory_p95 == pytest.approx(49.5)
    assert resource.memory_max == 65
    assert resource.network_in_total_bytes == 300
    assert resource.network_out_total_bytes == 125
    units = {series.metric_name: series.unit for series in result.series}
    assert units["NetworksBytesIn"] == "bytes"


def test_missing_metric_is_none_not_zero_and_stopped_reason_is_factual():
    rid = "ocid1.instance.stopped"
    result = run(
        {REGION: FakeMonitoringClient()},
        resources=[compute_resource(rid, state="STOPPED")],
    )
    resource = result.resources[0]
    assert resource.cpu_mean is None
    assert resource.cpu_p95 is None
    assert resource.metrics_available is False
    assert resource.coverage == "unavailable"
    assert "resource_not_running" in resource.coverage_reasons


def test_recent_resource_preserves_reduced_window_reason_without_zero_fill():
    rid = "ocid1.instance.new"
    created = datetime(2026, 9, 30, tzinfo=UTC)
    client = FakeMonitoringClient(
        {
            query("CpuUtilization", "mean"): [metric_data("CpuUtilization", rid, [25])],
            query("CpuUtilization", "max"): [metric_data("CpuUtilization", rid, [30])],
        }
    )
    result = run(
        {REGION: client},
        resources=[compute_resource(rid, created_at=created)],
    )
    resource = result.resources[0]
    assert "resource_created_within_window" in resource.coverage_reasons
    assert resource.cpu_mean == 25


def test_orphan_series_is_preserved_and_correlation_uses_resource_id_not_name():
    found = "ocid1.instance.found"
    orphan = "ocid1.instance.removed"
    rows = [
        metric_data("CpuUtilization", found, [10]),
        metric_data("CpuUtilization", orphan, [20]),
    ]
    client = FakeMonitoringClient({query("CpuUtilization", "mean"): rows})
    result = run(
        {REGION: client},
        resources=[
            compute_resource(found, name="duplicate"),
            compute_resource("ocid1.instance.other", name="duplicate"),
        ],
    )
    assert any(item.resource_id == orphan for item in result.orphan_series)
    matches = {item.resource_id: item.inventory_match for item in result.series}
    assert matches[found] is True
    assert matches[orphan] is False


def test_multiple_regions_and_compartments_drive_requests_not_resource_count():
    resources = [
        compute_resource(
            f"ocid1.instance.{index}",
            region=REGION if index % 2 == 0 else OTHER_REGION,
            compartment=COMP_A if index % 3 else COMP_B,
        )
        for index in range(100)
    ]
    clients = {
        REGION: FakeMonitoringClient(),
        OTHER_REGION: FakeMonitoringClient(),
    }
    result = run(
        clients,
        resources=resources,
        snap=snapshot(regions=(REGION, OTHER_REGION), compartments=(COMP_A, COMP_B)),
    )
    assert result.request_count == 2 * 2 * 6
    assert sum(len(client.calls) for client in clients.values()) == 24
    assert result.request_count < len(resources)


def test_region_outside_scope_is_never_queried():
    client = FakeMonitoringClient()
    run({REGION: client}, snap=snapshot(regions=(REGION,)))
    assert FakeFactory.seen_regions == [REGION]
    assert OTHER_REGION not in FakeFactory.seen_regions


def test_permission_failure_is_partial_and_never_becomes_zero_utilization():
    rid = "ocid1.instance.permission"
    client = FakeMonitoringClient(
        data={
            query("CpuUtilization", "mean"): [metric_data("CpuUtilization", rid, [20, 30])],
            query("CpuUtilization", "max"): [metric_data("CpuUtilization", rid, [35, 45])],
        },
        errors={"MemoryUtilization": service_error(403, "NotAuthorized")},
    )
    result = run({REGION: client}, resources=[compute_resource(rid)])
    resource = result.resources[0]
    assert result.status == "partial"
    assert resource.cpu_mean == 25
    assert resource.memory_mean is None
    assert any(error.category == "authorization_failed" for error in result.errors)
    assert "memory_query_incomplete" in resource.coverage_reasons


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (service_error(429, "TooManyRequests"), "service_throttled"),
        (service_error(503, "ServiceUnavailable"), "service_unavailable"),
        (requests_exceptions.Timeout("sensitive timeout"), "timeout"),
    ],
)
def test_transient_monitoring_failures_are_structured_and_sanitized(error, category):
    client = FakeMonitoringClient(errors={"CpuUtilization": error})
    result = run({REGION: client})
    assert result.status == "partial"
    assert any(item.category == category for item in result.errors)
    assert "raw-sensitive-monitoring-message" not in repr(result)
    assert "sensitive timeout" not in repr(result)


def test_authentication_failure_is_fatal_without_connection_status_side_effects():
    client = FakeMonitoringClient(errors={"CpuUtilization": service_error(401, "NotAuthenticated")})
    result = run({REGION: client})
    assert result.status == "failed"
    assert any(item.fatal and item.category == "authentication_failed" for item in result.errors)
    assert not hasattr(result, "connection_status")


def test_credential_failure_stops_before_client_creation():
    class FailFactory:
        def __init__(self, _snapshot):
            pytest.fail("client factory should not be created")

    def resolver(_db, _id):
        raise OciCredentialResolutionError("configuration_missing", "OCI config missing")

    result = OciMonitoringService(
        credential_resolver=resolver,
        client_factory_cls=FailFactory,
    ).collect_account(None, 7)
    assert result.status == "failed"
    assert result.errors[0].category == "configuration_missing"


def test_result_never_contains_credentials_signer_or_secrets():
    rid = "ocid1.instance.safe"
    result = run(
        {
            REGION: FakeMonitoringClient(
                {query("CpuUtilization", "mean"): [metric_data("CpuUtilization", rid, [10])]}
            )
        },
        resources=[compute_resource(rid)],
    )
    rendered = repr(result)
    assert PRIVATE_KEY not in rendered
    assert PASSPHRASE not in rendered
    assert "fingerprint" not in rendered.lower()
    assert "signer" not in rendered.lower()


def test_client_factory_caches_monitoring_client_per_region(monkeypatch):
    created = []

    class DummyClient:
        def __init__(self, config, **kwargs):
            created.append((config["region"], kwargs))

    monkeypatch.setattr(oci.monitoring, "MonitoringClient", DummyClient)
    factory = OciClientFactory(snapshot())

    first = factory.monitoring(REGION)
    second = factory.monitoring(REGION)
    third = factory.monitoring(OTHER_REGION)

    assert first is second
    assert third is not first
    assert len(created) == 2
    assert PRIVATE_KEY not in repr(factory)


def test_capabilities_executor_and_public_collection_remain_disabled():
    capabilities = get_provider_capabilities("oci")
    assert capabilities.manual_collection is False
    assert capabilities.scheduling is False
    assert capabilities.finops_policies is False
    assert has_collection_executor("oci") is False
    assert has_collection_executor("aws") is True


def test_result_contract_contains_no_deepops_decision_entities():
    result = run({REGION: FakeMonitoringClient()})
    rendered = repr(result).lower()
    for forbidden in ("opportunityobservation", "collectedfinding", "rightsizing", "saving"):
        assert forbidden not in rendered
    assert DEFAULT_INTERVAL == "1h"
