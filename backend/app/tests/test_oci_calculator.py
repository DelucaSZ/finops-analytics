"""Task 27.4: deterministic OCI catalog, licensing and temporal regression coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.oci_db_calculator import OciDbCalculatorBinding
from app.models.pricing import PricingCatalogItem
from app.schemas.calculator import CalculatorEstimateRequest
from app.services.oci_calculator import estimate_oci_calculator, oci_calculator_options
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers

AT = datetime(2026, 11, 11, tzinfo=UTC)
RATES = {
    ("compute", "VM.Standard.E3.Flex.OCPU", "OCPU_HOUR"): "0.0521",
    ("compute", "VM.Standard.E3.Flex.Memory", "GB_RAM_HOUR"): "0.0031",
    ("compute", "VM.Standard.E4.Flex.OCPU", "OCPU_HOUR"): "0.0689",
    ("compute", "VM.Standard.E4.Flex.Memory", "GB_RAM_HOUR"): "0.0041",
    ("compute", "VM.Standard.E5.Flex.OCPU", "OCPU_HOUR"): "0.08266",
    ("compute", "VM.Standard.E5.Flex.Memory", "GB_RAM_HOUR"): "0.005511",
    ("compute", "WINDOWS_LICENSE_OCPU", "OCPU_HOUR"): "0.46092",
    ("block_volume", "BLOCK_VOLUME_GB_MONTH", "GB_MONTH"): "0.0531",
    ("block_volume", "BLOCK_VOLUME_VPU_GB_MONTH", "VPU_GB_MONTH"): "0.0036",
}


def row(service, sku, unit, amount, *, currency="BRL", effective_from=None):
    return PricingCatalogItem(
        provider="oci", service=service, sku=sku, unit=unit,
        description="Test-only catalog value", price=Decimal(amount),
        currency=currency, effective_from=effective_from or AT - timedelta(days=1),
        enabled=True, source="TEST_ONLY",
    )


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            row(service, sku, unit, amount)
            for (service, sku, unit), amount in RATES.items()
        )
        session.commit()
        yield session
    engine.dispose()


def request(service="compute", *, configuration=None, period=None, quantity=1, **extra):
    cfg = {
        "service": "compute", "shape": "VM.Standard.E4.Flex",
        "ocpus": 4, "memory_gb": 32, "operating_system": "linux",
        "boot_volume": {"size_gb": 100, "vpus_per_gb": 10},
    } if service == "compute" else {
        "service": "db_system", "deployment_model": "base_database",
        "shape": "VM.BaseDB.x86", "edition": "enterprise",
        "license_model": "license_included", "cpu_unit": "ECPU",
        "cpu_count": 4, "storage_gb": 500,
    }
    cfg.update(configuration or {})
    data = {
        "provider": "oci", "region": "sa-saopaulo-1",
        "resource_configuration": cfg, "period": period or {"mode": "monthly"},
        "quantity": quantity, "pricing_reference_date": AT,
    }
    data.update(extra)
    return CalculatorEstimateRequest.model_validate(data)


def quote(db, **kwargs):
    return estimate_oci_calculator(request(**kwargs), db)


def binding(*, component, sku, unit, license_model="license_included",
            includes_license=False, region="sa-saopaulo-1"):
    return OciDbCalculatorBinding(
        region=region, deployment_model="base_database", shape="VM.BaseDB.x86",
        edition="enterprise", license_model=license_model, cpu_unit="ECPU",
        component=component, sku=sku, unit=unit,
        includes_license=includes_license, source_reference="TEST_ONLY_VERIFIED_MAPPING",
        enabled=True,
    )


@pytest.mark.parametrize("shape", [
    "VM.Standard.E3.Flex", "VM.Standard.E4.Flex", "VM.Standard.E5.Flex",
])
def test_compute_allowlisted_shapes_have_catalog_provenance(db, shape):
    value = quote(db, configuration={"shape": shape})
    assert value.pricing_status == "priced"
    assert value.monthly_final_cost is not None
    assert value.final_currency == value.pricing_currency == "BRL"
    assert value.monthly_original_cost == value.monthly_net_cost == value.monthly_final_cost
    assert all(p.pricing_item_id and p.source == "TEST_ONLY" for p in value.pricing_components)
    assert value.discount_percent is None and value.tax_percent is None


def test_vm_monthly_744_and_three_week_cost_with_two_resources_and_volumes(db):
    value = quote(
        db, quantity=2, period={"mode": "weeks", "amount": "3"},
        configuration={
            "block_volumes": [{"size_gb": 500, "vpus_per_gb": 10}],
        },
    )
    assert value.pricing_status == "priced"
    assert value.monthly_final_cost == Decimal("712.24")
    assert value.period_final_cost == Decimal("482.48")
    assert value.period_duration_hours == 504
    assert [p.sku for p in value.pricing_components] == [
        "VM.Standard.E4.Flex.OCPU", "VM.Standard.E4.Flex.Memory",
        "BLOCK_VOLUME_GB_MONTH", "BLOCK_VOLUME_VPU_GB_MONTH",
        "BLOCK_VOLUME_GB_MONTH", "BLOCK_VOLUME_VPU_GB_MONTH",
    ]
    assert value.pricing_components[0].monthly_units == 4 * 744 * 2
    assert value.pricing_components[-1].monthly_units == 500 * 10 * 2


def test_windows_has_distinct_catalog_license_and_linux_does_not(db):
    linux = quote(db)
    windows = quote(db, configuration={"operating_system": "windows"})
    license_line = next(p for p in windows.pricing_components if p.sku == "WINDOWS_LICENSE_OCPU")
    assert license_line.unit == "OCPU_HOUR"
    assert license_line.monthly_original_cost == Decimal("1371.70")
    assert windows.monthly_final_cost == linux.monthly_final_cost + Decimal("1371.70")
    assert not any(p.sku == "WINDOWS_LICENSE_OCPU" for p in linux.pricing_components)


def test_unknown_os_or_boot_performance_never_presents_final_cost(db):
    unknown = quote(db, configuration={"operating_system": "unknown"})
    assert unknown.pricing_status == "partially_priced"
    assert unknown.monthly_final_cost is None
    assert unknown.monthly_known_subtotal is not None
    assert "operating_system_license_classification" in unknown.missing_pricing_components
    no_vpu = quote(db, configuration={"boot_volume": {"size_gb": 100}})
    assert no_vpu.pricing_status == "partially_priced"
    assert no_vpu.period_final_cost is None
    assert "boot_volume_vpu_configuration" in no_vpu.missing_pricing_components
    no_boot = quote(db, configuration={"boot_volume": None})
    assert no_boot.monthly_final_cost is None
    assert "boot_volume_configuration" in no_boot.missing_pricing_components


def test_zero_vpu_is_valid_and_does_not_require_performance_sku(db):
    performance = db.query(PricingCatalogItem).filter_by(sku="BLOCK_VOLUME_VPU_GB_MONTH").one()
    db.delete(performance)
    db.commit()
    value = quote(db, configuration={"boot_volume": {"size_gb": 100, "vpus_per_gb": 0}})
    assert value.pricing_status == "priced"
    assert all(p.sku != "BLOCK_VOLUME_VPU_GB_MONTH" for p in value.pricing_components)
    assert value.pricing_components[-1].monthly_original_cost == Decimal("5.31")


def test_missing_windows_or_storage_catalog_sku_is_partial(db):
    windows_price = db.query(PricingCatalogItem).filter_by(sku="WINDOWS_LICENSE_OCPU").one()
    db.delete(windows_price)
    db.commit()
    result = quote(db, configuration={"operating_system": "windows"})
    assert result.pricing_status == "partially_priced"
    assert result.monthly_final_cost is None
    assert "windows_license" in result.missing_pricing_components


@pytest.mark.parametrize(("configuration", "status"), [
    ({"shape": "VM.Standard.E6.Flex"}, "unsupported_configuration"),
    ({"ocpus": 65}, "invalid_combination"),
    ({"ocpus": 1, "memory_gb": 65}, "invalid_combination"),
    ({"memory_gb": 1}, "invalid_combination"),
    ({"boot_volume": {"size_gb": 100, "vpus_per_gb": 11}}, "invalid_combination"),
    ({"boot_volume": {"size_gb": 100, "vpus_per_gb": 10, "count": 2}}, "invalid_combination"),
    ({"shape": None}, "missing_configuration"),
])
def test_invalid_shapes_sizes_performance_and_boot_count_never_price(db, configuration, status):
    result = quote(db, configuration=configuration)
    assert result.pricing_status == status
    assert result.monthly_final_cost is None


@pytest.mark.parametrize(("period", "hours"), [
    ({"mode": "hours", "amount": "1"}, Decimal("1")),
    ({"mode": "days", "amount": "1"}, Decimal("24")),
    ({"mode": "weeks", "amount": "1"}, Decimal("168")),
    ({"mode": "weeks", "amount": "3"}, Decimal("504")),
    ({"mode": "days", "amount": "15"}, Decimal("360")),
    ({"mode": "hours", "amount": "1.25"}, Decimal("1.25")),
    ({"mode": "custom", "start_at": "2026-11-01T01:30:00-04:00",
     "end_at": "2026-11-01T01:30:00-05:00"}, Decimal("1")),
])
def test_oci_temporal_contract_is_centralized(db, period, hours):
    result = quote(db, period=period)
    assert result.pricing_status == "priced"
    assert result.period_duration_hours == hours
    assert result.period_final_cost is not None


def test_request_financial_separation_and_storage_validation():
    with pytest.raises(ValidationError):
        request(aws_financial={"discount_percent": 10})
    with pytest.raises(ValidationError):
        request(configuration={"boot_volume": {"size_gb": -5, "vpus_per_gb": 0}})
    with pytest.raises(ValidationError):
        request(configuration={"boot_volume": {"size_gb": 100, "vpus_per_gb": 0},
                               "boot_volume_gb": 100})
    with pytest.raises(ValidationError):
        request(configuration={"block_volumes": [{"size_gb": 1} for _ in range(21)]})


def test_db_missing_bindings_has_no_fictitious_skus_or_final_price(db):
    result = quote(db, service="db_system")
    assert result.pricing_status == "sku_missing"
    assert result.monthly_final_cost is None
    assert result.monthly_known_subtotal is None
    assert set(result.missing_pricing_components) == {
        "db_system_capacity_sku_mapping",
        "db_system_license_sku_mapping",
        "db_system_storage_sku_mapping",
    }
    assert result.pricing_components == []


def test_db_missing_license_yields_known_subtotal_not_final_total(db):
    db.add_all([
        row("db_system", "TEST_ONLY_DB_CAPACITY", "ECPU_HOUR", "0.2"),
        row("db_system", "TEST_ONLY_DB_STORAGE", "GB_MONTH", "0.05"),
        binding(component="capacity", sku="TEST_ONLY_DB_CAPACITY", unit="ECPU_HOUR"),
        binding(component="storage", sku="TEST_ONLY_DB_STORAGE", unit="GB_MONTH"),
    ])
    db.commit()
    result = quote(db, service="db_system")
    assert result.pricing_status == "partially_priced"
    assert result.monthly_known_subtotal == Decimal("620.20")
    assert result.monthly_final_cost is None
    assert result.missing_pricing_components == ["db_system_license_sku_mapping"]


def test_db_full_components_and_fifteen_day_proration(db):
    db.add_all([
        row("db_system", "TEST_ONLY_DB_CAPACITY", "ECPU_HOUR", "0.2"),
        row("db_system", "TEST_ONLY_DB_LICENSE", "ECPU_HOUR", "0.1"),
        row("db_system", "TEST_ONLY_DB_STORAGE", "GB_MONTH", "0.05"),
        binding(component="capacity", sku="TEST_ONLY_DB_CAPACITY", unit="ECPU_HOUR"),
        binding(component="license", sku="TEST_ONLY_DB_LICENSE", unit="ECPU_HOUR"),
        binding(component="storage", sku="TEST_ONLY_DB_STORAGE", unit="GB_MONTH"),
    ])
    db.commit()
    result = quote(db, service="db_system", period={"mode": "days", "amount": 15})
    assert result.pricing_status == "priced"
    assert result.monthly_final_cost == Decimal("917.80")
    assert result.period_final_cost == Decimal("444.10")
    assert {p.sku for p in result.pricing_components} == {
        "TEST_ONLY_DB_CAPACITY", "TEST_ONLY_DB_LICENSE", "TEST_ONLY_DB_STORAGE",
    }
    metadata = oci_calculator_options(db, service="db_system", region="sa-saopaulo-1")
    assert metadata["items"][0]["complete_price_available"] is True


def test_db_license_included_in_capacity_does_not_double_bill(db):
    db.add_all([
        row("db_system", "TEST_ONLY_DB_BUNDLED", "ECPU_HOUR", "0.3"),
        row("db_system", "TEST_ONLY_DB_STORAGE", "GB_MONTH", "0.05"),
        binding(component="capacity", sku="TEST_ONLY_DB_BUNDLED",
                unit="ECPU_HOUR", includes_license=True),
        binding(component="storage", sku="TEST_ONLY_DB_STORAGE", unit="GB_MONTH"),
    ])
    db.commit()
    result = quote(db, service="db_system")
    assert result.pricing_status == "priced"
    assert result.monthly_final_cost == Decimal("917.80")
    assert not any(p.service == "compute" for p in result.pricing_components)
    assert len(result.pricing_components) == 2


def test_db_byol_requires_distinct_verified_binding_not_free_license(db):
    db.add_all([
        row("db_system", "TEST_ONLY_DB_BYOL", "ECPU_HOUR", "0.05"),
        row("db_system", "TEST_ONLY_DB_STORAGE", "GB_MONTH", "0.05"),
        binding(component="capacity", sku="TEST_ONLY_DB_BYOL",
                unit="ECPU_HOUR", license_model="byol"),
        binding(component="storage", sku="TEST_ONLY_DB_STORAGE",
                unit="GB_MONTH", license_model="byol"),
    ])
    db.commit()
    result = quote(db, service="db_system", configuration={"license_model": "byol"})
    assert result.pricing_status == "priced"
    assert result.monthly_final_cost == Decimal("173.80")
    assert "byol_requires_owned_eligible_oracle_licenses" in result.warnings
    assert all(p.sku != "TEST_ONLY_DB_LICENSE" for p in result.pricing_components)


@pytest.mark.parametrize(("configuration", "status"), [
    ({"cpu_unit": "OCPU"}, "unsupported_configuration"),
    ({"shape": "VM.Standard.E4.Flex"}, "unsupported_configuration"),
    ({"cpu_count": 3}, "invalid_combination"),
    ({"cpu_count": 6}, "invalid_combination"),
    ({"edition": None}, "missing_configuration"),
])
def test_db_rejects_legacy_ocpu_invalid_ecpu_and_missing_product(db, configuration, status):
    result = quote(db, service="db_system", configuration=configuration)
    assert result.pricing_status == status
    assert result.monthly_final_cost is None


def test_db_region_and_catalog_effectiveness_must_match(db):
    db.add_all([
        row("db_system", "TEST_ONLY_FUTURE", "ECPU_HOUR", "0.2",
            effective_from=AT + timedelta(days=1)),
        binding(component="capacity", sku="TEST_ONLY_FUTURE", unit="ECPU_HOUR"),
    ])
    db.commit()
    value = quote(db, service="db_system")
    assert value.pricing_status == "sku_missing" or value.pricing_status == "partially_priced"
    assert value.monthly_final_cost is None
    assert value.pricing_components[0].pricing_status == "price_not_effective"


def test_oci_authenticated_http_and_dropdown_contract(auth_env):
    client, engine, tokens, _ = auth_env
    payload = request().model_dump(mode="json")
    assert client.post("/api/v1/calculator/estimate", json=payload).status_code == 401
    with Session(engine) as db:
        db.add_all(row(service, sku, unit, amount)
                   for (service, sku, unit), amount in RATES.items())
        db.commit()
    response = client.post("/api/v1/calculator/estimate",
                           json=payload, headers=headers(tokens))
    assert response.status_code == 200, response.text
    assert response.json()["pricing_status"] == "priced"
    assert response.json()["final_currency"] == "BRL"
    options = client.get(
        "/api/v1/calculator/oci/options?service=compute&region=sa-saopaulo-1",
        headers=headers(tokens),
    )
    assert options.status_code == 200
    assert len(options.json()["items"]) == 3
    assert all(item["pricing_status"] == "priced" for item in options.json()["items"])
    assert client.get(
        "/api/v1/calculator/oci/options?service=db_system&region=sa-saopaulo-1",
        headers=headers(tokens),
    ).json()["setup_required"] is True
