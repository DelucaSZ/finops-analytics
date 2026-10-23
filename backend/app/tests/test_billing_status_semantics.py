from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.schemas.billing import (
    AwsBillingRequest,
    BillingDataStatus,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
    BillingSeriesPoint,
)
from app.services.aws_billing import AwsBillingService, _BillingRow, _status_from_estimation_flags


def _request(*, group_by: BillingGroupBy = BillingGroupBy.SERVICE) -> AwsBillingRequest:
    return AwsBillingRequest(
        account_ids=[1],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        granularity=BillingGranularity.DAILY,
        metric=BillingMetric.AMORTIZED_COST,
        group_by=group_by,
        exclude_record_types=["Credit"],
    )


def _row(day: int, *, amount: str = "10", estimated: bool, key: str = "Amazon EC2") -> _BillingRow:
    start = date(2026, 10, day)
    return _BillingRow(
        start_date=start,
        end_date=start + timedelta(days=1),
        key=key,
        amount=Decimal(amount),
        currency="USD",
        estimated=estimated,
        deepops_account_id=1,
        aws_account_id="111111111111",
        display_name="Conta teste",
    )


class _RowsBillingService(AwsBillingService):
    def __init__(self, rows: tuple[_BillingRow, ...]) -> None:
        self._test_rows = rows

    def _rows(
        self,
        request: AwsBillingRequest,
        *,
        group_by: BillingGroupBy,
    ) -> tuple[_BillingRow, ...]:
        return self._test_rows


def _service_with_rows(rows: tuple[_BillingRow, ...]) -> AwsBillingService:
    return _RowsBillingService(rows)


def test_status_from_estimation_flags_keeps_three_aggregation_outcomes() -> None:
    assert _status_from_estimation_flags([False, False]) == BillingDataStatus.ACTUAL
    assert _status_from_estimation_flags([True, True]) == BillingDataStatus.ESTIMATED
    assert _status_from_estimation_flags([False, True]) == BillingDataStatus.PARTIALLY_ESTIMATED


def test_timeseries_preserves_actual_and_estimated_per_day() -> None:
    service = _service_with_rows(
        (
            _row(1, estimated=False),
            _row(2, estimated=False),
            _row(3, estimated=True),
        )
    )

    response = service.timeseries(_request())

    assert [point.status for point in response.points] == [
        BillingDataStatus.ACTUAL,
        BillingDataStatus.ACTUAL,
        BillingDataStatus.ESTIMATED,
    ]
    assert [point.estimated for point in response.points] == [False, False, True]


def test_closed_period_summary_is_actual_when_every_bucket_is_final() -> None:
    service = _service_with_rows(
        (
            _row(1, amount="20", estimated=False),
            _row(2, amount="30", estimated=False),
            _row(3, amount="40", estimated=False),
        )
    )

    response = service.summary(_request(group_by=BillingGroupBy.NONE))

    assert response.totals[0].amount == Decimal("90")
    assert response.totals[0].status == BillingDataStatus.ACTUAL
    assert response.totals[0].estimated is False


def test_summary_does_not_call_a_mixed_period_fully_estimated() -> None:
    service = _service_with_rows(
        (
            _row(1, estimated=False),
            _row(2, estimated=False),
            _row(3, estimated=True),
        )
    )

    response = service.summary(_request(group_by=BillingGroupBy.NONE))

    assert response.totals[0].status == BillingDataStatus.PARTIALLY_ESTIMATED
    assert response.totals[0].estimated is True


def test_breakdown_marks_service_as_partially_estimated_when_only_one_day_is_provisional() -> None:
    service = _service_with_rows(
        (
            _row(1, amount="100", estimated=False),
            _row(2, amount="50", estimated=False),
            _row(3, amount="25", estimated=True),
        )
    )

    response = service.breakdown(_request())

    assert len(response.items) == 1
    assert response.items[0].amount == Decimal("175")
    assert response.items[0].status == BillingDataStatus.PARTIALLY_ESTIMATED
    assert response.items[0].estimated is True


def test_forecast_is_explicit_and_never_serializes_as_estimated() -> None:
    point = BillingSeriesPoint(
        start_date=date(2026, 10, 24),
        end_date=date(2026, 10, 25),
        amount=Decimal("12.34"),
        currency="USD",
        status=BillingDataStatus.FORECAST,
        groups=[],
    )

    payload = point.model_dump(mode="json")

    assert payload["status"] == "FORECAST"
    assert payload["estimated"] is False
