"""Task 27.2: deterministic, provider-neutral composition and temporal metering.

Providers resolve verified catalog prices and supply explicit billing policies. This
module never selects cloud SKUs, performs account actions or invents price rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.schemas.calculator import (
    AwsFinancialTerms,
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    CalculatorPricingComponent,
    CalculatorPricingStatus,
)
from app.services.calculator_foundation import (
    CalculatorPriceLookup,
    apply_aws_financial_terms,
)

CENT = Decimal("0.01")
MAX_SECONDS = Decimal(5 * 366 * 86400)
MAX_FINANCIAL_VALUE = Decimal("1e18")
SECONDS_PER_UNIT = {
    "HOUR": Decimal(3600),
    "MINUTE": Decimal(60),
    "SECOND": Decimal(1),
}
STATUS_PRIORITY = (
    "pricing_configuration_error",
    "invalid_combination",
    "sync_required",
    "price_not_effective",
    "sku_missing",
    "missing_configuration",
    "unsupported_configuration",
)


@dataclass(frozen=True, slots=True)
class CalculatorMeteredComponent:
    """One required SKU and its provider-verified metering policy.

    units_per_resource is the metered dimension, e.g. 2 OCPUs or 16 GB RAM.
    reference_month_hours is an explicit component convention, not a global AWS
    assumption (OCI Compute adapters should provide OCI_MONTHLY_HOURS=744).
    increment_seconds is mandatory for time-based units, so the core never
    silently presumes per-second billing. Monthly units are prorated linearly
    under the adapter's explicit reference-month convention.
    """

    key: str
    lookup: CalculatorPriceLookup
    units_per_resource: Decimal
    reference_month_hours: Decimal
    increment_seconds: int | None = None
    minimum_billable_seconds: int = 0
    discount_eligible: bool = False


def _finite(
    value: Decimal, label: str, *, allow_zero: bool = True, validate_input_scale: bool = False
) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or (not allow_zero and value == 0)
        or value > MAX_FINANCIAL_VALUE
        or (validate_input_scale and value.as_tuple().exponent < -18)
    ):
        raise ValueError(f"invalid_{label}")
    return value


def _money(value: Decimal) -> Decimal:
    return _finite(value, "monetary_value").quantize(CENT, rounding=ROUND_HALF_UP)


def duration_seconds(request: CalculatorEstimateRequest) -> Decimal | None:
    """Elapsed instants, not wall-clock arithmetic; None denotes a reference month."""

    period = request.period
    if period.mode == "monthly":
        return None
    if period.mode == "custom":
        assert period.start_at is not None and period.end_at is not None
        delta = period.end_at.astimezone(UTC) - period.start_at.astimezone(UTC)
        seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(
            delta.microseconds
        ) / Decimal(1000000)
    else:
        assert period.amount is not None
        seconds = (
            period.amount
            * {
                "hours": Decimal(3600),
                "days": Decimal(86400),
                "weeks": Decimal(604800),
            }[period.mode]
        )
    if not seconds.is_finite() or not Decimal(0) < seconds <= MAX_SECONDS:
        raise ValueError("invalid_period_duration")
    return seconds


def _billing_unit(unit: str) -> str:
    suffix = unit.upper().rsplit("_", 1)[-1]
    if suffix not in {*SECONDS_PER_UNIT, "MONTH"}:
        raise ValueError("unsupported_billing_unit")
    return suffix


def _component_usage(
    component: CalculatorMeteredComponent, *, quantity: int, seconds: Decimal | None
) -> tuple[Decimal, Decimal]:
    _finite(
        component.units_per_resource,
        "units_per_resource",
        allow_zero=False,
        validate_input_scale=True,
    )
    month_hours = _finite(
        component.reference_month_hours,
        "reference_month_hours",
        allow_zero=False,
        validate_input_scale=True,
    )
    if month_hours > Decimal(8784):
        raise ValueError("invalid_reference_month_hours")
    unit = _billing_unit(component.lookup.identity.unit)
    if component.minimum_billable_seconds < 0 or component.minimum_billable_seconds > 2678400:
        raise ValueError("invalid_minimum_charge")
    if unit == "MONTH":
        if component.increment_seconds is not None:
            raise ValueError("monthly_units_do_not_use_second_rounding")
        monthly = component.units_per_resource * quantity
        # AWS provisioned storage prices are denominated in GB-month even when
        # invoice usage is metered by second with a per-volume minimum.
        billable = (
            max(
                Decimal(component.minimum_billable_seconds),
                seconds.to_integral_value(rounding=ROUND_CEILING),
            )
            if seconds is not None and component.minimum_billable_seconds
            else seconds
        )
        period = monthly if seconds is None else monthly * billable / (month_hours * Decimal(3600))
    else:
        increment = component.increment_seconds
        if increment is None or not 1 <= increment <= 2678400:
            raise ValueError("time_metering_policy_required")
        unit_seconds = SECONDS_PER_UNIT[unit]
        monthly = (
            component.units_per_resource * quantity * month_hours * Decimal(3600) / unit_seconds
        )
        if seconds is None:
            period = monthly
        else:
            billable = max(
                Decimal(component.minimum_billable_seconds),
                (seconds / Decimal(increment)).to_integral_value(rounding=ROUND_CEILING)
                * Decimal(increment),
            )
            period = component.units_per_resource * quantity * billable / unit_seconds
    return _finite(monthly, "monthly_usage"), _finite(period, "period_usage")


def estimate_calculator_cost(
    request: CalculatorEstimateRequest,
    components: Sequence[CalculatorMeteredComponent],
    *,
    reference_at: datetime | None = None,
    additional_missing_components: Sequence[str] = (),
    missing_status: CalculatorPricingStatus = "missing_configuration",
    extra_warnings: Sequence[str] = (),
) -> CalculatorEstimateResponse:
    """Sum raw Decimal costs before rounding; retain nullable final totals if incomplete.

    Pricing is a single snapshot at the request reference instant, applied to
    the entire selected duration. Adapters must resolve each component against
    that instant; rates are not split across effective-date boundaries here.
    """

    reference = request.pricing_reference_date or reference_at or datetime.now(UTC)
    if reference.utcoffset() is None:
        raise ValueError("pricing_reference_date_must_be_aware")
    reference = reference.astimezone(UTC)
    seconds = duration_seconds(request)
    currency = "USD" if request.provider == "aws" else "BRL"
    terms = request.aws_financial or AwsFinancialTerms() if request.provider == "aws" else None
    warnings: list[str] = []
    if seconds is not None:
        warnings.append("price_snapshot_applied_to_entire_period")
    warnings.extend(extra_warnings)
    if len(set(additional_missing_components)) != len(additional_missing_components):
        raise ValueError("duplicate_missing_component_key")
    if missing_status in {"priced", "partially_priced"}:
        raise ValueError("invalid_missing_component_status")

    line_items: list[CalculatorPricingComponent] = []
    missing: list[str] = []
    failures: list[CalculatorPricingStatus] = []
    monthly_eligible = Decimal(0)
    monthly_noneligible = Decimal(0)
    period_eligible = Decimal(0)
    period_noneligible = Decimal(0)
    sources: set[str] = set()
    seen: set[str] = set()

    for component in components:
        lookup = component.lookup
        if not component.key or component.key in seen:
            raise ValueError("duplicate_or_empty_component_key")
        seen.add(component.key)
        if lookup.identity.provider != request.provider:
            raise ValueError("component_provider_mismatch")
        if component.discount_eligible and request.provider != "aws":
            raise ValueError("oci_discount_is_forbidden")
        if lookup.reference_at.astimezone(UTC) != reference:
            raise ValueError("component_pricing_snapshot_mismatch")
        monthly_units, period_units = _component_usage(
            component, quantity=request.quantity, seconds=seconds
        )
        price = lookup.price if lookup.available else None
        if price is not None and (price.identity != lookup.identity or price.currency != currency):
            raise ValueError("component_price_identity_or_currency_mismatch")
        monthly_cost = _finite(price.amount * monthly_units, "monthly_cost") if price else None
        period_cost = _finite(price.amount * period_units, "period_cost") if price else None
        if price is None:
            missing.append(component.key)
            failures.append(lookup.status)
            warnings.append(lookup.warning_code or lookup.status)
        else:
            sources.add(price.source)
            if component.discount_eligible:
                monthly_eligible += monthly_cost
                period_eligible += period_cost
            else:
                monthly_noneligible += monthly_cost
                period_noneligible += period_cost
        line_items.append(
            CalculatorPricingComponent(
                service=lookup.identity.service,
                sku=lookup.identity.sku,
                unit=lookup.identity.unit,
                description=price.description if price else None,
                pricing_status=lookup.status,
                pricing_item_id=price.id if price else None,
                region_code=lookup.region_code,
                product_sku=lookup.product_sku,
                rate_code=lookup.rate_code,
                import_batch_id=lookup.import_batch_id,
                synced_at=lookup.synced_at,
                unit_price=price.amount if price else None,
                monthly_units=monthly_units,
                period_units=period_units,
                monthly_original_cost=_money(monthly_cost) if monthly_cost is not None else None,
                period_original_cost=_money(period_cost) if period_cost is not None else None,
                discount_eligible=component.discount_eligible,
                currency=currency,
                source=price.source if price else None,
                effective_from=price.effective_from if price else None,
                effective_until=price.effective_until if price else None,
                reference_month_hours=component.reference_month_hours,
                billing_increment_seconds=component.increment_seconds,
                minimum_billable_seconds=component.minimum_billable_seconds,
            )
        )

    priced_count = len(components) - len(missing)
    for key in additional_missing_components:
        if not key or key in seen:
            raise ValueError("duplicate_or_empty_component_key")
        seen.add(key)
        missing.append(key)
        failures.append(missing_status)
    if not components and not additional_missing_components:
        status: CalculatorPricingStatus = "unsupported_configuration"
        warnings.append("service_adapter_not_available")
    elif missing and priced_count:
        status = "partially_priced"
    elif missing:
        status = next((s for s in STATUS_PRIORITY if s in failures), failures[0])
    else:
        status = "priced"

    payload = dict(
        provider=request.provider,
        service=request.resource_configuration.service,
        region=request.region,
        resource_configuration=request.resource_configuration,
        quantity=request.quantity,
        period=request.period,
        period_duration_hours=seconds / Decimal(3600) if seconds is not None else None,
        pricing_components=line_items,
        pricing_source=(next(iter(sources)) if len(sources) == 1 else "MULTIPLE_SOURCES")
        if sources
        else None,
        pricing_reference_date=reference,
        pricing_currency=currency,
        final_currency=currency if terms is None or not terms.conversion_enabled else "BRL",
        pricing_status=status,
        missing_pricing_components=missing,
        warnings=list(dict.fromkeys(warnings)),
    )
    if terms is not None:
        payload.update(
            discount_percent=terms.discount_percent,
            conversion_enabled=terms.conversion_enabled,
            usd_brl_rate=terms.usd_brl_rate,
            tax_percent=terms.tax_percent if terms.conversion_enabled else None,
        )
    if priced_count and missing:
        payload.update(
            monthly_known_subtotal=_money(monthly_eligible + monthly_noneligible),
            period_known_subtotal=_money(period_eligible + period_noneligible),
        )
    if status == "priced":
        if terms is None:
            monthly_total = _money(monthly_noneligible)
            period_total = _money(period_noneligible)
            payload.update(
                monthly_original_cost=monthly_total,
                period_original_cost=period_total,
                monthly_net_cost=monthly_total,
                period_net_cost=period_total,
                monthly_final_cost=monthly_total,
                period_final_cost=period_total,
            )
        else:
            monthly = apply_aws_financial_terms(
                eligible_original_usd=monthly_eligible,
                noneligible_original_usd=monthly_noneligible,
                terms=terms,
            )
            period = apply_aws_financial_terms(
                eligible_original_usd=period_eligible,
                noneligible_original_usd=period_noneligible,
                terms=terms,
            )
            payload.update(
                monthly_original_cost=monthly.original_usd,
                period_original_cost=period.original_usd,
                monthly_net_cost=monthly.net_usd,
                period_net_cost=period.net_usd,
                monthly_final_cost=monthly.final_amount,
                period_final_cost=period.final_amount,
                monthly_discount_amount=monthly.discount_amount_usd,
                period_discount_amount=period.discount_amount_usd,
                monthly_converted_cost=monthly.converted_brl,
                period_converted_cost=period.converted_brl,
                monthly_tax_amount=monthly.tax_amount_brl,
                period_tax_amount=period.tax_amount_brl,
                # Task 27.1 legacy singular totals correspond to the monthly summary.
                discount_amount=monthly.discount_amount_usd,
                tax_amount=monthly.tax_amount_brl,
            )
    return CalculatorEstimateResponse.model_validate(payload)
