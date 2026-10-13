from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.services.oci_pricing import OciPricingService
from app.services.opportunity_evidence import normalize_persisted_evidence
from app.services.pricing_catalog import PricingResolver
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def test_compute_flex_retains_both_catalog_versions(auth_env):
    _, engine, _, _ = auth_env
    with Session(engine) as db:
        result = OciPricingService(PricingResolver(db)).price_compute_resource(
            shape="VM.Standard.E4.Flex",
            ocpus=Decimal("4"),
            memory_gb=Decimal("64"),
        )

    assert result.currency == "BRL"
    assert result.base_monthly_cost == Decimal("400.27")
    assert len(result.pricing_components) == 2
    by_sku = {component.sku: component for component in result.pricing_components}
    ocpu = by_sku["VM.Standard.E4.Flex.OCPU"]
    memory = by_sku["VM.Standard.E4.Flex.Memory"]
    assert ocpu.pricing_item_id
    assert memory.pricing_item_id
    assert ocpu.pricing_item_id != memory.pricing_item_id
    assert ocpu.unit_price == Decimal("0.06890000")
    assert memory.unit_price == Decimal("0.00410000")
    assert ocpu.currency == memory.currency == "BRL"
    assert ocpu.quantity == Decimal("2976")
    assert memory.quantity == Decimal("47616")
    assert ocpu.as_evidence()["unit_price"] == "0.06890000"


def test_windows_compute_adds_third_pricing_component(auth_env):
    _, engine, _, _ = auth_env
    with Session(engine) as db:
        result = OciPricingService(PricingResolver(db)).compute_monthly_pricing(
            family="E3",
            ocpus=Decimal("2"),
            memory_gb=Decimal("16"),
            include_windows_license=True,
        )

    assert len(result.pricing_components) == 3
    assert {component.sku for component in result.pricing_components} == {
        "VM.Standard.E3.Flex.OCPU",
        "VM.Standard.E3.Flex.Memory",
        "WINDOWS_LICENSE_OCPU",
    }
    assert all(component.currency == "BRL" for component in result.pricing_components)


def test_block_volume_retains_capacity_and_vpu_versions(auth_env):
    _, engine, _, _ = auth_env
    with Session(engine) as db:
        result = OciPricingService(PricingResolver(db)).block_volume_monthly_pricing(
            size_gb=Decimal("500"),
            vpus_per_gb=Decimal("10"),
        )

    assert result.monthly_cost == Decimal("44.55")
    assert result.currency == "BRL"
    assert len(result.pricing_components) == 2
    by_sku = {component.sku: component for component in result.pricing_components}
    assert by_sku["BLOCK_VOLUME_GB_MONTH"].unit_price == Decimal("0.05310000")
    assert by_sku["BLOCK_VOLUME_GB_MONTH"].quantity == Decimal("500")
    assert by_sku["BLOCK_VOLUME_VPU_GB_MONTH"].unit_price == Decimal("0.00360000")
    assert by_sku["BLOCK_VOLUME_VPU_GB_MONTH"].quantity == Decimal("5000")


def test_catalog_change_keeps_old_calculation_reference_and_new_calculation_uses_new_version(auth_env):
    http, engine, tokens, _ = auth_env
    current = http.get(
        "/api/v1/pricing/oci?q=VM.Standard.E4.Flex.OCPU&status=all",
        headers=headers(tokens),
    ).json()["items"][0]
    transition = utcnow() + timedelta(days=1)

    changed = http.patch(
        f"/api/v1/pricing/oci/{current['id']}",
        headers=headers(tokens),
        json={
            "price": "0.07000000",
            "effective_from": transition.isoformat(),
            "reason": "Teste de provenance",
        },
    )
    assert changed.status_code == 200, changed.text
    replacement = changed.json()

    with Session(engine) as db:
        service = OciPricingService(PricingResolver(db))
        old = service.compute_monthly_pricing(
            family="E4",
            ocpus=Decimal("1"),
            memory_gb=Decimal("1"),
            at=transition - timedelta(seconds=1),
        )
        new = service.compute_monthly_pricing(
            family="E4",
            ocpus=Decimal("1"),
            memory_gb=Decimal("1"),
            at=transition + timedelta(seconds=1),
        )

    old_ocpu = next(c for c in old.pricing_components if c.sku.endswith("OCPU"))
    new_ocpu = next(c for c in new.pricing_components if c.sku.endswith("OCPU"))
    assert old_ocpu.pricing_item_id == current["id"]
    assert old_ocpu.unit_price == Decimal("0.06890000")
    assert new_ocpu.pricing_item_id == replacement["id"]
    assert new_ocpu.unit_price == Decimal("0.07000000")
    # The old result is an immutable monetary snapshot; it is not re-resolved dynamically.
    assert old_ocpu.pricing_item_id == current["id"]
    assert old_ocpu.unit_price == Decimal("0.06890000")


def test_pricing_provenance_survives_observation_evidence_normalization():
    component = {
        "pricing_item_id": "price-version-1",
        "service": "block_volume",
        "sku": "BLOCK_VOLUME_GB_MONTH",
        "unit": "GB_MONTH",
        "unit_price": "0.05310000",
        "currency": "BRL",
        "source": "IMPORTED_OCI_CALCULATOR",
        "effective_from": "2026-10-01T00:00:00+00:00",
        "effective_until": None,
        "quantity": "100",
    }
    normalized = normalize_persisted_evidence(
        rule_key="oci_block_volume_unattached",
        service="OCI Block Storage",
        region="sa-saopaulo-1",
        resource_id="volume-1",
        resource_name="volume",
        title="Volume OCI",
        description="Volume OCI sem attachment",
        evidence={
            "pricing": {
                "status": "priced",
                "currency": "BRL",
                "monthly_cost": "5.31",
                "pricing_components": [component],
            }
        },
        current_monthly_cost=Decimal("5.31"),
        estimated_monthly_savings=Decimal("5.31"),
        provider="oci",
    )
    assert normalized["details"]["pricing"]["pricing_components"] == [component]


def test_old_observation_evidence_without_provenance_remains_valid():
    normalized = normalize_persisted_evidence(
        rule_key="oci_block_volume_unattached",
        service="OCI Block Storage",
        region="sa-saopaulo-1",
        resource_id="legacy-volume",
        resource_name=None,
        title="Legacy OCI volume",
        description="Historical observation",
        evidence={"analysis": {"attachment_count": 0}},
        current_monthly_cost=Decimal("5.31"),
        estimated_monthly_savings=Decimal("5.31"),
        provider="oci",
    )
    assert "pricing" not in normalized["details"]
