from datetime import date
from decimal import Decimal

from app.models.account import AwsAccount, CloudAccount
from app.schemas.billing import AwsBillingRequest, BillingGroupBy
from app.services.aws_billing import AwsBillingService, BillingQueryCache
from app.services.aws_cost_explorer import CostExplorerPages


class _FakeDb:
    def __init__(self, accounts):
        self.accounts = accounts

    def scalars(self, _statement):
        return self.accounts


class _Client:
    def __init__(self, pages):
        self.pages = tuple(pages)
        self.queries = []

    def get_cost_and_usage(self, query):
        self.queries.append(query)
        return CostExplorerPages(self.pages, 1)


def _account(account_id: int, aws_id: str, name: str):
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
        is_management_account=False,
    )
    return cloud


def _service(account, client):
    return AwsBillingService(
        _FakeDb([account]),
        cache=BillingQueryCache(),
        session_factory=lambda configuration: configuration.aws_account_id,
        client_factory=lambda _aws_id: client,
        today_factory=lambda: date(2026, 10, 16),
    )


def _request(group_by: BillingGroupBy):
    return AwsBillingRequest(
        account_ids=[1],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        group_by=group_by,
        exclude_record_types=["Credit"],
    )


def test_grouped_timeseries_keeps_periods_groups_totals_and_negative_values():
    account = _account(1, "111111111111", "Prod")
    client = _Client(
        [
            {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-02"},
                        "Estimated": False,
                        "Groups": [
                            {
                                "Keys": ["Amazon EC2"],
                                "Metrics": {"AmortizedCost": {"Amount": "12.5", "Unit": "USD"}},
                            },
                            {
                                "Keys": ["Amazon S3"],
                                "Metrics": {"AmortizedCost": {"Amount": "2.5", "Unit": "USD"}},
                            },
                        ],
                    },
                    {
                        "TimePeriod": {"Start": "2026-10-03", "End": "2026-10-04"},
                        "Estimated": True,
                        "Groups": [
                            {
                                "Keys": ["Credit adjustment"],
                                "Metrics": {"AmortizedCost": {"Amount": "-3", "Unit": "USD"}},
                            }
                        ],
                    },
                ]
            }
        ]
    )

    response = _service(account, client).timeseries(_request(BillingGroupBy.SERVICE))

    assert response.group_by == BillingGroupBy.SERVICE
    assert [point.amount for point in response.points] == [
        Decimal("15.0"),
        Decimal("0"),
        Decimal("-3"),
    ]
    assert [(group.key, group.amount) for group in response.points[0].groups] == [
        ("Amazon EC2", Decimal("12.5")),
        ("Amazon S3", Decimal("2.5")),
    ]
    assert response.points[1].groups == []
    assert response.points[2].groups[0].amount == Decimal("-3")
    assert response.points[2].estimated is True
    assert client.queries[0]["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]


def test_account_grouped_timeseries_uses_registered_account_label():
    account = _account(1, "111111111111", "Prod")
    client = _Client(
        [
            {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-02"},
                        "Estimated": False,
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

    response = _service(account, client).timeseries(_request(BillingGroupBy.ACCOUNT))

    group = response.points[0].groups[0]
    assert group.label == "Prod"
    assert group.display_name == "Prod"
    assert group.aws_account_id == "111111111111"
    assert group.deepops_account_id == 1
