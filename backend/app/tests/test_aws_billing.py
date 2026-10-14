from datetime import date
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from app.models.account import AwsAccount, CloudAccount
from app.schemas.billing import (
    AwsBillingRequest,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
)
from app.services.aws_billing import AwsBillingService, BillingQueryCache, BillingServiceError
from app.services.aws_cost_explorer import (
    AwsBillingUpstreamError,
    AwsCostExplorerClient,
    CostExplorerPages,
    build_cost_and_usage_query,
)


def _query(**overrides):
    values = {
        "start_date": "2026-10-01",
        "end_date": "2026-10-15",
        "granularity": BillingGranularity.DAILY,
        "metric": BillingMetric.AMORTIZED_COST,
        "group_by": BillingGroupBy.NONE,
        "exclude_record_types": ("Credit",),
        "linked_account_id": None,
    }
    values.update(overrides)
    return build_cost_and_usage_query(**values)


def test_query_builder_daily_amortized_and_credit_exclusion():
    query = _query(linked_account_id="111111111111")

    assert query["TimePeriod"] == {"Start": "2026-10-01", "End": "2026-10-15"}
    assert query["Granularity"] == "DAILY"
    assert query["Metrics"] == ["AmortizedCost"]
    assert query["Filter"] == {
        "And": [
            {"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": ["111111111111"]}},
            {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit"]}}},
        ]
    }


@pytest.mark.parametrize(
    ("granularity", "metric", "expected_metric"),
    [
        (BillingGranularity.MONTHLY, BillingMetric.AMORTIZED_COST, "AmortizedCost"),
        (BillingGranularity.DAILY, BillingMetric.UNBLENDED_COST, "UnblendedCost"),
        (BillingGranularity.DAILY, BillingMetric.NET_AMORTIZED_COST, "NetAmortizedCost"),
    ],
)
def test_query_builder_supported_granularity_and_metrics(
    granularity,
    metric,
    expected_metric,
):
    query = _query(granularity=granularity, metric=metric)
    assert query["Granularity"] == granularity.value
    assert query["Metrics"] == [expected_metric]


@pytest.mark.parametrize(
    ("group_by", "dimension"),
    [
        (BillingGroupBy.SERVICE, "SERVICE"),
        (BillingGroupBy.ACCOUNT, "LINKED_ACCOUNT"),
    ],
)
def test_query_builder_grouping(group_by, dimension):
    query = _query(group_by=group_by)
    assert query["GroupBy"] == [{"Type": "DIMENSION", "Key": dimension}]


def test_query_builder_without_grouping_has_no_group_by():
    assert "GroupBy" not in _query()


class _PagedClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def get_cost_and_usage(self, **request):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_cost_explorer_client_consumes_all_pages():
    low_level = _PagedClient(
        [
            {"ResultsByTime": [], "NextPageToken": "page-2"},
            {"ResultsByTime": []},
        ]
    )
    result = AwsCostExplorerClient(client=low_level).get_cost_and_usage(_query())

    assert result.aws_request_count == 2
    assert len(result.pages) == 2
    assert "NextPageToken" not in low_level.requests[0]
    assert low_level.requests[1]["NextPageToken"] == "page-2"


def test_cost_explorer_client_rejects_repeated_pagination_token():
    low_level = _PagedClient(
        [
            {"ResultsByTime": [], "NextPageToken": "same"},
            {"ResultsByTime": [], "NextPageToken": "same"},
        ]
    )
    with pytest.raises(AwsBillingUpstreamError, match="token") as error:
        AwsCostExplorerClient(client=low_level).get_cost_and_usage(_query())
    assert error.value.code == "PAGINATION_ERROR"


def test_cost_explorer_access_denied_is_normalized():
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "secret upstream detail"}},
        "GetCostAndUsage",
    )
    low_level = _PagedClient([error])

    with pytest.raises(AwsBillingUpstreamError) as normalized:
        AwsCostExplorerClient(client=low_level).get_cost_and_usage(_query())

    assert normalized.value.code == "ACCESS_DENIED"
    assert "secret upstream detail" not in normalized.value.safe_message


class _FakeDb:
    def __init__(self, accounts):
        self.accounts = accounts

    def scalars(self, _statement):
        return self.accounts


def _account(account_id: int, aws_id: str, name: str, *, management: bool = False):
    cloud = CloudAccount(
        id=account_id,
        provider="aws",
        native_account_id=aws_id,
        name=name,
        enabled=True,
    )
    cloud.aws_configuration = AwsAccount(
        id=account_id,
        cloud_account_id=account_id,
        name=name,
        aws_account_id=aws_id,
        enabled=True,
        role_arn=f"arn:aws:iam::{aws_id}:role/NuvemIQReadOnly",
        external_id=f"external-{account_id}-0123456789",
        regions=["sa-east-1"],
        is_management_account=management,
    )
    return cloud


def _request(
    account_ids=(1,),
    *,
    start=date(2026, 10, 1),
    end=date(2026, 10, 4),
    granularity=BillingGranularity.DAILY,
    metric=BillingMetric.AMORTIZED_COST,
    group_by=BillingGroupBy.NONE,
):
    return AwsBillingRequest(
        account_ids=list(account_ids),
        start_date=start,
        end_date=end,
        granularity=granularity,
        metric=metric,
        group_by=group_by,
        exclude_record_types=["Credit"],
    )


def _bucket(start, end, amount, currency="USD", *, estimated=False):
    return {
        "TimePeriod": {"Start": start, "End": end},
        "Total": {
            "AmortizedCost": {"Amount": str(amount), "Unit": currency},
            "UnblendedCost": {"Amount": str(amount), "Unit": currency},
            "NetAmortizedCost": {"Amount": str(amount), "Unit": currency},
        },
        "Estimated": estimated,
    }


class _ServiceClient:
    def __init__(self, pages=None, error=None):
        self.pages = tuple(pages or ())
        self.error = error
        self.queries = []

    def get_cost_and_usage(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return CostExplorerPages(self.pages, 1)


def _service(accounts, clients):
    return AwsBillingService(
        _FakeDb(accounts),
        cache=BillingQueryCache(),
        session_factory=lambda configuration: configuration.aws_account_id,
        client_factory=lambda aws_id: clients[aws_id],
        today_factory=lambda: date(2026, 10, 14),
    )


def test_service_summary_uses_decimal_preserves_currency_and_estimated():
    account = _account(1, "111111111111", "Prod")
    client = _ServiceClient(
        [
            {
                "ResultsByTime": [
                    _bucket("2026-10-01", "2026-10-02", "10.123456", estimated=False),
                    _bucket("2026-10-02", "2026-10-03", "20.000001", estimated=True),
                ]
            }
        ]
    )
    response = _service([account], {account.native_account_id: client}).summary(_request())

    assert response.totals[0].amount == Decimal("30.123457")
    assert response.totals[0].currency == "USD"
    assert response.totals[0].estimated is True


def test_service_timeseries_fills_missing_bucket_when_currency_is_known():
    account = _account(1, "111111111111", "Prod")
    client = _ServiceClient(
        [
            {
                "ResultsByTime": [
                    _bucket("2026-10-01", "2026-10-02", "10"),
                    _bucket("2026-10-03", "2026-10-04", "30"),
                ]
            }
        ]
    )
    response = _service([account], {account.native_account_id: client}).timeseries(_request())

    assert [(point.start_date, point.amount) for point in response.points] == [
        (date(2026, 10, 1), Decimal("10")),
        (date(2026, 10, 2), Decimal("0")),
        (date(2026, 10, 3), Decimal("30")),
    ]


def test_service_keeps_mixed_currencies_separate():
    account_a = _account(1, "111111111111", "A")
    account_b = _account(2, "222222222222", "B")
    clients = {
        account_a.native_account_id: _ServiceClient(
            [{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "10", "USD")]}]
        ),
        account_b.native_account_id: _ServiceClient(
            [{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "20", "BRL")]}]
        ),
    }

    response = _service([account_a, account_b], clients).summary(_request((1, 2)))

    assert [(item.currency, item.amount) for item in response.totals] == [
        ("BRL", Decimal("20")),
        ("USD", Decimal("10")),
    ]


def test_management_account_is_filtered_to_its_registered_linked_account():
    management = _account(1, "111111111111", "Payer", management=True)
    member = _account(2, "222222222222", "Member")
    clients = {
        management.native_account_id: _ServiceClient(
            [{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "10")]}]
        ),
        member.native_account_id: _ServiceClient(
            [{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "20")]}]
        ),
    }

    _service([management, member], clients).summary(_request((1, 2)))

    payer_filter = clients[management.native_account_id].queries[0]["Filter"]
    assert payer_filter["And"][0] == {
        "Dimensions": {"Key": "LINKED_ACCOUNT", "Values": ["111111111111"]}
    }
    member_filter = clients[member.native_account_id].queries[0]["Filter"]
    assert member_filter == {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit"]}}}


def test_unknown_internal_account_is_rejected_before_aws_call():
    called = False

    def session_factory(_configuration):
        nonlocal called
        called = True
        raise AssertionError("AWS must not be called")

    service = AwsBillingService(
        _FakeDb([]),
        cache=BillingQueryCache(),
        session_factory=session_factory,
        today_factory=lambda: date(2026, 10, 14),
    )

    with pytest.raises(BillingServiceError) as error:
        service.summary(_request((999,)))

    assert error.value.code == "ACCOUNT_NOT_FOUND"
    assert called is False


def test_future_period_is_rejected_before_aws_call():
    account = _account(1, "111111111111", "Prod")
    client = _ServiceClient([])
    service = _service([account], {account.native_account_id: client})

    with pytest.raises(BillingServiceError) as error:
        service.summary(_request(start=date(2026, 10, 15), end=date(2026, 10, 16)))

    assert error.value.code == "INVALID_PERIOD"
    assert client.queries == []


def test_identical_query_hits_cache_but_metric_change_misses():
    account = _account(1, "111111111111", "Prod")
    client = _ServiceClient([{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "10")]}])
    service = _service([account], {account.native_account_id: client})

    service.summary(_request())
    service.summary(_request())
    service.summary(_request(metric=BillingMetric.UNBLENDED_COST))

    assert len(client.queries) == 2
    assert client.queries[1]["Metrics"] == ["UnblendedCost"]


def test_service_breakdown_by_service_aggregates_accounts_in_same_currency():
    account_a = _account(1, "111111111111", "A")
    account_b = _account(2, "222222222222", "B")

    def grouped(amount):
        return {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-02"},
                    "Estimated": False,
                    "Groups": [
                        {
                            "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                            "Metrics": {"AmortizedCost": {"Amount": str(amount), "Unit": "USD"}},
                        }
                    ],
                }
            ]
        }

    clients = {
        account_a.native_account_id: _ServiceClient([grouped("10")]),
        account_b.native_account_id: _ServiceClient([grouped("20")]),
    }
    response = _service([account_a, account_b], clients).breakdown(
        _request((1, 2), group_by=BillingGroupBy.SERVICE)
    )

    assert len(response.items) == 1
    assert response.items[0].amount == Decimal("30")
    assert response.items[0].currency == "USD"


def test_account_breakdown_maps_registered_account_name():
    account = _account(1, "111111111111", "Prod")
    client = _ServiceClient(
        [
            {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-02"},
                        "Estimated": True,
                        "Groups": [
                            {
                                "Keys": ["111111111111"],
                                "Metrics": {"AmortizedCost": {"Amount": "42", "Unit": "USD"}},
                            }
                        ],
                    }
                ]
            }
        ]
    )
    response = _service([account], {account.native_account_id: client}).breakdown(
        _request(group_by=BillingGroupBy.ACCOUNT)
    )

    item = response.items[0]
    assert item.deepops_account_id == 1
    assert item.aws_account_id == "111111111111"
    assert item.display_name == "Prod"
    assert item.label == "Prod"
    assert item.estimated is True


def test_multi_account_failure_does_not_return_partial_total():
    account_a = _account(1, "111111111111", "A")
    account_b = _account(2, "222222222222", "B")
    clients = {
        account_a.native_account_id: _ServiceClient(
            [{"ResultsByTime": [_bucket("2026-10-01", "2026-10-02", "10")]}]
        ),
        account_b.native_account_id: _ServiceClient(
            error=AwsBillingUpstreamError("ACCESS_DENIED", "denied")
        ),
    }

    with pytest.raises(AwsBillingUpstreamError) as error:
        _service([account_a, account_b], clients).summary(_request((1, 2)))

    assert error.value.code == "ACCESS_DENIED"


def test_record_type_validation_rejects_unknown_value():
    with pytest.raises(ValueError, match="Unsupported AWS record type"):
        AwsBillingRequest(
            account_ids=[1],
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            exclude_record_types=["Credits"],
        )
