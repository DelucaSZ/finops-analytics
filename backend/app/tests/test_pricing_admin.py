from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.pricing import PricingCatalogItem
from app.services.pricing_catalog import PricingNotFoundError, PricingResolver
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _seed_item(http, tokens, sku: str):
    response = http.get(
        f"/api/v1/pricing/oci?q={sku}&status=all",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    return next(row for row in response.json()["items"] if row["sku"] == sku)


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_pricing_admin_is_restricted_to_admin(auth_env, role):
    http, _, tokens, _ = auth_env
    assert http.get("/api/v1/pricing/oci", headers=headers(tokens, role)).status_code == 403
    assert (
        http.post(
            "/api/v1/pricing/oci",
            headers=headers(tokens, role),
            json={
                "service": "compute",
                "sku": "TEST.PRICE",
                "description": "test",
                "unit": "INSTANCE_HOUR",
                "price": "1.00",
            },
        ).status_code
        == 403
    )


def test_pricing_list_search_filter_and_pagination(auth_env):
    http, _, tokens, _ = auth_env

    response = http.get(
        "/api/v1/pricing/oci?service=block_volume&status=active&limit=1",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["provider"] == "oci"
    assert data["items"][0]["currency"] == "BRL"

    search = http.get(
        "/api/v1/pricing/oci?q=WINDOWS_LICENSE_OCPU&status=all",
        headers=headers(tokens),
    ).json()
    assert search["total"] == 1
    assert search["items"][0]["sku"] == "WINDOWS_LICENSE_OCPU"

    metadata = http.get(
        "/api/v1/pricing/oci/meta",
        headers=headers(tokens),
    ).json()
    assert metadata["provider"] == "oci"
    assert metadata["currency"] == "BRL"
    assert {"compute", "block_volume"} <= set(metadata["services"])


def test_create_pricing_forces_brl_manual_and_preserves_decimal(auth_env):
    http, _, tokens, _ = auth_env
    start = (utcnow() + timedelta(days=30)).isoformat()

    response = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Future.Test.OCPU",
            "description": "Future test OCPU",
            "unit": "OCPU_HOUR",
            "price": "0.12345678",
            "effective_from": start,
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["currency"] == "BRL"
    assert item["source"] == "MANUAL"
    assert Decimal(str(item["price"])) == Decimal("0.12345678")

    future = http.get(
        "/api/v1/pricing/oci?status=future&q=VM.Future.Test.OCPU",
        headers=headers(tokens),
    ).json()
    assert future["total"] == 1

    spoofed = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Bad.Currency",
            "description": "bad currency",
            "unit": "OCPU_HOUR",
            "price": "1",
            "currency": "USD",
        },
    )
    assert spoofed.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [("price", "-0.01"), ("unit", "bad-unit")],
)
def test_invalid_pricing_values_are_rejected(auth_env, field, value):
    http, _, tokens, _ = auth_env
    payload = {
        "service": "compute",
        "sku": "VM.Invalid.Test",
        "description": "Invalid item",
        "unit": "OCPU_HOUR",
        "price": "0.1",
    }
    payload[field] = value
    response = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json=payload,
    )
    assert response.status_code == 422


def test_conflicting_effective_interval_is_rejected(auth_env):
    http, _, tokens, _ = auth_env
    response = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Standard.E4.Flex.OCPU",
            "description": "conflict",
            "unit": "OCPU_HOUR",
            "price": "0.099",
            "effective_from": (utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "pricing_overlap"


def test_price_change_creates_new_effective_version_and_preserves_history(auth_env):
    http, engine, tokens, _ = auth_env
    current = _seed_item(http, tokens, "VM.Standard.E4.Flex.OCPU")
    transition = utcnow() + timedelta(days=1)

    response = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={
            "price": "0.07000000",
            "effective_from": transition.isoformat(),
            "reason": "Atualização contratual de teste",
        },
    )
    assert response.status_code == 200, response.text
    replacement = response.json()
    assert replacement["id"] != current["id"]
    assert Decimal(str(replacement["price"])) == Decimal("0.07000000")
    assert replacement["currency"] == "BRL"
    assert replacement["source"] == "MANUAL"

    history = http.get(
        f"/api/v1/pricing/oci/{replacement['id']}/history",
        headers=headers(tokens),
    )
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 2
    original = next(row for row in rows if row["id"] == current["id"])
    assert Decimal(str(original["price"])) == Decimal(str(current["price"]))
    assert original["effective_until"] is not None

    with Session(engine) as db:
        resolver = PricingResolver(db)
        old = resolver.resolve_price(
            provider="oci",
            service="compute",
            sku="VM.Standard.E4.Flex.OCPU",
            unit="OCPU_HOUR",
            at=transition - timedelta(seconds=1),
            expected_currency="BRL",
        )
        new = PricingResolver(db).resolve_price(
            provider="oci",
            service="compute",
            sku="VM.Standard.E4.Flex.OCPU",
            unit="OCPU_HOUR",
            at=transition + timedelta(seconds=1),
            expected_currency="BRL",
        )
    assert old.amount == Decimal("0.06890000")
    assert new.amount == Decimal("0.07000000")


def test_deactivate_is_idempotent_without_deleting_history(auth_env):
    http, engine, tokens, _ = auth_env
    create = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Deactivate.Test",
            "description": "Deactivate test",
            "unit": "INSTANCE_HOUR",
            "price": "2.50",
            "effective_from": (utcnow() - timedelta(minutes=1)).isoformat(),
        },
    )
    assert create.status_code == 201, create.text
    item_id = create.json()["id"]

    first = http.post(
        f"/api/v1/pricing/oci/{item_id}/deactivate",
        headers=headers(tokens),
        json={"reason": "SKU substituído para teste"},
    )
    second = http.post(
        f"/api/v1/pricing/oci/{item_id}/deactivate",
        headers=headers(tokens),
        json={"reason": "Retry idempotente"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["enabled"] is False
    assert second.json()["enabled"] is False

    with Session(engine) as db:
        row = db.scalar(select(PricingCatalogItem).where(PricingCatalogItem.id == item_id))
        assert row is not None
        assert row.enabled is False
        with pytest.raises(PricingNotFoundError):
            PricingResolver(db).resolve_price(
                provider="oci",
                service="compute",
                sku="VM.Deactivate.Test",
                unit="INSTANCE_HOUR",
                expected_currency="BRL",
            )
