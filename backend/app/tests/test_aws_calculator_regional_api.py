"""Task 28.6: authenticated AWS calculator routes require no AWS Pricing API access."""

from unittest.mock import patch

import pytest

from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers

BASE = "/api/v1/calculator"


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_aws_catalog_endpoints_allow_authenticated_non_admins(auth_env, role):
    client, _, tokens, _ = auth_env
    with patch(
        "app.services.aws_calculator_pricing._client",
        side_effect=AssertionError("calculator must not call AWS Pricing API"),
    ):
        regions = client.get(BASE + "/aws/regions", headers=headers(tokens, role))
        options = client.get(
            BASE + "/aws/options",
            params={
                "service": "ec2",
                "region": "sa-east-1",
                "search": "t3",
                "offset": 0,
                "limit": 10,
            },
            headers=headers(tokens, role),
        )
        response = client.post(
            BASE + "/estimate",
            headers=headers(tokens, role),
            json={
                "provider": "aws",
                "region": "sa-east-1",
                "resource_configuration": {
                    "service": "ec2",
                    "instance_type": "t3.medium",
                    "operating_system": "linux",
                },
            },
        )
    assert regions.status_code == 200, regions.text
    assert regions.json()["source"] == "AWS_REGIONAL_CATALOG"
    assert options.status_code == 200, options.text
    assert options.json()["total"] == 0
    assert response.status_code == 200, response.text
    assert response.json()["pricing_status"] == "sync_required"
    assert response.json()["monthly_final_cost"] is None


def test_aws_catalog_endpoints_are_not_public(auth_env):
    client, _, _, _ = auth_env
    assert client.get(BASE + "/aws/regions").status_code == 401
    assert (
        client.get(
            BASE + "/aws/options",
            params={"service": "ec2", "region": "sa-east-1", "search": "t3"},
        ).status_code
        == 401
    )
    assert client.post(
        BASE + "/estimate",
        json={
            "provider": "aws",
            "region": "sa-east-1",
            "resource_configuration": {"service": "ec2"},
        },
    ).status_code == 401


def test_aws_option_pagination_is_bounded(auth_env):
    client, _, tokens, _ = auth_env
    for bad in (0, 101):
        response = client.get(
            BASE + "/aws/options",
            params={
                "service": "ec2",
                "region": "sa-east-1",
                "search": "t3",
                "limit": bad,
            },
            headers=headers(tokens),
        )
        assert response.status_code == 422
