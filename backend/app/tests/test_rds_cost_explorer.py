from decimal import Decimal

from app.services.rds_cost_explorer import RdsCostExplorerClient


class FakeCostExplorer:
    def __init__(self) -> None:
        self.requests = []

    def get_reservation_coverage(self, **request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return {
                "CoveragesByTime": [
                    {
                        "Total": {
                            "CoverageNormalizedUnits": {
                                "TotalRunningNormalizedUnits": "10",
                                "ReservedNormalizedUnits": "6",
                            }
                        }
                    }
                ],
                "NextPageToken": "page-2",
            }
        return {
            "CoveragesByTime": [
                {
                    "Total": {
                        "CoverageNormalizedUnits": {
                            "TotalRunningNormalizedUnits": "10",
                            "ReservedNormalizedUnits": "8",
                        }
                    }
                }
            ]
        }


def test_rds_reservation_coverage_filters_service_and_paginates() -> None:
    upstream = FakeCostExplorer()
    client = RdsCostExplorerClient(client=upstream)

    result = client.get_rds_reservation_coverage(
        start_date="2026-10-25",
        end_date="2026-10-26",
        linked_account_id="111111111111",
    )

    assert result.aws_request_count == 2
    assert result.total_running_units == Decimal("20")
    assert result.reserved_units == Decimal("14")
    assert result.coverage_percentage == Decimal("70")
    assert upstream.requests[0]["TimePeriod"] == {
        "Start": "2026-10-25",
        "End": "2026-10-26",
    }
    assert upstream.requests[0]["Granularity"] == "DAILY"
    assert upstream.requests[0]["Filter"] == {
        "And": [
            {
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Relational Database Service"],
                }
            },
            {
                "Dimensions": {
                    "Key": "LINKED_ACCOUNT",
                    "Values": ["111111111111"],
                }
            },
        ]
    }
    assert "NextPageToken" not in upstream.requests[0]
    assert upstream.requests[1]["NextPageToken"] == "page-2"
