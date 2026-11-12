"""Read-only AWS Price List Query API access for calculator adapters.

No Cost Explorer estimates, credential material, pricing mutation, or account-specific
billing. AWS Pricing API endpoint location is NOT the requested resource region.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

import boto3
from botocore.config import Config

from app.services.calculator_foundation import CalculatorPriceLookup
from app.services.pricing_catalog import PricingIdentity, ResolvedPrice

logger = logging.getLogger(__name__)
_SOURCE = "AWS_PUBLIC_PRICE_LIST"
_MAX_PAGES = 12
_MAX_RESULTS = 100


class AwsPriceUnavailable(RuntimeError):
    """Live AWS Price List service or credentials unavailable."""


class AwsPriceAmbiguous(RuntimeError):
    """The requested product does not resolve to one exact rate."""


def _client():
    # Uses the backend's default credential chain (for example, instance role).
    # A customer's integrated AWS account is never required.
    return boto3.client(
        "pricing",
        region_name="us-east-1",
        config=Config(connect_timeout=3, read_timeout=7, retries={"max_attempts": 2}),
    )


@lru_cache(maxsize=256)
def _products(service_code: str, filters: tuple[tuple[str, str], ...], bucket: int):
    client = _client()
    items = []
    next_token = None
    for _ in range(_MAX_PAGES):
        args = {
            "ServiceCode": service_code,
            "FormatVersion": "aws_v1",
            "Filters": [
                {
                    "Type": "CONTAINS" if k.startswith("contains:") else "TERM_MATCH",
                    "Field": k.removeprefix("contains:"),
                    "Value": v,
                }
                for k, v in filters
            ],
            "MaxResults": _MAX_RESULTS,
        }
        if next_token:
            args["NextToken"] = next_token
        try:
            result = client.get_products(**args)
        except Exception as exc:
            logger.warning("aws_calculator_pricing_unavailable service=%s reason=%s",
                           service_code, type(exc).__name__)
            raise AwsPriceUnavailable("aws_pricing_api_unavailable") from exc
        items.extend(json.loads(row) for row in result.get("PriceList", ()))
        next_token = result.get("NextToken")
        if not next_token:
            return tuple(items)
    # Never interpret a truncated catalog as authoritative.
    raise AwsPriceUnavailable("aws_pricing_result_exceeds_page_limit")


def _utc_effective(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _price_dimension(row: dict, *, unit: str, at: datetime):
    terms = row.get("terms", {}).get("OnDemand", {})
    candidates = []
    for term in terms.values():
        try:
            effective = _utc_effective(term["effectiveDate"])
        except (KeyError, TypeError, ValueError):
            continue
        if effective > at:
            continue
        for rate_code, dimension in term.get("priceDimensions", {}).items():
            if dimension.get("unit") != unit:
                continue
            # Tiered and minimum-charge terms need a dedicated billing contract.
            if str(dimension.get("beginRange")) != "0" or str(dimension.get("endRange")) != "Inf":
                continue
            try:
                value = Decimal(dimension["pricePerUnit"]["USD"])
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
            if value.is_finite() and value >= 0:
                candidates.append((rate_code, dimension, value, effective))
    return candidates


class AwsPublicPriceResolver:
    """Unique USD, region-qualified, current On-Demand rate, fail closed."""

    def __init__(self, fetcher: Callable | None = None) -> None:
        self._fetcher = fetcher or _products

    def products(self, service_code: str, filters: dict[str, str]) -> tuple[dict, ...]:
        return self._fetcher(
            service_code, tuple(sorted(filters.items())), int(time.time() // 3600)
        )

    def resolve(
        self,
        *,
        service: str,
        region: str,
        family: str,
        filters: dict[str, str],
        matches: Callable[[dict], bool],
        unit: str,
        aws_unit: str,
        at: datetime,
        key: str,
    ) -> CalculatorPriceLookup:
        identity = PricingIdentity("aws", service, f"UNAVAILABLE:{region}:{key}", unit)
        def missing(status, warning):
            return CalculatorPriceLookup(identity, status, None, at, warning)
        if at.utcoffset() is None:
            raise ValueError("pricing reference must have timezone")
        at = at.astimezone(UTC)
        if at > datetime.now(UTC):
            return missing("price_not_effective", "future_aws_price_snapshot_unavailable")
        selectors = dict(filters)
        selectors["regionCode"] = region
        selectors["productFamily"] = family
        try:
            rows = self.products("AmazonEC2" if service == "ec2" else "AmazonRDS", selectors)
        except AwsPriceUnavailable as exc:
            return missing("pricing_configuration_error", str(exc))
        candidates = []
        for row in rows:
            product = row.get("product", {})
            attr = product.get("attributes", {})
            if (
                product.get("productFamily") != family
                or attr.get("regionCode") != region
                or attr.get("locationType") not in (None, "AWS Region")
                or not matches(attr)
            ):
                continue
            for code, dimension, amount, effective in _price_dimension(row, unit=aws_unit, at=at):
                candidates.append((row, code, dimension, amount, effective))
        if not candidates:
            return missing("sku_missing", f"aws_{service}_{key}_price_unavailable")
        if len(candidates) != 1:
            return missing("pricing_configuration_error", f"aws_{service}_{key}_ambiguous_price")
        row, rate_code, dimension, amount, effective = candidates[0]
        sku = str(row["product"]["sku"])
        resolved_id = PricingIdentity("aws", service, f"{sku}:{rate_code}", unit)
        price = ResolvedPrice(
            id=rate_code,
            provider="aws",
            service=service,
            sku=resolved_id.sku,
            description=dimension.get("description") or f"AWS {family} {sku}",
            unit=unit,
            amount=amount,
            currency="USD",
            effective_from=effective,
            effective_until=None,
            source=_SOURCE,
        )
        return CalculatorPriceLookup(resolved_id, "priced", price, at)


def missing_aws_lookup(
    service: str, region: str, key: str, unit: str, at: datetime,
    status: str = "unsupported_configuration", warning: str | None = None,
) -> CalculatorPriceLookup:
    return CalculatorPriceLookup(
        PricingIdentity("aws", service, f"UNAVAILABLE:{region}:{key}", unit),
        status, None, at, warning or status,
    )
