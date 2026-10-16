from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloudwatch_pricing import CloudWatchPricingRule


class CloudWatchPricingError(RuntimeError):
    pass


class CloudWatchPricingNotFoundError(CloudWatchPricingError):
    pass


class CloudWatchPricingAmbiguousError(CloudWatchPricingError):
    pass


@dataclass(frozen=True)
class CloudWatchPricingDimension:
    name: str
    usage_field: str


CLOUDWATCH_PRICING_DIMENSIONS: dict[str, CloudWatchPricingDimension] = {
    "GetMetricStatistics": CloudWatchPricingDimension(
        name="API_REQUEST",
        usage_field="request_count",
    )
}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_aws_commercial_region(region: str) -> bool:
    if not region or region == "unknown":
        return False
    excluded_prefixes = ("cn-", "us-gov-", "us-iso-", "us-isob-")
    return "-" in region and not region.startswith(excluded_prefixes)


def region_scope_matches(region_scope: str, region: str) -> bool:
    if region_scope == "GLOBAL":
        return True
    if region_scope == "AWS_COMMERCIAL":
        return is_aws_commercial_region(region)
    if region_scope.startswith("REGION:"):
        return region == region_scope.removeprefix("REGION:")
    return False


def _effective(rule: CloudWatchPricingRule, occurred_at: datetime) -> bool:
    at = utc(occurred_at)
    effective_from = utc(rule.effective_from)
    effective_until = utc(rule.effective_until) if rule.effective_until is not None else None
    return effective_from <= at and (effective_until is None or at < effective_until)


def _tier_contains(rule: CloudWatchPricingRule, usage_position: Decimal) -> bool:
    lower = Decimal(rule.tier_from)
    upper = Decimal(rule.tier_to) if rule.tier_to is not None else None
    return lower <= usage_position and (upper is None or usage_position < upper)


class CloudWatchPricingResolver:
    """Resolve an effective pricing rule without silently choosing an overlap."""

    def __init__(self, db: Session):
        self._db = db
        self._rules: tuple[CloudWatchPricingRule, ...] | None = None

    def all_enabled_rules(self) -> tuple[CloudWatchPricingRule, ...]:
        if self._rules is None:
            statement = (
                select(CloudWatchPricingRule)
                .where(CloudWatchPricingRule.enabled.is_(True))
                .order_by(
                    CloudWatchPricingRule.operation,
                    CloudWatchPricingRule.pricing_dimension,
                    CloudWatchPricingRule.region_scope,
                    CloudWatchPricingRule.effective_from,
                    CloudWatchPricingRule.tier_from,
                )
            )
            self._rules = tuple(self._db.scalars(statement).all())
        return self._rules

    def resolve(
        self,
        *,
        operation: str,
        pricing_dimension: str,
        region: str,
        occurred_at: datetime,
        usage_position: Decimal = Decimal("0"),
    ) -> CloudWatchPricingRule:
        matches = [
            rule
            for rule in self.all_enabled_rules()
            if rule.operation == operation
            and rule.pricing_dimension == pricing_dimension
            and region_scope_matches(rule.region_scope, region)
            and _effective(rule, occurred_at)
            and _tier_contains(rule, usage_position)
        ]
        if not matches:
            raise CloudWatchPricingNotFoundError(
                "cloudwatch pricing not found for "
                f"operation={operation} dimension={pricing_dimension} "
                f"region={region} occurred_at={utc(occurred_at).isoformat()} "
                f"usage_position={usage_position}"
            )
        if len(matches) > 1:
            rule_ids = ",".join(rule.id for rule in matches)
            raise CloudWatchPricingAmbiguousError(
                "cloudwatch pricing ambiguous for "
                f"operation={operation} dimension={pricing_dimension} "
                f"region={region} occurred_at={utc(occurred_at).isoformat()} "
                f"usage_position={usage_position}; rules={rule_ids}"
            )
        return matches[0]

    def resolve_tiers(
        self,
        *,
        operation: str,
        pricing_dimension: str,
        region: str,
        occurred_at: datetime,
    ) -> tuple[CloudWatchPricingRule, ...]:
        matches = [
            rule
            for rule in self.all_enabled_rules()
            if rule.operation == operation
            and rule.pricing_dimension == pricing_dimension
            and region_scope_matches(rule.region_scope, region)
            and _effective(rule, occurred_at)
        ]
        if not matches:
            raise CloudWatchPricingNotFoundError(
                "cloudwatch pricing not found for "
                f"operation={operation} dimension={pricing_dimension} "
                f"region={region} occurred_at={utc(occurred_at).isoformat()}"
            )
        return tuple(sorted(matches, key=lambda rule: Decimal(rule.tier_from)))


def calculate_tiered_cost(
    quantity: Decimal,
    rules: tuple[CloudWatchPricingRule, ...],
) -> tuple[Decimal, list[dict]]:
    """Apply continuous tier ranges without block rounding."""

    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not rules:
        raise CloudWatchPricingNotFoundError("no pricing tiers supplied")

    currencies = {rule.currency for rule in rules}
    if len(currencies) != 1:
        raise CloudWatchPricingAmbiguousError(
            f"pricing tiers mix currencies: {','.join(sorted(currencies))}"
        )

    total = Decimal("0")
    covered = Decimal("0")
    components: list[dict] = []
    previous_upper: Decimal | None = Decimal("0")

    for rule in sorted(rules, key=lambda item: Decimal(item.tier_from)):
        lower = Decimal(rule.tier_from)
        upper = Decimal(rule.tier_to) if rule.tier_to is not None else None
        if previous_upper is not None and lower != previous_upper:
            raise CloudWatchPricingNotFoundError(
                f"pricing tier gap before rule={rule.id}: expected={previous_upper} got={lower}"
            )
        if upper is not None and upper <= lower:
            raise CloudWatchPricingAmbiguousError(f"invalid pricing tier rule={rule.id}")

        tier_quantity = max(Decimal("0"), quantity - lower)
        if upper is not None:
            tier_quantity = min(tier_quantity, upper - lower)
        if tier_quantity > 0:
            component_cost = tier_quantity / Decimal(rule.unit_quantity) * Decimal(rule.price)
            total += component_cost
            covered += tier_quantity
            components.append(
                {
                    "pricing_rule_id": rule.id,
                    "usage_quantity": tier_quantity,
                    "unit_price": Decimal(rule.price),
                    "unit_quantity": Decimal(rule.unit_quantity),
                    "pricing_unit": rule.unit,
                    "currency": rule.currency,
                    "effective_from": rule.effective_from,
                    "effective_until": rule.effective_until,
                    "source": rule.source,
                    "source_reference": rule.source_reference,
                    "pricing_verified_at": rule.pricing_verified_at,
                }
            )
        previous_upper = upper
        if covered >= quantity:
            break

    if covered < quantity:
        raise CloudWatchPricingNotFoundError(
            f"pricing tiers cover {covered} units but quantity is {quantity}"
        )
    return total, components
