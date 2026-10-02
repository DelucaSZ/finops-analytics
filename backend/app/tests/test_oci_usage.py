from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import oci
import pytest

from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_usage import (
    PRIMARY_GROUP_BY,
    SKU_USAGE_GROUP_BY,
    OciUsageService,
    default_usage_window,
    validate_usage_window,
)
from app.services.provider_capabilities import get_provider_capabilities


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def snapshot():
    return OciConnectionSnapshot(
        cloud_account_id=7,
        configuration_revision=1,
        tenancy_ocid="ocid1.tenancy.oc1..example",
        user_ocid="ocid1.user.oc1..example",
        fingerprint="aa:bb",
        region="sa-saopaulo-1",
        scope_regions=("sa-saopaulo-1",),
        compartment_ocids=("ocid1.compartment.oc1..a",),
        include_root_compartment=False,
        include_subcompartments=False,
        private_key_pem="PRIVATE-KEY-MARKER",
        private_key_password="PASSPHRASE-MARKER",
    )


def usage_item(
    *,
    resource_id="ocid1.instance.oc1.sa-saopaulo-1.example",
    service="Compute",
    region="sa-saopaulo-1",
    compartment_id="ocid1.compartment.oc1..a",
    sku_name=None,
    sku_part_number=None,
    unit=None,
    quantity=None,
    cost="1.25",
    currency="USD",
    start=datetime(2026, 9, 1, tzinfo=UTC),
    end=datetime(2026, 9, 2, tzinfo=UTC),
):
    return obj(
        time_usage_started=start,
        time_usage_ended=end,
        resource_id=resource_id,
        resource_name=None,
        service=service,
        region=region,
        compartment_id=compartment_id,
        sku_name=sku_name,
        sku_part_number=sku_part_number,
        unit=unit,
        computed_quantity=quantity,
        computed_amount=cost,
        currency=currency,
        subscription_id=None,
    )


class FakeUsageClient:
    def __init__(self, primary_pages=None, sku_pages=None, primary_error=None, sku_error=None):
        self.primary_pages = [[]] if primary_pages is None else primary_pages
        self.sku_pages = [[]] if sku_pages is None else sku_pages
        self.primary_error = primary_error
        self.sku_error = sku_error
        self.calls = []

    def request_summarized_usages(self, details, page=None):
        group = tuple(details.group_by or [])
        self.calls.append((group, page, details))
        is_primary = group == PRIMARY_GROUP_BY
        pages = self.primary_pages if is_primary else self.sku_pages
        error = self.primary_error if is_primary else self.sku_error
        index = 0 if page is None else int(page.split("-")[-1])
        if error is not None and index >= len(pages):
            raise error
        items = pages[index]
        next_page = f"page-{index + 1}" if index + 1 < len(pages) else None
        headers = {"opc-next-page": next_page} if next_page else {}
        return obj(data=obj(items=items), headers=headers)


class FakeFactory:
    client = None

    def __init__(self, _snapshot):
        pass

    def usage(self, region):
        assert region == "sa-saopaulo-1"
        return self.client


def run(client, *, inventory=None, start=None, end=None):
    FakeFactory.client = client
    service = OciUsageService(
        credential_resolver=lambda _db, _id: snapshot(),
        client_factory_cls=FakeFactory,
    )
    kwargs = {}
    if start is not None or end is not None:
        kwargs.update(start_time=start, end_time=end)
    return service.collect_account(
        None,
        7,
        inventory=inventory,
        now=datetime(2026, 10, 2, 12, tzinfo=UTC),
        **kwargs,
    )


def service_error(status, code="Error"):
    return oci.exceptions.ServiceError(status, code, "raw-sensitive-message", {}, "request-id")


def test_default_window_is_last_30_complete_utc_days():
    start, end = default_usage_window(datetime(2026, 10, 2, 12, 30, tzinfo=UTC))
    assert start == datetime(2026, 9, 2, tzinfo=UTC)
    assert end == datetime(2026, 10, 2, tzinfo=UTC)


def test_custom_window_is_timezone_aware_and_normalized_to_utc():
    start, end = validate_usage_window(
        datetime.fromisoformat("2026-09-01T00:00:00+00:00"),
        datetime.fromisoformat("2026-10-01T00:00:00+00:00"),
    )
    assert start.tzinfo is UTC
    assert end.tzinfo is UTC


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 10, 2, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
        (datetime(2026, 9, 1), datetime(2026, 10, 1, tzinfo=UTC)),
        (datetime(2026, 9, 1, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
        (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
    ],
)
def test_invalid_windows_are_rejected(start, end):
    with pytest.raises(ValueError):
        validate_usage_window(start, end)


def test_empty_period_is_successful_zero_without_invented_currency():
    result = run(FakeUsageClient())
    assert result.status == "success"
    assert result.records == []
    assert result.totals_by_currency == {}
    assert result.total_cost is None
    assert result.currency is None


def test_primary_and_auxiliary_groupings_respect_four_dimension_limit():
    client = FakeUsageClient()
    run(client)
    groups = [call[0] for call in client.calls]
    assert PRIMARY_GROUP_BY in groups
    assert SKU_USAGE_GROUP_BY in groups
    assert all(len(group) <= 4 for group in groups)
    assert all(call[2].query_type == "COST" for call in client.calls)
    assert all(call[2].granularity == "DAILY" for call in client.calls)


def test_three_pages_are_consumed_without_duplication():
    item1 = usage_item(resource_id="r1")
    item2 = usage_item(resource_id="r2")
    item3 = usage_item(resource_id="r3")
    client = FakeUsageClient(primary_pages=[[item1], [item2], [item3]])
    result = run(client)
    assert [r.resource_id for r in result.records] == ["r1", "r2", "r3"]
    assert result.pages["resource_cost"] == 3


def test_duplicate_page_rows_are_deduplicated_by_financial_identity():
    item = usage_item(resource_id="r1")
    result = run(FakeUsageClient(primary_pages=[[item], [item]]))
    assert len(result.records) == 1


def test_resource_cost_zero_negative_and_decimal_precision_are_preserved():
    rows = [
        usage_item(resource_id="positive", cost="10.123456789"),
        usage_item(resource_id="zero", cost="0"),
        usage_item(resource_id="credit", cost="-2.50"),
    ]
    result = run(FakeUsageClient(primary_pages=[rows]))
    by_id = {r.resource_id: r for r in result.records}
    assert by_id["positive"].actual_cost == Decimal("10.123456789")
    assert by_id["zero"].actual_cost == Decimal("0")
    assert by_id["credit"].actual_cost == Decimal("-2.50")
    assert result.totals_by_currency["USD"] == Decimal("7.623456789")


def test_two_currencies_are_never_summed_into_one_total():
    rows = [
        usage_item(resource_id="usd", cost="10", currency="USD"),
        usage_item(resource_id="brl", cost="50", currency="BRL"),
    ]
    result = run(FakeUsageClient(primary_pages=[rows]))
    assert result.totals_by_currency == {"USD": Decimal("10"), "BRL": Decimal("50")}
    assert result.total_cost is None
    assert result.currency is None


def test_missing_currency_is_not_invented_or_added_to_totals():
    result = run(FakeUsageClient(primary_pages=[[usage_item(currency=None, cost="9.9")]]))
    assert result.records[0].currency is None
    assert result.totals_by_currency == {}


def test_sku_and_usage_quantity_are_preserved_only_in_auxiliary_breakdown():
    aux = usage_item(
        resource_id="r1",
        sku_part_number="B123",
        unit="OCPU_HOUR",
        quantity="744.125",
        cost="12.50",
    )
    result = run(FakeUsageClient(sku_pages=[[aux]]))
    assert result.sku_usage_records[0].sku_part_number == "B123"
    assert result.sku_usage_records[0].unit == "OCPU_HOUR"
    assert result.sku_usage_records[0].usage_quantity == Decimal("744.125")
    assert result.totals_by_currency == {}


def test_resource_without_resource_id_is_preserved():
    result = run(FakeUsageClient(primary_pages=[[usage_item(resource_id=None)]]))
    assert len(result.records) == 1
    assert result.records[0].resource_id is None
    assert result.records[0].inventory_match is None


def test_inventory_match_true_false_and_historical_missing_resource():
    inventory = obj(resources=[obj(resource_id="present")])
    rows = [
        usage_item(resource_id="present"),
        usage_item(resource_id="historical"),
    ]
    result = run(FakeUsageClient(primary_pages=[rows]), inventory=inventory)
    by_id = {r.resource_id: r for r in result.records}
    assert by_id["present"].inventory_match is True
    assert by_id["historical"].inventory_match is False


def test_scope_in_out_and_unknown_are_explicit_and_out_of_scope_is_not_totaled():
    rows = [
        usage_item(resource_id="in", cost="10"),
        usage_item(resource_id="out-region", region="us-ashburn-1", cost="20"),
        usage_item(resource_id="out-comp", compartment_id="other", cost="30"),
        usage_item(resource_id="unknown", region=None, cost="40"),
    ]
    result = run(FakeUsageClient(primary_pages=[rows]))
    by_id = {r.resource_id: r for r in result.records}
    assert by_id["in"].scope_match == "in"
    assert by_id["out-region"].scope_match == "out"
    assert by_id["out-comp"].scope_match == "out"
    assert by_id["unknown"].scope_match == "unknown"
    assert result.totals_by_currency["USD"] == Decimal("50")


def test_usage_permission_failure_is_not_reported_as_zero_cost():
    result = run(
        FakeUsageClient(
            primary_pages=[],
            primary_error=service_error(403, "NotAuthorized"),
        )
    )
    assert result.status == "partial"
    assert result.coverage["resource_cost"] is False
    assert result.totals_by_currency == {}
    assert result.total_cost is None
    assert any(e.category == "authorization_failed" for e in result.errors)


@pytest.mark.parametrize(
    "error,category",
    [
        (service_error(429, "TooManyRequests"), "service_throttled"),
        (service_error(500, "InternalError"), "service_unavailable"),
        (service_error(504, "Timeout"), "timeout"),
    ],
)
def test_transient_and_service_failures_are_structured(error, category):
    result = run(FakeUsageClient(primary_pages=[], primary_error=error))
    assert result.status == "partial"
    assert any(e.category == category for e in result.errors)
    assert "raw-sensitive-message" not in repr(result)


def test_401_is_fatal_but_does_not_mutate_account_connection_state():
    result = run(
        FakeUsageClient(
            primary_pages=[],
            primary_error=service_error(401, "NotAuthenticated"),
        )
    )
    assert result.status == "failed"
    assert any(e.fatal and e.category == "authentication_failed" for e in result.errors)


def test_auxiliary_failure_preserves_primary_cost_and_marks_partial():
    primary = usage_item(resource_id="r1", cost="12")
    result = run(
        FakeUsageClient(
            primary_pages=[[primary]],
            sku_pages=[],
            sku_error=service_error(403, "NotAuthorized"),
        )
    )
    assert result.status == "partial"
    assert result.records[0].actual_cost == Decimal("12")
    assert result.coverage["resource_cost"] is True
    assert result.coverage["sku_usage"] is False


def test_100_inventory_resources_do_not_create_per_resource_usage_queries():
    inventory = obj(resources=[obj(resource_id=f"r{i}") for i in range(100)])
    client = FakeUsageClient()
    result = run(client, inventory=inventory)
    assert result.request_count == 2
    assert len(client.calls) == 2


def test_result_never_contains_credentials_or_signer_material():
    result = run(FakeUsageClient(primary_pages=[[usage_item()]]))
    rendered = repr(result)
    assert "PRIVATE-KEY-MARKER" not in rendered
    assert "PASSPHRASE-MARKER" not in rendered
    assert "fingerprint" not in rendered.lower()


def test_oci_public_collection_capabilities_remain_disabled():
    capabilities = get_provider_capabilities("oci")
    assert capabilities.manual_collection is False
    assert capabilities.scheduling is False
    assert capabilities.finops_policies is False
