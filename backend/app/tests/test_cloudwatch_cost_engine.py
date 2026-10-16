from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.cloudwatch_pricing import CloudWatchPricingRule
from app.models.cloudwatch_usage import CloudWatchUsageEvent
from app.services.cloudwatch_cost_engine import CloudWatchCostEngine
from app.services.cloudwatch_pricing import (
    CloudWatchPricingAmbiguousError,
    CloudWatchPricingNotFoundError,
    CloudWatchPricingResolver,
    calculate_tiered_cost,
)
from app.services.cloudwatch_usage_query import CloudWatchUsageFilters

VERIFIED_AT = datetime(2026, 10, 16, tzinfo=UTC)


def pricing_rule(
    *,
    rule_id: str,
    effective_from: datetime,
    price: str = "0.01",
    effective_until: datetime | None = None,
    region_scope: str = "AWS_COMMERCIAL",
    currency: str = "USD",
    tier_from: str = "0",
    tier_to: str | None = None,
) -> CloudWatchPricingRule:
    return CloudWatchPricingRule(
        id=rule_id,
        operation="GetMetricStatistics",
        pricing_dimension="API_REQUEST",
        region_scope=region_scope,
        unit="REQUEST",
        unit_quantity=Decimal("1000"),
        price=Decimal(price),
        currency=currency,
        effective_from=effective_from,
        effective_until=effective_until,
        tier_from=Decimal(tier_from),
        tier_to=Decimal(tier_to) if tier_to is not None else None,
        tier_scope="NONE",
        applicability="gross public rate; shared free tier not applied",
        source="AWS_OFFICIAL_PRICING",
        source_reference="https://aws.amazon.com/cloudwatch/pricing/",
        pricing_verified_at=VERIFIED_AT,
        enabled=True,
    )


def usage_event(
    *,
    event_id: str,
    occurred_at: datetime,
    account: str = "111111111111",
    region: str = "sa-east-1",
    operation: str = "GetMetricStatistics",
    collector: str | None = "rds_nonprod_idle",
    analyzer: str | None = "rds_nonprod_idle",
    collection_run_id: str | None = None,
    request_count: int = 1,
    exact: bool = True,
    success: bool = True,
) -> CloudWatchUsageEvent:
    return CloudWatchUsageEvent(
        id=event_id,
        occurred_at=occurred_at,
        provider="aws",
        aws_service="cloudwatch",
        aws_account_id=account,
        region=region,
        operation=operation,
        collector=collector,
        analyzer=analyzer,
        collection_run_id=collection_run_id,
        request_count=request_count,
        retry_count=max(0, request_count - 1) if exact else None,
        request_count_is_exact=exact,
        metrics_requested=1,
        success=success,
        error_type=None if success else "Throttling",
        event_metadata={},
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_pricing_resolver_respects_effective_dates_and_future_versions(db: Session):
    first = datetime(2026, 1, 1, tzinfo=UTC)
    change = datetime(2026, 7, 1, tzinfo=UTC)
    db.add_all(
        [
            pricing_rule(
                rule_id="old",
                effective_from=first,
                effective_until=change,
                price="0.01",
            ),
            pricing_rule(rule_id="new", effective_from=change, price="0.02"),
        ]
    )
    db.commit()

    resolver = CloudWatchPricingResolver(db)
    june = resolver.resolve(
        operation="GetMetricStatistics",
        pricing_dimension="API_REQUEST",
        region="sa-east-1",
        occurred_at=datetime(2026, 6, 30, tzinfo=UTC),
    )
    august = resolver.resolve(
        operation="GetMetricStatistics",
        pricing_dimension="API_REQUEST",
        region="sa-east-1",
        occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert june.id == "old"
    assert august.id == "new"
    with pytest.raises(CloudWatchPricingNotFoundError):
        resolver.resolve(
            operation="GetMetricStatistics",
            pricing_dimension="API_REQUEST",
            region="sa-east-1",
            occurred_at=datetime(2025, 12, 31, tzinfo=UTC),
        )


def test_pricing_resolver_rejects_overlapping_rules(db: Session):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    db.add_all(
        [
            pricing_rule(rule_id="a", effective_from=start),
            pricing_rule(
                rule_id="b",
                effective_from=start + timedelta(days=1),
                price="0.02",
            ),
        ]
    )
    db.commit()

    with pytest.raises(CloudWatchPricingAmbiguousError):
        CloudWatchPricingResolver(db).resolve(
            operation="GetMetricStatistics",
            pricing_dimension="API_REQUEST",
            region="sa-east-1",
            occurred_at=start + timedelta(days=2),
        )


def test_tier_calculation_preserves_decimal_precision_and_boundaries(db: Session):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = pricing_rule(
        rule_id="tier-1",
        effective_from=start,
        price="0.01",
        tier_from="0",
        tier_to="1000",
    )
    second = pricing_rule(
        rule_id="tier-2",
        effective_from=start,
        price="0.005",
        tier_from="1000",
    )

    cost, components = calculate_tiered_cost(Decimal("1500"), (first, second))

    assert cost == Decimal("0.0125")
    assert [component["usage_quantity"] for component in components] == [
        Decimal("1000"),
        Decimal("500"),
    ]
    exact_boundary, _ = calculate_tiered_cost(Decimal("1000"), (first, second))
    assert exact_boundary == Decimal("0.01")


def test_engine_prices_requests_retries_failures_and_marks_unpriced_usage(db: Session):
    start = datetime(2026, 10, 16, tzinfo=UTC)
    db.add(pricing_rule(rule_id="current", effective_from=start))
    db.add_all(
        [
            usage_event(event_id="one", occurred_at=start + timedelta(minutes=1)),
            usage_event(
                event_id="retry-failure",
                occurred_at=start + timedelta(minutes=2),
                request_count=3,
                success=False,
            ),
            usage_event(
                event_id="inexact",
                occurred_at=start + timedelta(minutes=3),
                account="222222222222",
                request_count=2,
                exact=False,
            ),
            usage_event(
                event_id="unsupported",
                occurred_at=start + timedelta(minutes=4),
                operation="GetMetricData",
            ),
        ]
    )
    db.commit()

    result = CloudWatchCostEngine(db).calculate(CloudWatchUsageFilters())

    assert result["totals"] == [
        {
            "currency": "USD",
            "gross_estimated_cost": Decimal("0.00006"),
            "usage_quantity": Decimal("6"),
        }
    ]
    assert result["priced_events"] == 3
    assert result["unpriced_events"] == 1
    assert result["is_complete"] is False
    assert result["request_count_is_exact"] is False
    assert result["inexact_request_events"] == 1
    assert result["failed_events"] == 1
    assert result["free_tier_applied"] is False
    assert result["unpriced_usage"][0]["operation"] == "GetMetricData"


@pytest.mark.parametrize(
    "group_by",
    ["account", "region", "operation", "collector", "analyzer", "collection_run"],
)
def test_engine_supports_required_breakdowns(db: Session, group_by: str):
    start = datetime(2026, 10, 16, tzinfo=UTC)
    db.add(pricing_rule(rule_id="current", effective_from=start))
    db.add_all(
        [
            usage_event(
                event_id="a",
                occurred_at=start + timedelta(hours=1),
                account="111111111111",
                region="sa-east-1",
                collection_run_id="run-a",
            ),
            usage_event(
                event_id="b",
                occurred_at=start + timedelta(hours=2),
                account="222222222222",
                region="us-east-1",
                collector="load_balancer_no_traffic",
                analyzer="load_balancer_no_traffic",
                collection_run_id="run-b",
                request_count=2,
            ),
        ]
    )
    db.commit()

    result = CloudWatchCostEngine(db).calculate(
        CloudWatchUsageFilters(),
        group_by=group_by,
    )

    assert result["is_complete"] is True
    assert sum(item["usage_quantity"] for item in result["items"]) == Decimal("3")
    assert all(item["currency"] == "USD" for item in result["items"])


def test_engine_supports_daily_and_monthly_timeseries(db: Session):
    start = datetime(2026, 10, 16, tzinfo=UTC)
    db.add(pricing_rule(rule_id="current", effective_from=start))
    db.add_all(
        [
            usage_event(event_id="day-1", occurred_at=start + timedelta(hours=1)),
            usage_event(event_id="day-2", occurred_at=start + timedelta(days=1)),
        ]
    )
    db.commit()

    daily = CloudWatchCostEngine(db).calculate(
        CloudWatchUsageFilters(),
        granularity="daily",
    )
    monthly = CloudWatchCostEngine(db).calculate(
        CloudWatchUsageFilters(),
        granularity="monthly",
    )

    assert [item["period"] for item in daily["items"]] == ["2026-10-16", "2026-10-17"]
    assert [item["period"] for item in monthly["items"]] == ["2026-10"]
    assert monthly["items"][0]["usage_quantity"] == Decimal("2")


def test_engine_never_sums_distinct_currencies(db: Session):
    start = datetime(2026, 10, 16, tzinfo=UTC)
    db.add_all(
        [
            pricing_rule(
                rule_id="usd",
                effective_from=start,
                region_scope="REGION:us-east-1",
                currency="USD",
            ),
            pricing_rule(
                rule_id="brl-test",
                effective_from=start,
                region_scope="REGION:sa-east-1",
                currency="BRL",
                price="0.02",
            ),
            usage_event(
                event_id="usd-event",
                occurred_at=start + timedelta(minutes=1),
                region="us-east-1",
            ),
            usage_event(
                event_id="brl-event",
                occurred_at=start + timedelta(minutes=2),
                region="sa-east-1",
            ),
        ]
    )
    db.commit()

    result = CloudWatchCostEngine(db).calculate(CloudWatchUsageFilters())

    assert {item["currency"] for item in result["totals"]} == {"USD", "BRL"}
    assert len(result["totals"]) == 2


def test_non_commercial_or_unknown_region_is_explicitly_unpriced(db: Session):
    start = datetime(2026, 10, 16, tzinfo=UTC)
    db.add(pricing_rule(rule_id="current", effective_from=start))
    db.add_all(
        [
            usage_event(
                event_id="gov",
                occurred_at=start + timedelta(minutes=1),
                region="us-gov-west-1",
            ),
            usage_event(
                event_id="unknown",
                occurred_at=start + timedelta(minutes=2),
                region="unknown",
            ),
        ]
    )
    db.commit()

    result = CloudWatchCostEngine(db).calculate(CloudWatchUsageFilters())

    assert result["priced_events"] == 0
    assert result["unpriced_events"] == 2
    assert result["is_complete"] is False
