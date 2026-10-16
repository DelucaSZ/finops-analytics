import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, and_, case, extract, false, func, not_, or_, select, true
from sqlalchemy.orm import Session

from app.models.cloudwatch_pricing import CloudWatchPricingRule
from app.models.cloudwatch_usage import CloudWatchUsageEvent
from app.services.cloudwatch_pricing import (
    CLOUDWATCH_PRICING_DIMENSIONS,
    CloudWatchPricingAmbiguousError,
    CloudWatchPricingResolver,
    calculate_tiered_cost,
    is_aws_commercial_region,
    utc,
)
from app.services.cloudwatch_usage_query import CloudWatchUsageFilters

logger = logging.getLogger("deepops.cloudwatch_cost")

CloudWatchCostGroup = Literal[
    "account",
    "region",
    "operation",
    "collector",
    "analyzer",
    "collection_run",
]
CloudWatchCostGranularity = Literal["daily", "monthly"]

_GROUP_COLUMNS = {
    "account": CloudWatchUsageEvent.aws_account_id,
    "region": CloudWatchUsageEvent.region,
    "operation": CloudWatchUsageEvent.operation,
    "collector": CloudWatchUsageEvent.collector,
    "analyzer": CloudWatchUsageEvent.analyzer,
    "collection_run": CloudWatchUsageEvent.collection_run_id,
}


def _filtered(statement: Select, filters: CloudWatchUsageFilters) -> Select:
    if filters.date_from is not None:
        statement = statement.where(CloudWatchUsageEvent.occurred_at >= utc(filters.date_from))
    if filters.date_to is not None:
        statement = statement.where(CloudWatchUsageEvent.occurred_at < utc(filters.date_to))
    if filters.cloud_account_id is not None:
        statement = statement.where(
            CloudWatchUsageEvent.cloud_account_id == filters.cloud_account_id
        )
    if filters.aws_account_id is not None:
        statement = statement.where(CloudWatchUsageEvent.aws_account_id == filters.aws_account_id)
    if filters.region is not None:
        statement = statement.where(CloudWatchUsageEvent.region == filters.region)
    if filters.operation is not None:
        statement = statement.where(CloudWatchUsageEvent.operation == filters.operation)
    if filters.collector is not None:
        statement = statement.where(CloudWatchUsageEvent.collector == filters.collector)
    if filters.analyzer is not None:
        statement = statement.where(CloudWatchUsageEvent.analyzer == filters.analyzer)
    if filters.collection_run_id is not None:
        statement = statement.where(
            CloudWatchUsageEvent.collection_run_id == filters.collection_run_id
        )
    if filters.success is not None:
        statement = statement.where(CloudWatchUsageEvent.success.is_(filters.success))
    return statement


def _region_clause(region_scope: str):
    region = CloudWatchUsageEvent.region
    if region_scope == "GLOBAL":
        return true()
    if region_scope == "AWS_COMMERCIAL":
        return and_(
            region != "unknown",
            not_(region.like("cn-%")),
            not_(region.like("us-gov-%")),
            not_(region.like("us-iso-%")),
            not_(region.like("us-isob-%")),
        )
    if region_scope.startswith("REGION:"):
        return region == region_scope.removeprefix("REGION:")
    return false()


def _regions_overlap(left: str, right: str) -> bool:
    if left == "GLOBAL" or right == "GLOBAL":
        return True
    if left == right:
        return True
    if left == "AWS_COMMERCIAL" and right.startswith("REGION:"):
        return is_aws_commercial_region(right.removeprefix("REGION:"))
    if right == "AWS_COMMERCIAL" and left.startswith("REGION:"):
        return is_aws_commercial_region(left.removeprefix("REGION:"))
    return False


def _time_overlap(left: CloudWatchPricingRule, right: CloudWatchPricingRule) -> bool:
    left_start = utc(left.effective_from)
    right_start = utc(right.effective_from)
    left_end = utc(left.effective_until) if left.effective_until else datetime.max.replace(tzinfo=UTC)
    right_end = (
        utc(right.effective_until) if right.effective_until else datetime.max.replace(tzinfo=UTC)
    )
    return left_start < right_end and right_start < left_end


def _tier_overlap(left: CloudWatchPricingRule, right: CloudWatchPricingRule) -> bool:
    left_start = Decimal(left.tier_from)
    right_start = Decimal(right.tier_from)
    left_end = Decimal(left.tier_to) if left.tier_to is not None else Decimal("Infinity")
    right_end = Decimal(right.tier_to) if right.tier_to is not None else Decimal("Infinity")
    return left_start < right_end and right_start < left_end


def _validate_no_ambiguous_rules(rules: tuple[CloudWatchPricingRule, ...]) -> None:
    for index, left in enumerate(rules):
        for right in rules[index + 1 :]:
            if left.operation != right.operation:
                continue
            if left.pricing_dimension != right.pricing_dimension:
                continue
            if not _regions_overlap(left.region_scope, right.region_scope):
                continue
            if not _time_overlap(left, right):
                continue
            if not _tier_overlap(left, right):
                continue
            raise CloudWatchPricingAmbiguousError(
                "overlapping CloudWatch pricing rules: " f"{left.id},{right.id}"
            )


def _version_key(rule: CloudWatchPricingRule) -> tuple:
    return (
        rule.operation,
        rule.pricing_dimension,
        rule.region_scope,
        utc(rule.effective_from),
        utc(rule.effective_until) if rule.effective_until else None,
        rule.tier_scope,
        rule.currency,
    )


def _coverage_clause(rules: tuple[CloudWatchPricingRule, ...]):
    clauses = []
    for rule in rules:
        if rule.operation not in CLOUDWATCH_PRICING_DIMENSIONS:
            continue
        clause = and_(
            CloudWatchUsageEvent.operation == rule.operation,
            CloudWatchUsageEvent.occurred_at >= utc(rule.effective_from),
            _region_clause(rule.region_scope),
        )
        if rule.effective_until is not None:
            clause = and_(
                clause,
                CloudWatchUsageEvent.occurred_at < utc(rule.effective_until),
            )
        clauses.append(clause)
    return or_(*clauses) if clauses else false()


def _period_columns(granularity: CloudWatchCostGranularity | None) -> list:
    if granularity is None:
        return []
    columns = [
        extract("year", CloudWatchUsageEvent.occurred_at).label("period_year"),
        extract("month", CloudWatchUsageEvent.occurred_at).label("period_month"),
    ]
    if granularity == "daily":
        columns.append(extract("day", CloudWatchUsageEvent.occurred_at).label("period_day"))
    return columns


def _period_value(row, granularity: CloudWatchCostGranularity | None) -> str | None:
    if granularity is None:
        return None
    year = int(row.period_year)
    month = int(row.period_month)
    if granularity == "monthly":
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{int(row.period_day):02d}"


class CloudWatchCostEngine:
    """Estimate DeepOps CloudWatch cost from raw telemetry and versioned public pricing."""

    def __init__(self, db: Session):
        self._db = db
        self._resolver = CloudWatchPricingResolver(db)

    def calculate(
        self,
        filters: CloudWatchUsageFilters,
        *,
        group_by: CloudWatchCostGroup | None = None,
        granularity: CloudWatchCostGranularity | None = None,
    ) -> dict:
        rules = self._resolver.all_enabled_rules()
        _validate_no_ambiguous_rules(rules)

        rules_by_version: dict[tuple, list[CloudWatchPricingRule]] = defaultdict(list)
        for rule in rules:
            if rule.operation in CLOUDWATCH_PRICING_DIMENSIONS:
                rules_by_version[_version_key(rule)].append(rule)

        merged: dict[tuple[str | None, str | None, str], dict] = {}
        priced_events = 0
        inexact_request_events = 0
        failed_events = 0

        for version_key, version_rules_list in rules_by_version.items():
            (
                operation,
                pricing_dimension,
                region_scope,
                effective_from,
                effective_until,
                tier_scope,
                currency,
            ) = version_key
            if tier_scope != "NONE" and len(version_rules_list) > 1:
                raise CloudWatchPricingAmbiguousError(
                    "tiered analytical attribution requires a supported AWS tier scope; "
                    f"operation={operation} tier_scope={tier_scope}"
                )

            dimension = CLOUDWATCH_PRICING_DIMENSIONS[operation]
            if dimension.name != pricing_dimension:
                continue
            quantity_column = getattr(CloudWatchUsageEvent, dimension.usage_field)
            select_columns = []
            group_columns = []
            if group_by is not None:
                group_column = _GROUP_COLUMNS[group_by]
                select_columns.append(group_column.label("cost_group"))
                group_columns.append(group_column)
            period_columns = _period_columns(granularity)
            select_columns.extend(period_columns)
            group_columns.extend(period_columns)

            statement = select(
                *select_columns,
                func.count(CloudWatchUsageEvent.id).label("events"),
                func.coalesce(func.sum(quantity_column), 0).label("usage_quantity"),
                func.coalesce(
                    func.sum(
                        case(
                            (CloudWatchUsageEvent.request_count_is_exact.is_(False), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("inexact_request_events"),
                func.coalesce(
                    func.sum(
                        case((CloudWatchUsageEvent.success.is_(False), 1), else_=0)
                    ),
                    0,
                ).label("failed_events"),
            ).where(
                CloudWatchUsageEvent.operation == operation,
                CloudWatchUsageEvent.occurred_at >= effective_from,
                _region_clause(region_scope),
            )
            if effective_until is not None:
                statement = statement.where(CloudWatchUsageEvent.occurred_at < effective_until)
            statement = _filtered(statement, filters)
            if group_columns:
                statement = statement.group_by(*group_columns)

            version_rules = tuple(
                sorted(version_rules_list, key=lambda rule: Decimal(rule.tier_from))
            )
            for row in self._db.execute(statement).all():
                quantity = Decimal(row.usage_quantity)
                if quantity <= 0:
                    continue
                cost, components = calculate_tiered_cost(quantity, version_rules)
                group_value = str(row.cost_group) if group_by is not None and row.cost_group is not None else None
                period = _period_value(row, granularity)
                key = (group_value, period, currency)
                item = merged.setdefault(
                    key,
                    {
                        "group": group_value,
                        "period": period,
                        "currency": currency,
                        "gross_estimated_cost": Decimal("0"),
                        "usage_quantity": Decimal("0"),
                        "priced_events": 0,
                        "inexact_request_events": 0,
                        "failed_events": 0,
                        "components": [],
                    },
                )
                item["gross_estimated_cost"] += cost
                item["usage_quantity"] += quantity
                item["priced_events"] += int(row.events)
                item["inexact_request_events"] += int(row.inexact_request_events)
                item["failed_events"] += int(row.failed_events)
                item["components"].extend(components)
                priced_events += int(row.events)
                inexact_request_events += int(row.inexact_request_events)
                failed_events += int(row.failed_events)

        coverage = _coverage_clause(rules)
        unpriced_statement = select(
            CloudWatchUsageEvent.operation.label("operation"),
            CloudWatchUsageEvent.region.label("region"),
            func.count(CloudWatchUsageEvent.id).label("events"),
            func.coalesce(func.sum(CloudWatchUsageEvent.request_count), 0).label("requests"),
        ).where(not_(coverage))
        unpriced_statement = _filtered(unpriced_statement, filters).group_by(
            CloudWatchUsageEvent.operation,
            CloudWatchUsageEvent.region,
        )
        unpriced_rows = self._db.execute(unpriced_statement).all()
        unpriced_usage = [
            {
                "operation": row.operation,
                "region": row.region,
                "events": int(row.events),
                "requests": int(row.requests),
                "reason": "UNPRICED_USAGE",
            }
            for row in unpriced_rows
        ]
        unpriced_events = sum(item["events"] for item in unpriced_usage)

        totals_by_currency: dict[str, dict] = {}
        for item in merged.values():
            total = totals_by_currency.setdefault(
                item["currency"],
                {
                    "currency": item["currency"],
                    "gross_estimated_cost": Decimal("0"),
                    "usage_quantity": Decimal("0"),
                },
            )
            total["gross_estimated_cost"] += item["gross_estimated_cost"]
            total["usage_quantity"] += item["usage_quantity"]

        used_components = [
            component
            for item in merged.values()
            for component in item["components"]
        ]
        pricing_sources = sorted({component["source"] for component in used_components})
        verified_dates = [utc(component["pricing_verified_at"]) for component in used_components]
        pricing_verified_at = max(verified_dates) if verified_dates else None

        for row in unpriced_usage:
            logger.warning(
                "event=cloudwatch_pricing_not_found operation=%s region=%s events=%s requests=%s",
                row["operation"],
                row["region"],
                row["events"],
                row["requests"],
            )
        logger.info(
            "event=cloudwatch_cost_calculated usage_groups=%s priced_groups=%s "
            "unpriced_groups=%s currencies=%s",
            len(merged) + len(unpriced_usage),
            len(merged),
            len(unpriced_usage),
            ",".join(sorted(totals_by_currency)) or "none",
        )

        return {
            "group_by": group_by,
            "granularity": granularity,
            "items": sorted(
                merged.values(),
                key=lambda item: (
                    item["period"] or "",
                    item["group"] or "",
                    item["currency"],
                ),
            ),
            "totals": [totals_by_currency[key] for key in sorted(totals_by_currency)],
            "priced_events": priced_events,
            "unpriced_events": unpriced_events,
            "unpriced_usage": unpriced_usage,
            "is_complete": unpriced_events == 0,
            "request_count_is_exact": inexact_request_events == 0,
            "inexact_request_events": inexact_request_events,
            "failed_events": failed_events,
            "free_tier_applied": False,
            "pricing_sources": pricing_sources,
            "pricing_verified_at": pricing_verified_at,
            "estimation_basis": (
                "Gross operational estimate from DeepOps-observed CloudWatch usage and "
                "effective-dated public AWS pricing. Shared AWS Free Tier, private pricing, "
                "taxes, credits, discounts, and FX are not applied. Failed requests are "
                "included because current AWS pricing documentation does not state an "
                "exclusion for failed API attempts; inexact retry observations are flagged."
            ),
        }
