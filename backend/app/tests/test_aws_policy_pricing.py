"""Task 28.7: deterministic AWS policy/catalog financial integration tests.

The fixtures are synthetic, and never represent audited official AWS tariff values.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.services.aws_policy_pricing import AwsPolicyPricingAdapter
from app.services.opportunity_evidence import build_collected_finding_evidence
from app.services.collector_types import CollectedFinding
from app.tests.test_aws_calculator_regional import (
    AT,
    compute,
    ebs,
    publish,
    rds,
)


@pytest.fixture(params=["sqlite", "postgresql"])
def db(request):
    if request.param == "postgresql":
        uri = os.getenv("TEST_POSTGRES_URL")
        if not uri:
            pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL integration")
        root = create_engine(uri)
        schema = "test_policy_28_" + uuid.uuid4().hex
        with root.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        root.dispose()
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
            root = create_engine(uri)
            with root.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            root.dispose()


def finding(key, region="sa-east-1", **details):
    return CollectedFinding(
        rule_key=key,
        service="EC2",
        region=region,
        resource_id="resource-123",
        title="Synthetic financial test",
        description="A resource eligible for financial assessment.",
        evidence={"details": details, "metrics": [], "notes": []},
        current_monthly_cost=None,
        estimated_monthly_savings=None,
    )


def enrich(db, item, *, config=None, at=AT):
    values = [item]
    with patch(
        "app.services.aws_calculator_pricing._client",
        side_effect=AssertionError("Live AWS Pricing API must not be called"),
    ):
        AwsPolicyPricingAdapter(db, reference_at=at).enrich_findings(
            values,
            [{"rule_key": item.rule_key, "config": config or {}}],
        )
    return values[0] if values else None


def test_ebs_gp3_rate_is_identical_to_calculator_and_regional(db):
    ebs(db, amount="0.10")
    ebs(
        db,
        family="System Operation",
        usage="VolumeP-IOPS.gp3",
        sku="IOPS-3000",
        amount="0.005",
        unit="IOPS_MONTH",
        aws_unit="IOPS-Mo",
    )
    ebs(
        db,
        family="Provisioned Throughput",
        usage="VolumeP-Throughput.gp3",
        sku="THROUGHPUT",
        amount="0.04",
        unit="MBPS_MONTH",
        aws_unit="MBps-Mo",
    )
    db.commit()
    item = enrich(
        db, finding("ebs_unattached", size_gib=100, volume_type="gp3", iops=4000, throughput=150)
    )
    assert item is not None
    assert item.estimated_monthly_savings == Decimal("16.00")
    assert item.evidence["pricing"]["status"] == "priced"
    components = item.evidence["pricing"]["components"]
    assert [x["unit_price_usd"] for x in components] == ["0.10000000", "0.00500000", "0.04000000"]
    assert all(x["product_sku"] and x["rate_code"] and x["catalog_item_id"] for x in components)
    assert components[0]["unit"] == "GB_MONTH"
    assert components[0]["source"] == "AWS_PUBLIC_PRICE_LIST"


def test_ebs_gp3_missing_required_component_keeps_operational_finding(db):
    ebs(db, amount="0.10")
    db.commit()
    item = enrich(
        db,
        finding("ebs_unattached", size_gib=100, volume_type="gp3", iops=4000, throughput=125),
        config={"minimum_monthly_savings_usd": 1000},
    )
    assert item is not None
    assert item.evidence["pricing"]["status"] == "partially_priced"
    assert item.evidence["pricing"]["known_subtotal_usd"] == "10.00"
    assert item.estimated_monthly_savings is None
    assert item.severity == "low"
    assert item.evidence["pricing"]["missing_components"]


def test_unsynced_region_never_defaults_to_zero_or_another_region(db):
    ebs(db)
    db.commit()
    item = enrich(
        db,
        finding(
            "ebs_unattached",
            "us-east-1",
            size_gib=100,
            volume_type="gp3",
            iops=3000,
            throughput=125,
        ),
    )
    assert item is not None
    assert item.evidence["pricing"]["status"] == "sync_required"
    assert item.current_monthly_cost is None
    assert item.estimated_monthly_savings is None


def test_stopped_ec2_counts_ebs_only_and_preserves_no_prices(db):
    ebs(db)
    db.commit()
    item = enrich(
        db,
        finding(
            "ec2_stopped_with_ebs",
            volumes=[
                {"volume_id": "v1", "type": "gp3", "size_gib": 40, "iops": 3000, "throughput": 125}
            ],
        ),
    )
    assert item is not None
    assert item.current_monthly_cost == Decimal("4.00")
    assert item.estimated_monthly_savings == Decimal("4.00")
    assert len(item.evidence["pricing"]["components"]) == 1
    assert item.evidence["pricing"]["components"][0]["name"] == "ebs_storage"


def test_ec2_linux_nonprod_uses_monthly_schedule_not_fixed_365_hours(db):
    compute(db, amount="1")
    db.commit()
    item = enrich(
        db,
        finding(
            "ec2_nonprod_outside_hours",
            instance_type="t3.medium",
            platform_details="Linux/UNIX",
            tenancy="default",
        ),
        config={
            "business_days": [1, 2, 3, 4, 5],
            "business_hours_start": "08:00",
            "business_hours_end": "19:00",
        },
    )
    assert item is not None
    assert item.current_monthly_cost == Decimal("730.00")
    assert item.estimated_monthly_savings != Decimal("365.00")
    assert item.evidence["pricing"]["components"][0]["product_sku"] == "EC2-Linux"


def test_rds_is_engine_and_deployment_specific_compute_only(db):
    rds(db, deployment="Multi-AZ", amount="2")
    db.commit()
    item = enrich(
        db,
        finding(
            "rds_nonprod_idle",
            engine="postgres",
            instance_class="db.t3.medium",
            multi_az=True,
            license_model="postgresql-license",
        ),
    )
    assert item is not None
    assert item.evidence["pricing"]["status"] == "partially_priced"
    assert item.estimated_monthly_savings == Decimal("1460.00")
    assert item.current_monthly_cost is None
    assert (
        "rds_storage_and_additional_costs_excluded"
        in item.evidence["pricing"]["missing_components"]
    )


def test_snapshot_price_is_upper_bound_not_recognized_saving(db):
    publish(
        db,
        sku="SNAP-STANDARD",
        amount="0.06",
        attrs={
            "usagetype": "SAE1-EBS:SnapshotUsage",
            "snapshotType": "standard",
            "productFamily": "Snapshot Storage",
        },
        family="Snapshot Storage",
        service="snapshot",
        unit="GB_MONTH",
        aws_unit="GB-Mo",
    )
    db.commit()
    item = enrich(
        db,
        finding(
            "snapshot_retention",
            storage_tier="standard",
            volume_size_gib=200,
        ),
    )
    assert item is not None
    assert item.current_monthly_cost == Decimal("12.00")
    assert item.estimated_monthly_savings is None
    assert "Incremental" in " ".join(item.evidence["pricing"]["notes"])


def test_eip_uses_hourly_public_price_without_monthly_hardcoding(db):
    publish(
        db,
        sku="IP-IDLE",
        amount="0.005",
        attrs={"usagetype": "SAE1-PublicIPv4:IdleAddress", "productFamily": "Public IPv4"},
        family="Public IPv4",
        service="ipv4",
        service_code="AmazonVPC",
        unit="IP_HOUR",
        aws_unit="Hrs",
    )
    db.commit()
    item = enrich(db, finding("eip_unassociated"))
    assert item is not None
    assert item.estimated_monthly_savings == Decimal("3.65")
    assert item.evidence["pricing"]["components"][0]["unit"] == "IP_HOUR"


def test_load_balancer_base_does_not_claim_full_cost_or_savings(db):
    publish(
        db,
        sku="ALB-HOURS",
        amount="0.03",
        attrs={"usagetype": "SAE1-LoadBalancerUsage", "productFamily": "Load Balancing"},
        family="Load Balancing",
        service="alb",
        service_code="AWSELB",
        unit="LB_HOUR",
        aws_unit="Hrs",
    )
    db.commit()
    item = enrich(
        db,
        finding(
            "load_balancer_no_traffic",
            load_balancer_type="application",
            datapoint_count=7,
        ),
    )
    assert item is not None
    assert item.evidence["pricing"]["status"] == "partially_priced"
    assert item.evidence["pricing"]["known_subtotal_usd"] == "21.90"
    assert item.estimated_monthly_savings is None


def test_legitimate_zero_price_is_distinct_from_missing(db):
    ebs(db, amount="0")
    db.commit()
    item = enrich(
        db,
        finding("ebs_unattached", size_gib=10, volume_type="gp3", iops=3000, throughput=125),
        config={"minimum_monthly_savings_usd": 0},
    )
    assert item is not None
    assert item.evidence["pricing"]["status"] == "priced"
    assert item.current_monthly_cost == Decimal("0.00")
    assert item.estimated_monthly_savings == Decimal("0.00")



def test_flat_collector_evidence_is_priced_and_preserved_in_opportunity(db):
    ebs(db, amount="0.09")
    db.commit()
    item = CollectedFinding(
        rule_key="ebs_unattached", service="EC2/EBS", region="sa-east-1",
        resource_id="vol-123", title="Unattached volume",
        description="Operationally eligible volume.",
        evidence={
            "size_gib": 20, "volume_type": "gp3",
            "iops": 3000, "throughput": 125, "age_days": 15,
        },
    )
    item = enrich(db, item)
    assert item is not None
    assert item.estimated_monthly_savings == Decimal("1.80")
    normalized = build_collected_finding_evidence(
        item,
        {"rule_key": "ebs_unattached", "config": {"minimum_age_days": 7}},
        evaluated_at=AT,
    )
    assert normalized["pricing"]["region"] == "sa-east-1"
    assert normalized["pricing"]["status"] == "priced"
    assert normalized["pricing"]["components"][0]["unit_price_usd"] == "0.09000000"
    assert normalized["pricing"]["components"][0]["rate_code"]
    assert normalized["pricing"]["components"][0]["product_sku"]
    assert normalized["pricing"]["components"][0]["catalog_item_id"]
