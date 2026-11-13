"""Task 28.6: persisted AWS catalog -> calculator financial integration.

Fixtures are synthetic; they are not claims about current official AWS rates.
No AWS network, customer credentials, or production catalog data is used.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.schemas.calculator import CalculatorEstimateRequest
from app.services.aws_calculator import estimate_aws_calculator
from app.services.aws_calculator_options import available_regions, aws_options
from app.services.aws_regional_pricing import (
    AwsRegionalPricingRepository,
    AwsRegionalPricingResolver,
)

AT = datetime(2026, 11, 12, 12, tzinfo=UTC)


@pytest.fixture(params=["sqlite", "postgresql"])
def db(request):
    if request.param == "postgresql":
        uri = os.getenv("TEST_POSTGRES_URL")
        if not uri:
            pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL integration")
        from sqlalchemy import text

        engine = create_engine(uri)
        schema = "test_calculator_28_" + uuid.uuid4().hex
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine.dispose()
        engine = create_engine(uri, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        if request.param == "postgresql":
            control = create_engine(uri)
            with control.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()


def batch(db, service_code="AmazonEC2", region="sa-east-1"):
    repo = AwsRegionalPricingRepository(db)
    item = repo.get_or_create_batch(
        service_code=service_code,
        region_code=region,
        source_version="fixture-2026-11",
        checksum=f"fixture-{service_code}-{region}",
        source_type="TEST_FIXTURE",
    )
    item.status = "published"
    repo.set_sync_state(service_code=service_code, region_code=region, status="synced", batch=item)
    return item


def publish(
    db,
    *,
    sku,
    amount,
    attrs,
    family,
    region="sa-east-1",
    service="ec2",
    service_code="AmazonEC2",
    unit="INSTANCE_HOUR",
    aws_unit="Hrs",
    effective_at=None,
):
    repo = AwsRegionalPricingRepository(db)
    product = repo.put_product(
        service=service,
        service_code=service_code,
        region_code=region,
        product_sku=sku,
        product_family=family,
        description=sku,
        financial_attributes=attrs,
        product_attributes=attrs,
    )
    return repo.put_rate(
        product=product,
        rate_code=f"{sku}.RATE",
        term_code="TEST-TERM",
        billing_unit=unit,
        aws_unit=aws_unit,
        amount=Decimal(amount),
        effective_from=effective_at or AT - timedelta(days=10),
        source="AWS_PUBLIC_PRICE_LIST",
        source_effective_at=AT - timedelta(days=15),
        import_batch=batch(db, service_code, region),
    )


def compute(db, *, region="sa-east-1", os_name="Linux", amount="1", sku=None, effective_at=None):
    attrs = {
        "instanceType": "t3.medium",
        "operatingSystem": os_name,
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
        "operation": "RunInstances" if os_name == "Linux" else "RunInstances:0002",
        "productFamily": "Compute Instance",
    }
    return publish(
        db,
        sku=sku or f"EC2-{os_name}",
        amount=amount,
        attrs=attrs,
        family="Compute Instance",
        region=region,
        effective_at=effective_at,
    )


def ebs(
    db,
    *,
    family="Storage",
    usage="VolumeUsage.gp3",
    sku="EBS-GP3",
    amount="0.1",
    unit="GB_MONTH",
    aws_unit="GB-Mo",
):
    attrs = {
        "volumeApiName": "gp3",
        "usagetype": "SAE1-EBS:" + usage,
        "productFamily": family,
    }
    return publish(
        db,
        sku=sku,
        amount=amount,
        attrs=attrs,
        family=family,
        service="ebs",
        unit=unit,
        aws_unit=aws_unit,
    )


def rds(db, *, engine="PostgreSQL", deployment="Single-AZ", amount="2", sku=None):
    attrs = {
        "instanceType": "db.t3.medium",
        "databaseEngine": engine,
        "deploymentOption": deployment,
        "licenseModel": "No license required",
        "productFamily": "Database Instance",
    }
    return publish(
        db,
        sku=sku or f"RDS-{engine}-{deployment}",
        amount=amount,
        attrs=attrs,
        family="Database Instance",
        service="rds",
        service_code="AmazonRDS",
    )


def rds_storage(db, *, deployment="Single-AZ", amount="0.2"):
    usage = ("Multi-AZ-" if deployment == "Multi-AZ" else "") + "GP3-Storage"
    attrs = {
        "usagetype": "SAE1-RDS:" + usage,
        "deploymentOption": deployment,
        "productFamily": "Database Storage",
    }
    return publish(
        db,
        sku="RDS-STORAGE-" + deployment,
        amount=amount,
        attrs=attrs,
        family="Database Storage",
        service="rds",
        service_code="AmazonRDS",
        unit="GB_MONTH",
        aws_unit="GB-Mo",
    )


def estimate(
    db,
    *,
    region="sa-east-1",
    os_name="linux",
    storage=True,
    terms=None,
    service="ec2",
    deployment="single_az",
    engine="postgres",
):
    cfg = (
        {
            "service": "ec2",
            "instance_type": "t3.medium",
            "operating_system": os_name,
            "root_volume_gb": "100" if storage else None,
        }
        if service == "ec2"
        else {
            "service": "rds",
            "instance_class": "db.t3.medium",
            "engine": engine,
            "deployment": deployment,
            "storage_type": "gp3",
            "allocated_storage_gb": "100",
        }
    )
    request = CalculatorEstimateRequest.model_validate(
        {
            "provider": "aws",
            "region": region,
            "resource_configuration": cfg,
            "pricing_reference_date": AT,
            "aws_financial": terms,
        }
    )
    return estimate_aws_calculator(request, db=db)


def test_locally_published_price_equals_regional_resolver_and_catalog(db):
    item = compute(db)
    ebs(db)
    db.commit()
    with patch(
        "app.services.aws_calculator_pricing._client",
        side_effect=AssertionError("no AWS Pricing API"),
    ):
        output = estimate(db)
        choices = aws_options(
            db,
            service="ec2",
            region="sa-east-1",
            search="t3",
            engine=None,
            offset=0,
            limit=10,
        )
    assert output.pricing_status == "priced"
    line = output.pricing_components[0]
    assert line.pricing_item_id == item.id
    assert line.product_sku == "EC2-Linux"
    assert line.rate_code == "EC2-Linux.RATE"
    assert line.region_code == "sa-east-1"
    assert line.unit_price == Decimal("1")
    assert line.source == "AWS_PUBLIC_PRICE_LIST"
    assert line.import_batch_id is not None
    assert output.monthly_original_cost == Decimal("740.00")
    assert choices["total"] == 1
    assert choices["items"][0]["pricing_status"] == "priced"
    resolved = AwsRegionalPricingResolver(db).resolve_aws_price(
        service="ec2",
        service_code="AmazonEC2",
        region_code="sa-east-1",
        configuration={
            "instanceType": "t3.medium",
            "operatingSystem": "Linux",
            "tenancy": "Shared",
            "preInstalledSw": "NA",
            "capacitystatus": "Used",
            "operation": "RunInstances",
            "productFamily": "Compute Instance",
        },
        billing_unit="INSTANCE_HOUR",
        reference_at=AT,
    )
    assert resolved.catalog_item_id == line.pricing_item_id
    assert resolved.unit_price == line.unit_price


def test_regional_isolation_and_unsynced_region(db):
    compute(db, region="sa-east-1", amount="1")
    compute(db, region="us-east-1", amount="2")
    db.commit()
    a = estimate(db, storage=False)
    b = estimate(db, region="us-east-1", storage=False)
    missing = estimate(db, region="eu-west-1", storage=False)
    assert a.pricing_components[0].unit_price == Decimal("1")
    assert b.pricing_components[0].unit_price == Decimal("2")
    assert a.pricing_components[0].sku == b.pricing_components[0].sku
    assert missing.pricing_status == "sync_required"
    assert missing.monthly_final_cost is None
    assert "aws_region_catalog_not_synchronized" in missing.warnings


def test_gp3_capacity_and_extra_performance_is_not_discounted(db):
    compute(db)
    ebs(db)
    ebs(
        db,
        family="System Operation",
        usage="VolumeP-IOPS.gp3",
        sku="EBS-IOPS",
        amount="0.005",
        unit="IOPS_MONTH",
        aws_unit="IOPS-Mo",
    )
    ebs(
        db,
        family="Provisioned Throughput",
        usage="VolumeP-Throughput.gp3",
        sku="EBS-MBPS",
        amount="0.04",
        unit="MBPS_MONTH",
        aws_unit="MBps-Mo",
    )
    db.commit()
    request = CalculatorEstimateRequest.model_validate(
        {
            "provider": "aws",
            "region": "sa-east-1",
            "pricing_reference_date": AT,
            "resource_configuration": {
                "service": "ec2",
                "instance_type": "t3.medium",
                "operating_system": "linux",
                "root_volume_gb": "100",
                "ebs_iops": 4000,
                "ebs_throughput_mbps": 200,
            },
            "aws_financial": {
                "discount_percent": "10",
                "conversion_enabled": True,
                "usd_brl_rate": "5",
                "tax_percent": "13",
            },
        }
    )
    result = estimate_aws_calculator(request, db=db)
    assert result.pricing_status == "priced"
    assert [c.unit_price for c in result.pricing_components] == [
        Decimal("1"),
        Decimal("0.1"),
        Decimal("0.005"),
        Decimal("0.04"),
    ]
    assert result.monthly_original_cost == Decimal("748.00")
    assert result.monthly_discount_amount == Decimal("73.00")
    assert result.monthly_net_cost == Decimal("675.00")
    assert result.monthly_final_cost == Decimal("3813.75")
    assert [c.discount_eligible for c in result.pricing_components] == [True, False, False, False]


@pytest.mark.parametrize("engine", ["PostgreSQL", "MySQL", "MariaDB"])
@pytest.mark.parametrize("deployment,expected", [("Single-AZ", "2"), ("Multi-AZ", "4")])
def test_rds_engines_deployments_and_storage(db, engine, deployment, expected):
    rds(db, engine=engine, deployment=deployment, amount=expected)
    rds_storage(db, deployment=deployment)
    db.commit()
    result = estimate(
        db,
        service="rds",
        engine=engine.lower().replace("postgresql", "postgres"),
        deployment="single_az" if deployment == "Single-AZ" else "multi_az",
    )
    assert result.pricing_status == "priced"
    assert result.pricing_components[0].unit_price == Decimal(expected)
    assert result.pricing_components[1].unit_price == Decimal("0.2")
    assert result.pricing_components[0].service == "rds"


def test_missing_storage_is_partial_and_no_final_total(db):
    compute(db)
    db.commit()
    result = estimate(db)
    assert result.pricing_status == "partially_priced"
    assert result.monthly_known_subtotal == Decimal("730.00")
    assert result.monthly_final_cost is None
    assert "ebs_storage" in result.missing_pricing_components


def test_not_effective_ambiguous_and_zero_are_not_conflated(db):
    compute(db, effective_at=AT + timedelta(days=1))
    db.commit()
    assert estimate(db, storage=False).pricing_status == "price_not_effective"
    db.rollback()
    # The same technical attributes with two products are financially ambiguous.
    compute(db, sku="ALT-EC2", effective_at=AT - timedelta(days=1))
    db.commit()
    assert estimate(db, storage=False).pricing_status == "pricing_configuration_error"


def test_valid_zero_price_remains_priced(db):
    compute(db, amount="0")
    ebs(db, amount="0")
    db.commit()
    result = estimate(db)
    assert result.pricing_status == "priced"
    assert result.monthly_final_cost == Decimal("0.00")
    assert result.pricing_components[0].unit_price == Decimal(0)


def test_service_specific_sync_status_does_not_mark_rds_as_synced_with_only_ec2(db):
    compute(db)
    db.commit()
    regions = available_regions(db)
    assert regions["service_status"]["ec2"]["sa-east-1"] == "synced"
    assert regions["service_status"]["rds"]["sa-east-1"] == "sync_required"


def test_regions_and_options_are_local_paginated_and_engine_specific(db):
    compute(db, os_name="Linux")
    compute(db, os_name="Windows")
    rds(db, engine="PostgreSQL")
    rds(db, engine="MySQL")
    db.commit()
    with patch(
        "app.services.aws_calculator_pricing._client",
        side_effect=AssertionError("no AWS calls"),
    ):
        regions = available_regions(db)
        a = aws_options(
            db,
            service="ec2",
            region="sa-east-1",
            search="t3",
            engine=None,
            limit=1,
            offset=0,
        )
        b = aws_options(
            db,
            service="ec2",
            region="sa-east-1",
            search="t3",
            engine=None,
            limit=1,
            offset=1,
        )
        pg = aws_options(
            db,
            service="rds",
            region="sa-east-1",
            search="t3",
            engine="postgres",
            limit=10,
            offset=0,
        )
    assert regions["source"] == "AWS_REGIONAL_CATALOG"
    assert "sa-east-1" in regions["items"]
    assert a["total"] == b["total"] == 2
    assert a["items"][0] != b["items"][0]
    assert pg["total"] == 1
    assert pg["items"][0]["instance_class"] == "db.t3.medium"
    assert pg["items"][0]["deployment"] == "single_az"


def test_ec2_missing_optional_importer_attributes_do_not_hide_valid_price(db):
    attrs = {
        "instanceType": "t3.medium",
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "operation": "RunInstances",
        "productFamily": "Compute Instance",
    }
    row = publish(
        db,
        sku="EC2-OPTIONAL-ATTRS",
        amount="1.1",
        attrs=attrs,
        family="Compute Instance",
    )
    db.commit()
    result = estimate(db, storage=False)
    assert result.pricing_status == "priced"
    assert result.pricing_components[0].pricing_item_id == row.id
    assert result.pricing_components[0].unit_price == Decimal("1.1")
    options = aws_options(
        db,
        service="ec2",
        region="sa-east-1",
        search="t3",
        engine=None,
        offset=0,
        limit=10,
    )
    assert options["total"] == 1
    assert options["items"][0]["pricing_status"] == "priced"
