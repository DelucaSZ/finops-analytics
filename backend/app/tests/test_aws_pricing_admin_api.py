"""Task 28.5 administrative pricing contracts: offline, deterministic and fail-closed."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.account import AwsAccount
from app.services.aws_regional_pricing import AwsRegionalPricingRepository
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers

BASE = "/api/v1/pricing/aws"
EFFECTIVE = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_pricing_aws_read_and_mutation_are_admin_only(auth_env, role):
    http, _, tokens, _ = auth_env
    assert http.get(BASE + "/meta", headers=headers(tokens, role)).status_code == 403
    assert (
        http.get(BASE + "/rates?region=sa-east-1", headers=headers(tokens, role)).status_code
        == 403
    )
    assert (
        http.post(
            BASE + "/sync",
            headers=headers(tokens, role),
            json={"service_code": "AmazonEC2", "region_code": "sa-east-1"},
        ).status_code
        == 403
    )


def test_empty_catalog_metadata_filters_and_invalid_region(auth_env):
    http, _, tokens, _ = auth_env
    meta = http.get(BASE + "/meta", headers=headers(tokens))
    assert meta.status_code == 200
    assert meta.json()["currency"] == "USD"
    assert "AmazonEC2" in meta.json()["services"]
    empty = http.get(BASE + "/rates?region=sa-east-1", headers=headers(tokens))
    assert empty.status_code == 200 and empty.json()["total"] == 0
    assert (
        http.get(BASE + "/rates?region=wrong", headers=headers(tokens)).status_code == 400
    )
    assert (
        http.get(BASE + "/rates?region=sa-east-1&limit=999", headers=headers(tokens)).status_code
        == 422
    )


def test_exact_decimal_rate_history_and_strict_region_isolation(auth_env):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db, db.begin():
        catalog = AwsRegionalPricingRepository(db)
        product = catalog.put_product(
            service="ec2",
            service_code="AmazonEC2",
            region_code="sa-east-1",
            product_sku="EC2-TEST-SKU",
            product_family="Compute Instance",
            description="Test-only AWS price fixture",
            financial_attributes={
                "instanceType": "t3.small",
                "operatingSystem": "Linux",
                "tenancy": "Shared",
                "operation": "RunInstances",
            },
            product_attributes={
                "instanceType": "t3.small",
                "operatingSystem": "Linux",
                "tenancy": "Shared",
                "operation": "RunInstances",
            },
        )
        catalog.put_rate(
            product=product,
            rate_code="EC2.TEST.RATE",
            term_code="JRTCKXETXF",
            billing_unit="INSTANCE_HOUR",
            aws_unit="Hrs",
            amount=Decimal("0.00425000"),
            effective_from=EFFECTIVE,
            source="AWS_PUBLIC_PRICE_LIST",
            source_effective_at=EFFECTIVE,
        )

    listing = http.get(
        BASE + "/rates?region=sa-east-1&q=EC2-TEST-SKU&limit=1",
        headers=headers(tokens),
    )
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["price"] == "0.00425000"
    assert row["currency"] == "USD"
    assert row["product_sku"] == "EC2-TEST-SKU"
    assert row["region_code"] == "sa-east-1"
    assert (
        http.get(BASE + "/rates?region=us-east-1", headers=headers(tokens)).json()["total"]
        == 0
    )
    detail = http.get(BASE + f"/rates/{row['id']}", headers=headers(tokens))
    assert detail.status_code == 200
    history = http.get(BASE + f"/rates/{row['id']}/history", headers=headers(tokens))
    assert history.status_code == 200 and history.json()["total"] == 1
    products = http.get(
        BASE + "/products?region=sa-east-1&q=EC2-TEST-SKU",
        headers=headers(tokens),
    )
    assert products.status_code == 200 and products.json()["total"] == 1
    coverage = http.get(
        BASE + "/sync/coverage?service=AmazonEC2&region=sa-east-1",
        headers=headers(tokens),
    )
    assert coverage.status_code == 200
    assert coverage.json()["active_rates"] == 1
    runs = http.get(BASE + "/sync/runs?region=sa-east-1", headers=headers(tokens))
    assert runs.status_code == 200 and runs.json()["total"] == 0


def test_manual_submission_requires_optin_and_deduplicates(auth_env, monkeypatch):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        aws = db.get(AwsAccount, 1)
        aws.regions = ["sa-east-1"]
        db.commit()
    monkeypatch.delenv("AVEN_AWS_PRICING_IMPORT_ENABLED", raising=False)
    disabled = http.post(
        BASE + "/sync",
        headers=headers(tokens),
        json={"service_code": "AmazonEC2", "region_code": "sa-east-1"},
    )
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["code"] == "import_disabled"
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    invalid = http.post(
        BASE + "/sync",
        headers=headers(tokens),
        json={"service_code": "AmazonEC2", "region_code": "not-a-region"},
    )
    assert invalid.status_code == 400
    submitted = http.post(
        BASE + "/sync",
        headers=headers(tokens),
        json={"service_code": "AmazonEC2", "region_code": "sa-east-1"},
    )
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "queued"
    request_id = submitted.json()["id"]
    poll = http.get(
        BASE + f"/sync/requests/{request_id}", headers=headers(tokens)
    )
    assert poll.status_code == 200 and poll.json()["status"] == "queued"
    concurrent = http.post(
        BASE + "/sync",
        headers=headers(tokens),
        json={"service_code": "AmazonEC2", "region_code": "sa-east-1"},
    )
    assert concurrent.status_code == 409
    assert concurrent.json()["detail"]["code"] == "sync_busy"
