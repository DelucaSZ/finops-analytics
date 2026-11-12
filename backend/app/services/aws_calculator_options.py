"""Bounded read-only options for the future Aven AWS calculator dropdowns.

Every returned class/OS/deployment has a matching current On-Demand product in
the selected region. Searches are deliberately paginated at the HTTP boundary.
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from time import time

from app.services.aws_calculator_pricing import (
    AwsPriceUnavailable,
    AwsPublicPriceResolver,
    _client,
    _price_dimension,
)

_ENGINES = {"postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB"}


@lru_cache(maxsize=2)
def _regions_hour(bucket: int) -> tuple[str, ...]:
    client = _client()
    values = set()
    token = None
    for _ in range(4):
        payload = {"ServiceCode": "AmazonEC2", "AttributeName": "regionCode", "MaxResults": 100}
        if token:
            payload["NextToken"] = token
        try:
            response = client.get_attribute_values(**payload)
        except Exception as exc:
            raise AwsPriceUnavailable("aws_pricing_regions_unavailable") from exc
        values.update(
            item["Value"] for item in response.get("AttributeValues", ())
            if item.get("Value")
        )
        token = response.get("NextToken")
        if not token:
            return tuple(sorted(values))
    raise AwsPriceUnavailable("aws_pricing_regions_page_limit")


def available_regions() -> list[str]:
    return list(_regions_hour(int(time() // 3600)))


def aws_options(
    *,
    region: str,
    service: str,
    search: str,
    engine: str | None,
    offset: int,
    limit: int,
    resolver: AwsPublicPriceResolver | None = None,
) -> dict:
    pricing = resolver or AwsPublicPriceResolver()
    filters = {
        "regionCode": region,
        "contains:instanceType": search,
        "productFamily": "Compute Instance" if service == "ec2" else "Database Instance",
    }
    if service == "ec2":
        filters.update({"tenancy": "Shared", "preInstalledSw": "NA", "capacitystatus": "Used"})
        code = "AmazonEC2"
    else:
        name = _ENGINES.get((engine or "").lower())
        if not name:
            return {"items": [], "total": 0, "limit": limit, "offset": offset,
                    "status": "unsupported_engine", "supported_engines": list(_ENGINES)}
        filters["databaseEngine"] = name
        code = "AmazonRDS"
    rows = pricing.products(code, filters)
    choices: set[tuple[str, str]] = set()
    now = datetime.now(UTC)
    for row in rows:
        product = row.get("product", {})
        attrs = product.get("attributes", {})
        if (
            product.get("productFamily") != filters["productFamily"]
            or attrs.get("regionCode") != region
            or not attrs.get("instanceType")
            or search.lower() not in attrs["instanceType"].lower()
            or not _price_dimension(row, unit="Hrs", at=now)
        ):
            continue
        if service == "ec2":
            if (
                attrs.get("tenancy") != "Shared"
                or attrs.get("preInstalledSw") != "NA"
                or attrs.get("capacitystatus") != "Used"
                or attrs.get("operatingSystem") not in ("Linux", "Windows")
            ):
                continue
            choices.add((attrs["instanceType"], attrs["operatingSystem"].lower()))
        else:
            if (
                attrs.get("databaseEngine") != filters["databaseEngine"]
                or attrs.get("deploymentOption") not in ("Single-AZ", "Multi-AZ")
                or attrs.get("licenseModel", "No license required").lower()
                not in ("no license required", "license included")
                or attrs.get("deploymentModel") in ("Custom", "Multi-AZ DB cluster")
            ):
                continue
            choices.add(
                (attrs["instanceType"],
                 "single_az" if attrs["deploymentOption"] == "Single-AZ" else "multi_az")
            )
    ordered = sorted(choices)
    return {
        "service": service, "region": region, "source": "AWS_PUBLIC_PRICE_LIST",
        "items": [
            {"instance_type": instance, "operating_system": variant}
            if service == "ec2"
            else {"instance_class": instance, "deployment": variant}
            for instance, variant in ordered[offset:offset + limit]
        ],
        "total": len(ordered), "limit": limit, "offset": offset, "status": "ok",
        "supported_engines": list(_ENGINES) if service == "rds" else [],
    }
