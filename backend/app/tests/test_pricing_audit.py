from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.pricing import PricingCatalogItem
from app.models.pricing_audit import PricingAuditAction, PricingAuditEvent
from app.models.user import User
from app.services.pricing_admin import PricingAdminValidationError
from app.services.pricing_audit import AuditedPricingCatalogAdminService
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _item(http, tokens, sku: str) -> dict:
    response = http.get(
        f"/api/v1/pricing/oci?q={sku}&status=all",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    return next(row for row in response.json()["items"] if row["sku"] == sku)


def test_create_records_actor_after_and_exact_decimal(auth_env):
    http, _, tokens, ids = auth_env
    response = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Audit.Create",
            "description": "Audit create",
            "unit": "OCPU_HOUR",
            "price": "0.12345678",
            "reason": "Nova condição comercial",
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()

    audit = http.get(
        f"/api/v1/pricing/oci/{item['id']}/audit",
        headers=headers(tokens),
    )
    assert audit.status_code == 200
    event = audit.json()["items"][0]
    assert event["action"] == PricingAuditAction.CREATED
    assert event["actor_type"] == "USER"
    assert event["actor_id"] == ids["admin"]
    assert event["actor_email"] == "admin@example.com"
    assert event["before_data"] is None
    assert event["after_data"]["price"] == "0.12345678"
    assert event["after_data"]["currency"] == "BRL"
    assert event["reason"] == "Nova condição comercial"


def test_financial_change_requires_reason_and_client_cannot_spoof_actor(auth_env):
    http, _, tokens, _ = auth_env
    current = _item(http, tokens, "VM.Standard.E4.Flex.OCPU")
    transition = (utcnow() + timedelta(days=1)).isoformat()

    missing_reason = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={"price": "0.07000000", "effective_from": transition},
    )
    assert missing_reason.status_code == 422

    spoofed = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={
            "price": "0.07000000",
            "effective_from": transition,
            "reason": "Mudança válida",
            "actor_id": "spoofed",
        },
    )
    assert spoofed.status_code == 422


def test_future_price_records_semantic_event_before_after_and_reason(auth_env):
    http, _, tokens, ids = auth_env
    current = _item(http, tokens, "VM.Standard.E4.Flex.Memory")
    transition = utcnow() + timedelta(days=2)

    changed = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={
            "price": "0.01111111",
            "effective_from": transition.isoformat(),
            "reason": "Atualização da tabela comercial OCI",
        },
    )
    assert changed.status_code == 200, changed.text
    replacement = changed.json()

    data = http.get(
        f"/api/v1/pricing/oci/{replacement['id']}/audit",
        headers=headers(tokens),
    ).json()
    assert data["total"] == 1
    event = data["items"][0]
    assert event["action"] == PricingAuditAction.FUTURE_VERSION_CREATED
    assert event["actor_id"] == ids["admin"]
    assert event["reason"] == "Atualização da tabela comercial OCI"
    assert event["before_data"]["id"] == current["id"]
    assert event["before_data"]["price"] == current["price"]
    assert event["before_data"]["currency"] == "BRL"
    assert event["after_data"]["id"] == replacement["id"]
    assert event["after_data"]["price"] == "0.01111111"
    assert event["after_data"]["currency"] == "BRL"


def test_metadata_change_is_audited_without_forcing_financial_reason(auth_env):
    http, _, tokens, _ = auth_env
    current = _item(http, tokens, "WINDOWS_LICENSE_OCPU")
    response = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={"description": "Windows license updated description"},
    )
    assert response.status_code == 200, response.text

    event = http.get(
        f"/api/v1/pricing/oci/{current['id']}/audit",
        headers=headers(tokens),
    ).json()["items"][0]
    assert event["action"] == PricingAuditAction.METADATA_CHANGED
    assert event["reason"] is None
    assert event["before_data"]["description"] != event["after_data"]["description"]


def test_deactivation_requires_reason_and_retry_does_not_duplicate_event(auth_env):
    http, _, tokens, _ = auth_env
    created = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Audit.Deactivate",
            "description": "Deactivate audit",
            "unit": "INSTANCE_HOUR",
            "price": "1.00",
        },
    ).json()

    assert (
        http.post(
            f"/api/v1/pricing/oci/{created['id']}/deactivate",
            headers=headers(tokens),
            json={},
        ).status_code
        == 422
    )
    for reason in ("SKU substituído", "retry"):
        response = http.post(
            f"/api/v1/pricing/oci/{created['id']}/deactivate",
            headers=headers(tokens),
            json={"reason": reason},
        )
        assert response.status_code == 200

    data = http.get(
        f"/api/v1/pricing/oci/{created['id']}/audit",
        headers=headers(tokens),
    ).json()
    actions = [event["action"] for event in data["items"]]
    assert actions.count(PricingAuditAction.CREATED) == 1
    assert actions.count(PricingAuditAction.DEACTIVATED) == 1
    deactivated = next(event for event in data["items"] if event["action"] == "DEACTIVATED")
    assert deactivated["before_data"]["enabled"] is True
    assert deactivated["after_data"]["enabled"] is False
    assert deactivated["reason"] == "SKU substituído"


def test_audit_history_is_paginated_newest_first(auth_env):
    http, _, tokens, _ = auth_env
    created = http.post(
        "/api/v1/pricing/oci",
        headers=headers(tokens),
        json={
            "service": "compute",
            "sku": "VM.Audit.Pagination",
            "description": "v1",
            "unit": "INSTANCE_HOUR",
            "price": "1.00",
        },
    ).json()
    for description in ("v2", "v3"):
        response = http.patch(
            f"/api/v1/pricing/oci/{created['id']}",
            headers=headers(tokens),
            json={"description": description},
        )
        assert response.status_code == 200

    first = http.get(
        f"/api/v1/pricing/oci/{created['id']}/audit?page=1&page_size=2",
        headers=headers(tokens),
    ).json()
    second = http.get(
        f"/api/v1/pricing/oci/{created['id']}/audit?page=2&page_size=2",
        headers=headers(tokens),
    ).json()
    assert first["total"] == 3
    assert first["total_pages"] == 2
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    occurred = [event["occurred_at"] for event in first["items"]]
    assert occurred == sorted(occurred, reverse=True)


def test_audit_failure_can_be_rolled_back_with_pricing_change(auth_env, monkeypatch):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        actor = db.get(User, ids["admin"])
        current = db.scalar(
            select(PricingCatalogItem).where(
                PricingCatalogItem.provider == "oci",
                PricingCatalogItem.sku == "VM.Standard.E3.Flex.OCPU",
                PricingCatalogItem.enabled.is_(True),
            )
        )
        assert actor is not None
        assert current is not None
        original_until = current.effective_until
        service = AuditedPricingCatalogAdminService(db, provider="oci")

        def fail_audit(**_kwargs):
            raise RuntimeError("audit write failed")

        monkeypatch.setattr(service, "_record", fail_audit)
        with pytest.raises(RuntimeError, match="audit write failed"):
            service.update_item_audited(
                current.id,
                actor=actor,
                reason="Falha forçada de auditoria",
                price=Decimal("0.09900000"),
                effective_from=utcnow() + timedelta(days=1),
            )
        db.rollback()

    with Session(engine) as db:
        current = db.scalar(
            select(PricingCatalogItem).where(
                PricingCatalogItem.provider == "oci",
                PricingCatalogItem.sku == "VM.Standard.E3.Flex.OCPU",
                PricingCatalogItem.price == Decimal("0.05210000"),
            )
        )
        assert current is not None
        assert current.effective_until == original_until
        replacement_count = db.scalar(
            select(func.count())
            .select_from(PricingCatalogItem)
            .where(
                PricingCatalogItem.sku == "VM.Standard.E3.Flex.OCPU",
                PricingCatalogItem.price == Decimal("0.09900000"),
            )
        )
        assert replacement_count == 0


def test_failed_pricing_change_does_not_leave_orphan_audit_event(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        actor = db.get(User, ids["admin"])
        current = db.scalar(
            select(PricingCatalogItem).where(
                PricingCatalogItem.sku == "VM.Standard.E5.Flex.OCPU",
                PricingCatalogItem.enabled.is_(True),
            )
        )
        assert actor is not None
        assert current is not None
        service = AuditedPricingCatalogAdminService(db, provider="oci")
        with pytest.raises(PricingAdminValidationError):
            service.update_item_audited(
                current.id,
                actor=actor,
                reason="Vigência inválida",
                price=Decimal("0.099"),
                effective_from=current.effective_from,
            )
        db.rollback()
        audit_count = db.scalar(
            select(func.count())
            .select_from(PricingAuditEvent)
            .where(PricingAuditEvent.sku == "VM.Standard.E5.Flex.OCPU")
        )
        assert audit_count == 0
