"""Task 27.3: deterministic AWS public-price adapter, metering and safety tests.

No AWS network, credentials or provisioned resources are involved in these tests.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.schemas.calculator import CalculatorEstimateRequest
from app.services.aws_calculator import estimate_aws_calculator
from app.services.aws_calculator_pricing import AwsPublicPriceResolver

AT = datetime(2026, 11, 12, 10, tzinfo=UTC)


def row(sku, family, attrs, rate, aws_unit):
    return {
        "product": {
            "sku": sku,
            "productFamily": family,
            "attributes": {"regionCode": "sa-east-1", "locationType": "AWS Region", **attrs},
        },
        "terms": {
            "OnDemand": {
                "TERM": {
                    "effectiveDate": "2026-10-01T00:00:00Z",
                    "priceDimensions": {
                        "RATE": {
                            "unit": aws_unit,
                            "beginRange": "0",
                            "endRange": "Inf",
                            "description": sku,
                            "pricePerUnit": {"USD": rate},
                        }
                    },
                }
            }
        },
    }


def fixture_rows():
    return [
        row(
            "LINUX",
            "Compute Instance",
            {
                "instanceType": "t3.medium",
                "operatingSystem": "Linux",
                "tenancy": "Shared",
                "preInstalledSw": "NA",
                "capacitystatus": "Used",
                "operation": "RunInstances",
            },
            "1",
            "Hrs",
        ),
        row(
            "WINDOWS",
            "Compute Instance",
            {
                "instanceType": "t3.medium",
                "operatingSystem": "Windows",
                "tenancy": "Shared",
                "preInstalledSw": "NA",
                "capacitystatus": "Used",
                "operation": "RunInstances:0002",
            },
            "1.5",
            "Hrs",
        ),
        row(
            "EBS_GP3",
            "Storage",
            {
                "volumeApiName": "gp3",
                "usagetype": "SAE1-EBS:VolumeUsage.gp3",
            },
            "0.10",
            "GB-Mo",
        ),
        row(
            "EBS_IOPS",
            "System Operation",
            {
                "volumeApiName": "gp3",
                "usagetype": "SAE1-EBS:VolumeP-IOPS.gp3",
            },
            "0.005",
            "IOPS-Mo",
        ),
        row(
            "EBS_MBPS",
            "Provisioned Throughput",
            {
                "volumeApiName": "gp3",
                "usagetype": "SAE1-EBS:VolumeP-Throughput.gp3",
            },
            "0.04",
            "MBps-Mo",
        ),
        row(
            "RDS_POSTGRES",
            "Database Instance",
            {
                "instanceType": "db.t3.medium",
                "databaseEngine": "PostgreSQL",
                "deploymentOption": "Single-AZ",
                "licenseModel": "No license required",
            },
            "2",
            "Hrs",
        ),
        row(
            "RDS_POSTGRES_MULTI",
            "Database Instance",
            {
                "instanceType": "db.t3.medium",
                "databaseEngine": "PostgreSQL",
                "deploymentOption": "Multi-AZ",
                "licenseModel": "No license required",
            },
            "4",
            "Hrs",
        ),
        row(
            "RDS_GP3",
            "Database Storage",
            {
                "usagetype": "SAE1-RDS:GP3-Storage",
                "deploymentOption": "Single-AZ",
            },
            "0.20",
            "GB-Mo",
        ),
        row(
            "RDS_MULTI_GP3",
            "Database Storage",
            {
                "usagetype": "SAE1-RDS:Multi-AZ-GP3-Storage",
                "deploymentOption": "Multi-AZ",
            },
            "0.35",
            "GB-Mo",
        ),
    ]


def resolver(rows=None):
    values = fixture_rows() if rows is None else rows
    return AwsPublicPriceResolver(
        fetcher=lambda service, filters, bucket: tuple(
            r
            for r in values
            if (
                (
                    service == "AmazonEC2"
                    and r["product"]["productFamily"]
                    in {"Compute Instance", "Storage", "System Operation", "Provisioned Throughput"}
                )
                or (
                    service == "AmazonRDS"
                    and r["product"]["productFamily"] in {"Database Instance", "Database Storage"}
                )
            )
        )
    )


def request(service="ec2", configuration=None, **updates):
    initial = (
        {
            "service": "ec2",
            "instance_type": "t3.medium",
            "operating_system": "linux",
            "root_volume_gb": "100",
        }
        if service == "ec2"
        else {
            "service": "rds",
            "instance_class": "db.t3.medium",
            "engine": "postgres",
            "deployment": "single_az",
            "storage_type": "gp3",
            "allocated_storage_gb": "100",
        }
    )
    data = {
        "provider": "aws",
        "region": "sa-east-1",
        "resource_configuration": configuration or initial,
        "quantity": 1,
        "period": {"mode": "monthly"},
        "pricing_reference_date": AT,
    }
    data.update(updates)
    return CalculatorEstimateRequest.model_validate(data)


def test_ec2_region_aware_compute_ebs_discount_and_brl_conversion():
    output = estimate_aws_calculator(
        request(
            quantity=2,
            period={"mode": "weeks", "amount": "3"},
            aws_financial={
                "discount_percent": "10",
                "conversion_enabled": True,
                "usd_brl_rate": "5",
                "tax_percent": "13",
            },
        ),
        resolver=resolver(),
    )
    assert output.pricing_status == "priced"
    assert output.monthly_original_cost == Decimal("1480.00")
    assert output.monthly_discount_amount == Decimal("146.00")
    assert output.monthly_final_cost == Decimal("7537.10")
    assert output.period_original_cost == Decimal("1022.00")
    assert output.period_discount_amount == Decimal("100.80")
    assert output.period_final_cost == Decimal("5204.78")
    assert output.final_currency == "BRL"
    assert output.pricing_source == "AWS_PUBLIC_PRICE_LIST"
    assert len(output.pricing_components) == 2
    assert output.pricing_components[1].discount_eligible is False
    assert output.pricing_components[0].effective_from == datetime(2026, 10, 1, tzinfo=UTC)


def test_ec2_windows_included_license_and_custom_gp3_performance():
    cfg = {
        "service": "ec2",
        "instance_type": "t3.medium",
        "operating_system": "windows",
        "root_volume_gb": "100",
        "ebs_iops": 4000,
        "ebs_throughput_mbps": 200,
    }
    result = estimate_aws_calculator(request(configuration=cfg), resolver=resolver())
    assert result.pricing_status == "priced"
    assert len(result.pricing_components) == 4
    assert result.monthly_original_cost == Decimal("1113.00")
    # 730*1.5 = 1095; 100*.10 = 10; 1000*.005 = 5; 75*.04 = 3
    assert "license" not in [c.service for c in result.pricing_components]


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_never_falls_back_to_another_region(region):
    result = estimate_aws_calculator(request(region=region), resolver=resolver())
    assert result.pricing_status == "sku_missing"
    assert result.monthly_final_cost is None
    assert result.period_final_cost is None
    assert "compute" in result.missing_pricing_components


def test_rds_postgres_storage_and_15_day_proration():
    result = estimate_aws_calculator(
        request(
            "rds", period={"mode": "days", "amount": "15"}, aws_financial={"discount_percent": "5"}
        ),
        resolver=resolver(),
    )
    assert result.pricing_status == "priced"
    assert result.monthly_original_cost == Decimal("1480.00")
    assert result.period_original_cost == Decimal("730.00")
    assert result.period_discount_amount == Decimal("36.00")
    assert result.period_final_cost == Decimal("694.00")


def test_rds_multi_az_uses_distinct_instance_and_storage_skus():
    cfg = {
        "service": "rds",
        "engine": "postgres",
        "instance_class": "db.t3.medium",
        "deployment": "multi_az",
        "storage_type": "gp3",
        "allocated_storage_gb": 100,
    }
    result = estimate_aws_calculator(request("rds", configuration=cfg), resolver=resolver())
    assert result.pricing_status == "priced"
    assert result.monthly_original_cost == Decimal("2955.00")
    assert result.pricing_components[0].sku.startswith("RDS_POSTGRES_MULTI:")
    assert result.pricing_components[1].sku.startswith("RDS_MULTI_GP3:")


@pytest.mark.parametrize(
    "service,cfg",
    [
        ("ec2", {"service": "ec2"}),
        ("rds", {"service": "rds"}),
        (
            "rds",
            {
                "service": "rds",
                "instance_class": "db.t3.medium",
                "engine": "oracle",
                "deployment": "single_az",
            },
        ),
        (
            "rds",
            {
                "service": "rds",
                "instance_class": "db.t3.medium",
                "engine": "postgres",
                "deployment": "single_az",
                "storage_type": "gp3",
                "allocated_storage_gb": 100,
                "provisioned_iops": 13000,
            },
        ),
    ],
)
def test_missing_and_unsupported_configs_never_quote_definitive_cost(service, cfg):
    result = estimate_aws_calculator(request(service, configuration=cfg), resolver=resolver())
    assert result.pricing_status != "priced"
    assert result.period_final_cost is None
    assert result.monthly_final_cost is None


def test_aws_short_duration_billing_minima_per_component():
    short = {"mode": "hours", "amount": "0.001"}
    ec2 = estimate_aws_calculator(request(period=short), resolver=resolver())
    rds = estimate_aws_calculator(request("rds", period=short), resolver=resolver())
    assert ec2.pricing_status == "priced"
    assert ec2.pricing_components[0].period_units == Decimal(1) / Decimal(60)
    assert ec2.pricing_components[1].period_units == (
        Decimal(100) * Decimal(60) / Decimal(720 * 3600)
    )
    assert rds.pricing_components[0].period_units == Decimal(1) / Decimal(6)
    assert rds.pricing_components[1].period_units == (
        Decimal(100) * Decimal(600) / Decimal(720 * 3600)
    )


def test_ambiguous_rates_and_missing_storage_do_not_yield_total():
    dup = [*fixture_rows(), fixture_rows()[0]]
    ambiguous = estimate_aws_calculator(request(), resolver=resolver(dup))
    assert ambiguous.pricing_status == "partially_priced"
    assert ambiguous.monthly_final_cost is None
    missing_storage = [r for r in fixture_rows() if r["product"]["sku"] != "EBS_GP3"]
    incomplete = estimate_aws_calculator(request(), resolver=resolver(missing_storage))
    assert incomplete.pricing_status == "partially_priced"
    assert incomplete.monthly_known_subtotal is not None
    assert incomplete.monthly_final_cost is None


def test_live_pricing_service_failure_returns_null_not_zero():
    def broken(*args):
        from app.services.aws_calculator_pricing import AwsPriceUnavailable

        raise AwsPriceUnavailable("aws_pricing_api_unavailable")

    out = estimate_aws_calculator(request(), resolver=AwsPublicPriceResolver(fetcher=broken))
    assert out.pricing_status == "pricing_configuration_error"
    assert out.monthly_final_cost is None
    assert "aws_pricing_api_unavailable" in out.warnings
