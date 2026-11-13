"""Task 28.3: offline AWS Bulk fixtures, isolated SQLite and discovery contracts.

Synthetic prices exercise the *official file structure*, not actual AWS pricing.
PostgreSQL exclusion/migration tests continue in test_aws_regional_pricing.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.aws_pricing import AwsPricingImportBatch, AwsPricingRateDetail
from app.models.pricing import PricingCatalogItem
from app.services.aws_pricing_bulk import (
    AwsBulkImportError,
    discover_price_list,
    stage_offer,
    validate_official_url,
)
from app.services.aws_pricing_import import import_aws_prices
from app.services.aws_pricing_normalization import (
    classify_product,
    coverage_summary,
    normalize_rate,
)
from app.services.aws_regional_pricing import (
    AwsPricingConflictError,
    AwsRegionalPricingRepository,
    AwsRegionalPricingResolver,
)

AT = "2026-11-13T00:00:00Z"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _offer(
    service="AmazonVPC", region="sa-east-1", version="20261113000000",
    amount="0.00500000", effective=AT, tier=False,
):
    sku = "SKU-VPC-1"
    return {
        "formatVersion": "aws_v1",
        "offerCode": service,
        "version": version,
        "publicationDate": AT,
        "products": {
            sku: {
                "sku": sku,
                "productFamily": "IP Address",
                "attributes": {
                    "regionCode": region,
                    "locationType": "AWS Region",
                    "usagetype": "SAE1-PublicIPv4:InUseAddress",
                    "group": "PublicIPv4",
                },
            },
        },
        "terms": {
            "OnDemand": {
                sku: {
                    "SKU-VPC-1.JRTCKXETXF": {
                        "offerTermCode": "JRTCKXETXF",
                        "effectiveDate": effective,
                        "priceDimensions": {
                            "SKU-VPC-1.JRTCKXETXF.6YS6EN2CT7": {
                                "rateCode": "SKU-VPC-1.JRTCKXETXF.6YS6EN2CT7",
                                "unit": "Hrs",
                                "beginRange": "0",
                                "endRange": "100" if tier else "Inf",
                                "description": "synthetic hourly public IPv4",
                                "pricePerUnit": {"USD": amount},
                            }
                        },
                    }
                }
            }
        },
    }


def _fixture(tmp_path, obj, name="offer.json"):
    file = tmp_path / name
    file.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    return file


def _import(db, fixture, *, region="sa-east-1", dry_run=False, allow_partial=False):
    return import_aws_prices(
        service_code="AmazonVPC",
        region_code=region,
        db=db,
        dry_run=dry_run,
        allow_partial=allow_partial,
        fixture_path=fixture,
    )


def test_complete_public_ipv4_import_and_region_match(db, tmp_path):
    path = _fixture(tmp_path, _offer())
    result = _import(db, path)
    assert result.status == "published"
    assert result.published_rates == 1
    assert result.coverage["complete"] is True
    resolved = AwsRegionalPricingResolver(db).resolve_aws_price(
        service="ipv4",
        service_code="AmazonVPC",
        region_code="sa-east-1",
        configuration={
            "productFamily": "IP Address",
            "usagetype": "SAE1-PublicIPv4:InUseAddress",
            "group": "PublicIPv4",
            "locationType": "AWS Region",
        },
        billing_unit="IP_HOUR",
        reference_at=datetime(2026, 11, 13, 12, tzinfo=UTC),
    )
    assert resolved.status == "priced"
    assert resolved.unit_price == Decimal("0.00500000")
    assert resolved.region_code == "sa-east-1"
    assert resolved.currency == "USD"
    assert resolved.rate_code == "SKU-VPC-1.JRTCKXETXF.6YS6EN2CT7"
    assert result.batch_id == resolved.import_batch_id


def test_idempotent_reimport_keeps_price_and_audit(db, tmp_path):
    path = _fixture(tmp_path, _offer())
    first = _import(db, path)
    second = _import(db, path)
    assert second.status == "already_published"
    assert second.batch_id == first.batch_id
    assert db.scalar(select(func.count()).select_from(PricingCatalogItem)) == 1
    assert db.scalar(select(func.count()).select_from(AwsPricingRateDetail)) == 1


def test_dry_run_does_not_insert_or_set_state(db, tmp_path):
    path = _fixture(tmp_path, _offer())
    result = _import(db, path, dry_run=True)
    assert result.status == "validated"
    assert result.diagnostics["conflicts"] == 0
    assert db.scalar(select(func.count()).select_from(PricingCatalogItem)) == 0
    assert db.scalar(select(func.count()).select_from(AwsPricingImportBatch)) == 0
    assert AwsRegionalPricingRepository(db).get_sync_state(
        service_code="AmazonVPC", region_code="sa-east-1"
    ) is None


def test_missing_region_never_falls_back(db, tmp_path):
    path = _fixture(tmp_path, _offer())
    _import(db, path)
    result = AwsRegionalPricingResolver(db).resolve_aws_price(
        service="ipv4",
        service_code="AmazonVPC",
        region_code="us-east-1",
        configuration={"productFamily": "IP Address", "usagetype": "SAE1-PublicIPv4:InUseAddress"},
        billing_unit="IP_HOUR",
        reference_at=datetime(2026, 11, 13, 12, tzinfo=UTC),
    )
    assert result.status == "sync_required"
    assert result.unit_price is None


def test_official_zero_is_not_missing(db, tmp_path):
    path = _fixture(tmp_path, _offer(amount="0"))
    _import(db, path)
    item = db.scalar(select(PricingCatalogItem))
    assert item.price == Decimal(0)
    assert item.enabled is True


def test_new_version_closes_previous_window_and_preserves_history(db, tmp_path):
    old = _fixture(tmp_path, _offer(), "old.json")
    new = _fixture(
        tmp_path,
        _offer(version="20261114000000", amount="0.00600000",
               effective="2026-11-14T00:00:00Z"),
        "new.json",
    )
    _import(db, old)
    _import(db, new)
    rows = db.scalars(
        select(PricingCatalogItem).order_by(PricingCatalogItem.effective_from)
    ).all()
    assert len(rows) == 2
    assert rows[0].price == Decimal("0.00500000")
    assert rows[1].price == Decimal("0.00600000")
    assert rows[0].effective_until.replace(tzinfo=UTC) == datetime(2026, 11, 14, tzinfo=UTC)


def test_conflicting_price_rolls_back_and_retains_last_good(db, tmp_path):
    old = _fixture(tmp_path, _offer(), "old.json")
    new = _fixture(tmp_path, _offer(version="20261114000000", amount="0.2000"), "new.json")
    original = _import(db, old)
    with pytest.raises(AwsPricingConflictError):
        _import(db, new)
    items = db.scalars(select(PricingCatalogItem)).all()
    assert len(items) == 1
    assert items[0].price == Decimal("0.00500000")
    state = AwsRegionalPricingRepository(db).get_sync_state(
        service_code="AmazonVPC", region_code="sa-east-1"
    )
    assert state.last_successful_batch_id == original.batch_id
    assert state.coverage_status == "synced"


def test_partial_file_is_audited_but_never_published_by_default(db, tmp_path):
    offer = _offer()
    offer["terms"]["OnDemand"] = {}
    path = _fixture(tmp_path, offer)
    result = _import(db, path)
    assert result.status == "partial"
    assert result.published_rates == 0
    assert db.scalar(select(func.count()).select_from(PricingCatalogItem)) == 0
    batch = db.get(AwsPricingImportBatch, result.batch_id)
    assert batch.status == "partial"


def test_partial_fixture_requires_opt_in_and_no_last_good(db, tmp_path):
    offer = _offer(tier=True)
    path = _fixture(tmp_path, offer)
    result = _import(db, path, allow_partial=True)
    assert result.status == "published_partial"
    item = db.scalar(select(PricingCatalogItem))
    assert item.enabled is False
    assert item.price == Decimal("0.00500000")


def test_reject_negative_price_without_catalog_mutation(db, tmp_path):
    path = _fixture(tmp_path, _offer(amount="-2"))
    result = _import(db, path)
    assert result.status == "partial"
    assert result.rates_rejected == 1
    assert db.scalar(select(func.count()).select_from(PricingCatalogItem)) == 0


def test_reject_unrepresentable_fraction_without_rounding(db, tmp_path):
    path = _fixture(tmp_path, _offer(amount="0.000000001"))
    result = _import(db, path, dry_run=True)
    assert result.rates_rejected == 1
    assert result.rates_staged == 0


def test_non_usd_and_unknown_unit_are_rejected(db, tmp_path):
    offer = _offer()
    dimension = next(iter(next(iter(
        offer["terms"]["OnDemand"].values()
    )).values()))["priceDimensions"]
    row = next(iter(dimension.values()))
    row["pricePerUnit"] = {"BRL": "0.2"}
    path = _fixture(tmp_path, offer)
    assert _import(db, path, dry_run=True).rates_rejected == 1
    row["pricePerUnit"] = {"USD": "0.2"}
    row["unit"] = "Requests"
    path = _fixture(tmp_path, offer)
    assert _import(db, path, dry_run=True).rates_rejected == 1


def test_wrong_region_product_not_persisted(db, tmp_path):
    path = _fixture(tmp_path, _offer(region="us-east-1"))
    result = _import(db, path, dry_run=True)
    assert result.products_matched == 0
    assert result.rates_staged == 0


@pytest.mark.parametrize("url", [
    "http://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/1/file.json",
    "https://evil.example/offers/v1.0/aws/AmazonVPC/1/file.json",
    "https://pricing.us-east-1.amazonaws.com.evil.example/offers/v1.0/aws/AmazonVPC/1/x",
    "https://pricing.us-east-1.amazonaws.com/not-offers/AmazonVPC/1/file",
])
def test_file_url_allowlist_rejects_unofficial_hosts(url):
    with pytest.raises(AwsBulkImportError):
        validate_official_url(url, "AmazonVPC")


class FakeBulkClient:
    def __init__(self):
        self.calls = []

    def describe_services(self, **kw):
        self.calls.append(("describe", kw))
        return {"Services": [{"ServiceCode": "AmazonVPC"}]}

    def list_price_lists(self, **kw):
        self.calls.append(("list", kw))
        return {
            "PriceLists": [{
                "CurrencyCode": "USD",
                "RegionCode": "sa-east-1",
                "FileFormats": ["json"],
                "PriceListArn": "arn:aws:pricing:::price-list/aws/AmazonVPC/USD/20261113/sa-east-1",
            }],
        }

    def get_price_list_file_url(self, **kw):
        self.calls.append(("url", kw))
        return {
            "Url": (
                "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
                "AmazonVPC/20261113/sa-east-1/index.json"
            )
        }


def test_bulk_discovery_keeps_commercial_region_separate_from_endpoint():
    client = FakeBulkClient()
    ref = discover_price_list(
        "AmazonVPC", "sa-east-1",
        effective_at=datetime(2026, 11, 13, tzinfo=UTC),
        client=client,
    )
    assert ref.region_code == "sa-east-1"
    assert client.calls[1][1]["RegionCode"] == "sa-east-1"
    assert ref.url.startswith("https://pricing.us-east-1.amazonaws.com/")


def test_service_discovery_fails_closed_when_missing():
    client = FakeBulkClient()
    with pytest.raises(AwsBulkImportError):
        discover_price_list("AmazonRDS", "sa-east-1", client=client)


def test_parser_rejects_schema_mismatch(tmp_path):
    offer = _offer()
    offer["formatVersion"] = "future_version"
    path = _fixture(tmp_path, offer)
    with pytest.raises(AwsBulkImportError, match="schema"):
        stage_offer(path, tmp_path / "stage.sqlite", service_code="AmazonVPC", region="sa-east-1")


def test_parser_rejects_product_limit(tmp_path):
    path = _fixture(tmp_path, _offer())
    with pytest.raises(AwsBulkImportError, match="processing limit"):
        stage_offer(
            path, tmp_path / "stage.sqlite",
            service_code="AmazonVPC", region="sa-east-1", max_products=0
        )


def test_compute_linux_windows_distinct_financial_attributes():
    base = {
        "productFamily": "Compute Instance",
        "attributes": {
            "regionCode": "sa-east-1", "instanceType": "m6i.large",
            "tenancy": "Shared", "operation": "RunInstances",
            "operatingSystem": "Linux", "preInstalledSw": "NA",
        },
    }
    linux = classify_product("AmazonEC2", "sa-east-1", "SKU-L", base)
    base["attributes"]["operatingSystem"] = "Windows"
    win = classify_product("AmazonEC2", "sa-east-1", "SKU-W", base)
    assert linux is not None and win is not None
    assert linux.financial_attributes != win.financial_attributes
    assert linux.service == "ec2"


def test_tiered_dimension_never_becomes_active_linear_rate():
    product = classify_product(
        "AmazonVPC", "sa-east-1", "SKU-1",
        _offer()["products"]["SKU-VPC-1"]
    )
    assert product is not None
    rate = normalize_rate(
        product, "RATE", "TERM", {"effectiveDate": AT},
        {
            "unit": "Hrs", "beginRange": "0", "endRange": "100",
            "pricePerUnit": {"USD": "0.00"},
        },
    )
    assert rate.amount == Decimal(0)
    assert rate.pricing_status == "unsupported"


def test_component_coverage_is_not_equated_to_file_download():
    result = coverage_summary("AmazonEC2", {"ec2_linux": 1})
    assert result["complete"] is False
    assert "ec2_windows" in result["missing"]
