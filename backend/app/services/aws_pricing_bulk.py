"""AWS Price List Bulk discovery, bounded download and incremental JSON staging.

The official file is parsed twice (products and OnDemand terms) into a temporary
SQLite staging database. No AWS product catalog is held in process memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import ijson
import requests
from botocore.config import Config

from app.services.aws_pricing_normalization import (
    NormalizedProduct,
    NormalizedRate,
    classify_product,
    coverage_component,
    coverage_summary,
    normalize_rate,
    supported_source,
)
from app.services.aws_regional_pricing import AwsPricingValidationError

logger = logging.getLogger(__name__)
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
_OFFICIAL_HOST = re.compile(r"^pricing\.(us-east-1|eu-central-1|ap-south-1)\.amazonaws\.com$")
_OFFICIAL_PATH = re.compile(r"^/offers/v1\.0/aws/[A-Za-z0-9-]+/")
_API_REGIONS = frozenset({"us-east-1", "eu-central-1", "ap-south-1"})


class AwsBulkImportError(RuntimeError):
    """Failed official discovery/download/format validation, with no publication."""


@dataclass(frozen=True, slots=True)
class PriceListReference:
    service_code: str
    region_code: str
    arn: str
    url: str


@dataclass(slots=True)
class StageStats:
    source_version: str = ""
    format_version: str = ""
    publication_date: str = ""
    checksum: str = ""
    source_bytes: int = 0
    products_seen: int = 0
    products_matched: int = 0
    rates_seen: int = 0
    rates_staged: int = 0
    rates_rejected: int = 0
    rates_unsupported: int = 0
    rejects: dict[str, int] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    components: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rates_rejected += 1
        key = reason[:120]
        self.rejects[key] = self.rejects.get(key, 0) + 1
        if len(self.examples) < 20:
            self.examples.append(key)


def _validate_service_region(service_code: str, region: str) -> None:
    if not supported_source(service_code):
        raise AwsBulkImportError("service not mapped for Task 28.3 (no generic-rate fallback)")
    if not _REGION.fullmatch(region):
        raise AwsBulkImportError("invalid commercial AWS region code")


def _client(endpoint_region: str = "us-east-1"):
    if endpoint_region not in _API_REGIONS:
        raise AwsBulkImportError("unsupported AWS Pricing API endpoint region")
    return boto3.client(
        "pricing",
        region_name=endpoint_region,
        config=Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"mode": "standard", "max_attempts": 4},
        ),
    )


def discover_price_list(
    service_code: str,
    region: str,
    *,
    effective_at: datetime | None = None,
    endpoint_region: str = "us-east-1",
    client=None,
) -> PriceListReference:
    """Verify an official service, commercial region and uniquely matching JSON offer."""
    _validate_service_region(service_code, region)
    date = effective_at or datetime.now(UTC)
    if date.tzinfo is None:
        raise AwsBulkImportError("effective_at must be timezone-aware")
    try:
        api = client or _client(endpoint_region)
        token = None
        found = False
        for _ in range(100):
            args = {"MaxResults": 100}
            if token:
                args["NextToken"] = token
            page = api.describe_services(**args)
            if any(x.get("ServiceCode") == service_code for x in page.get("Services", [])):
                found = True
                break
            token = page.get("NextToken")
            if not token:
                break
        if not found:
            raise AwsBulkImportError("service code absent from official DescribeServices")
        token = None
        matches = []
        for _ in range(100):
            args = {
                "ServiceCode": service_code,
                "RegionCode": region,
                "CurrencyCode": "USD",
                "EffectiveDate": date.astimezone(UTC),
                "MaxResults": 100,
            }
            if token:
                args["NextToken"] = token
            page = api.list_price_lists(**args)
            for item in page.get("PriceLists", []):
                if (
                    item.get("RegionCode") == region
                    and item.get("CurrencyCode") == "USD"
                    and "json" in item.get("FileFormats", [])
                    and item.get("PriceListArn")
                ):
                    matches.append(item["PriceListArn"])
            token = page.get("NextToken")
            if not token:
                break
        else:
            raise AwsBulkImportError("official list pagination limit exceeded")
        matches = list(dict.fromkeys(matches))
        if len(matches) != 1:
            raise AwsBulkImportError(
                "no unique regional USD JSON price list: " + str(len(matches))
            )
        response = api.get_price_list_file_url(PriceListArn=matches[0], FileFormat="json")
        url = response.get("Url", "")
        validate_official_url(url, service_code)
        return PriceListReference(service_code, region, matches[0], url)
    except AwsBulkImportError:
        raise
    except Exception as exc:
        logger.warning("aws_bulk_discovery_failed service=%s region=%s reason=%s",
                       service_code, region, type(exc).__name__)
        raise AwsBulkImportError("official AWS Bulk Pricing discovery failed") from exc


def validate_official_url(url: str, service_code: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port
        or not _OFFICIAL_HOST.fullmatch(parsed.hostname or "")
        or not _OFFICIAL_PATH.match(parsed.path)
        or f"/{service_code}/" not in parsed.path
    ):
        raise AwsBulkImportError("pricing URL is not an approved official AWS offer URL")


def download_official_offer(
    reference: PriceListReference,
    destination: Path,
    *,
    max_bytes: int = 2_000_000_000,
    timeout: int = 90,
    session: requests.Session | None = None,
) -> tuple[str, int]:
    validate_official_url(reference.url, reference.service_code)
    if not 1 <= max_bytes <= 10_000_000_000:
        raise AwsBulkImportError("invalid download byte limit")
    http = session or requests.Session()
    last_error = None
    for attempt in range(3):
        try:
            with http.get(
                reference.url,
                stream=True,
                timeout=(5, timeout),
                allow_redirects=False,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError("transient HTTP " + str(response.status_code))
                if response.status_code != 200:
                    raise AwsBulkImportError(
                        "official download returned HTTP " + str(response.status_code)
                    )
                digest = hashlib.sha256()
                total = 0
                with destination.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            raise AwsBulkImportError("official offer exceeds max_bytes")
                        digest.update(chunk)
                        handle.write(chunk)
                if total == 0:
                    raise AwsBulkImportError("official offer is empty")
                return digest.hexdigest(), total
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(min(2**attempt, 4))
            else:
                break
        finally:
            if attempt and destination.exists() and not destination.stat().st_size:
                destination.unlink()
    raise AwsBulkImportError("official offer download failed after bounded retries") from last_error


def _scalar(path: Path, prefix: str):
    with path.open("rb") as handle:
        return next(ijson.items(handle, prefix), None)


def _effective(value: str) -> str:
    if not isinstance(value, str):
        raise AwsPricingValidationError("invalid date")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise AwsPricingValidationError("invalid timezone-aware effectiveDate") from exc
    return at.astimezone(UTC).isoformat()


def _read_product(record: str) -> NormalizedProduct:
    value = json.loads(record)
    return NormalizedProduct(**value)


def iter_staged_rates(database: Path) -> Iterator[NormalizedRate]:
    """Read a bounded cursor, looking up official product identity from local disk."""
    with sqlite3.connect(database) as db:
        cursor = db.execute(
            "SELECT p.data, r.rate FROM rates r JOIN products p ON p.sku = r.sku "
            "ORDER BY r.sku, json_extract(r.rate, '$.effective_at'), r.id"
        )
        for product_json, rate_json in cursor:
            product = _read_product(product_json)
            payload = json.loads(rate_json)
            payload["amount"] = Decimal(payload["amount"])
            yield NormalizedRate(product=product, **payload)


def stage_offer(
    source: Path,
    staging: Path,
    *,
    service_code: str,
    region: str,
    max_products: int = 1_000_000,
    max_rates: int = 1_000_000,
) -> StageStats:
    """Stage official JSON without loading products/terms collections into memory."""
    _validate_service_region(service_code, region)
    if max_products < 1 or max_rates < 1:
        raise AwsBulkImportError("processing limits must be positive")
    stats = StageStats()
    try:
        stats.format_version = _scalar(source, "formatVersion") or ""
        stats.source_version = str(_scalar(source, "version") or "")
        stats.publication_date = str(_scalar(source, "publicationDate") or "")
        offer_code = _scalar(source, "offerCode")
        if (
            stats.format_version != "aws_v1"
            or not stats.source_version
            or offer_code != service_code
        ):
            raise AwsBulkImportError("incompatible official offer schema/version/service")
        with sqlite3.connect(staging) as db:
            db.execute("CREATE TABLE products (sku TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute(
                "CREATE TABLE rates (id INTEGER PRIMARY KEY, sku TEXT NOT NULL, rate TEXT NOT NULL)"
            )
            with source.open("rb") as handle:
                for sku, payload in ijson.kvitems(handle, "products"):
                    stats.products_seen += 1
                    if stats.products_seen > max_products:
                        raise AwsBulkImportError("product processing limit exceeded")
                    if not isinstance(payload, dict):
                        stats.reject("invalid product payload")
                        continue
                    product = classify_product(service_code, region, sku, payload)
                    if not product:
                        continue
                    stats.products_matched += 1
                    db.execute(
                        "INSERT INTO products (sku,data) VALUES (?,?)",
                        (sku, json.dumps(asdict(product), sort_keys=True)),
                    )
            db.commit()
            with source.open("rb") as handle:
                for sku, terms in ijson.kvitems(handle, "terms.OnDemand"):
                    product_row = db.execute(
                        "SELECT data FROM products WHERE sku = ?", (sku,)
                    ).fetchone()
                    if product_row is None:
                        continue
                    product = _read_product(product_row[0])
                    if not isinstance(terms, dict):
                        stats.reject("invalid OnDemand terms")
                        continue
                    for term_key, term in terms.items():
                        if not isinstance(term, dict):
                            stats.reject("invalid term")
                            continue
                        dimensions = term.get("priceDimensions")
                        if not isinstance(dimensions, dict):
                            stats.reject("invalid priceDimensions")
                            continue
                        for code, dimension in dimensions.items():
                            stats.rates_seen += 1
                            if stats.rates_seen > max_rates:
                                raise AwsBulkImportError("rate processing limit exceeded")
                            try:
                                rate = normalize_rate(
                                    product,
                                    str(code),
                                    str(term.get("offerTermCode") or term_key),
                                    term,
                                    dimension,
                                )
                                payload = asdict(rate)
                                payload.pop("product")
                                payload["amount"] = str(rate.amount)
                                payload["effective_at"] = _effective(rate.effective_at)
                                if len(product.sku + ":" + rate.rate_code) > 160:
                                    raise AwsPricingValidationError("composite SKU exceeds 160")
                            except (AwsPricingValidationError, ValueError, TypeError) as exc:
                                stats.reject(str(exc))
                                continue
                            db.execute(
                                "INSERT INTO rates (sku,rate) VALUES (?,?)",
                                (sku, json.dumps(payload, sort_keys=True)),
                            )
                            stats.rates_staged += 1
                            if rate.pricing_status == "unsupported":
                                stats.rates_unsupported += 1
                            else:
                                component = coverage_component(rate)
                                stats.components[component] = stats.components.get(component, 0) + 1
            db.commit()
    except (ijson.JSONError, sqlite3.Error, OSError) as exc:
        raise AwsBulkImportError("invalid official JSON or exhausted staging space") from exc
    stats.coverage = coverage_summary(service_code, stats.components)
    return stats
