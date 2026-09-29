import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import AwsAccount, CloudAccount
from app.schemas.account import CloudAccountBase
from app.services.cloud_accounts import UnsupportedProviderOperation, require_aws_configuration
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def test_structural_oci_identity_accepts_long_ocid_without_aws_fields():
    native_id = "ocid1.tenancy.oc1.." + "AbCdEf0123456789" * 6
    payload = CloudAccountBase(
        provider="OCI",
        native_account_id=native_id,
        name="OCI structural fixture",
    )
    assert payload.provider == "oci"
    assert payload.native_account_id == native_id

    with pytest.raises(ValidationError):
        CloudAccountBase(
            provider="aws",
            native_account_id=native_id,
            name="Invalid AWS fixture",
        )


def test_non_aws_account_cannot_enter_aws_operational_flow():
    account = CloudAccount(
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..fixture",
        name="OCI",
    )
    with pytest.raises(UnsupportedProviderOperation):
        require_aws_configuration(account)


def test_common_api_and_legacy_aws_contract_share_one_registration(auth_env):
    client, engine, tokens, _ = auth_env
    response = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json={
            "provider": "aws",
            "native_account_id": "222222222222",
            "name": "Second AWS",
            "enabled": True,
            "configuration": {
                "role_arn": "arn:aws:iam::222222222222:role/DeepOps",
                "external_id": "x" * 20,
                "regions": ["sa-east-1"],
                "schedule_enabled": False,
                "scan_interval_hours": 24,
            },
        },
    )
    assert response.status_code == 201, response.text
    common = response.json()
    assert common["provider"] == "aws"
    assert common["native_account_id"] == "222222222222"
    legacy_id = common["aws_configuration"]["id"]

    legacy = client.get(
        f"/api/v1/accounts/{legacy_id}",
        headers=headers(tokens),
    ).json()
    assert legacy["aws_account_id"] == common["native_account_id"]
    assert legacy["name"] == common["name"]

    response = client.patch(
        f"/api/v1/cloud-accounts/{common['id']}",
        headers=headers(tokens),
        json={"name": "Renamed common"},
    )
    assert response.status_code == 200
    legacy = client.get(f"/api/v1/accounts/{legacy_id}", headers=headers(tokens)).json()
    assert legacy["name"] == "Renamed common"

    response = client.patch(
        f"/api/v1/accounts/{legacy_id}",
        headers=headers(tokens),
        json={"name": "Renamed legacy"},
    )
    assert response.status_code == 200
    common = client.get(
        f"/api/v1/cloud-accounts/{common['id']}",
        headers=headers(tokens),
    ).json()
    assert common["name"] == "Renamed legacy"

    with Session(engine) as db:
        cloud = db.get(CloudAccount, common["id"])
        aws = db.get(AwsAccount, legacy_id)
        assert aws.cloud_account_id == cloud.id
        assert aws.name == cloud.name


def test_common_identity_is_immutable_and_uniqueness_is_database_backed(auth_env):
    client, _, tokens, _ = auth_env
    current = client.get("/api/v1/cloud-accounts", headers=headers(tokens)).json()[0]

    response = client.patch(
        f"/api/v1/cloud-accounts/{current['id']}",
        headers=headers(tokens),
        json={"provider": "oci"},
    )
    assert response.status_code == 422

    response = client.patch(
        f"/api/v1/cloud-accounts/{current['id']}",
        headers=headers(tokens),
        json={"native_account_id": "999999999999"},
    )
    assert response.status_code == 422

    duplicate = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json={
            "provider": "aws",
            "native_account_id": current["native_account_id"],
            "name": "Duplicate",
            "configuration": {
                "role_arn": f"arn:aws:iam::{current['native_account_id']}:role/DeepOps",
                "external_id": "d" * 20,
                "regions": ["sa-east-1"],
            },
        },
    )
    assert duplicate.status_code == 409


def test_recognized_oci_provider_is_not_registered_without_integration(auth_env):
    client, engine, tokens, _ = auth_env
    native_id = "ocid1.tenancy.oc1..structuralfixture"
    response = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json={
            "provider": "oci",
            "native_account_id": native_id,
            "name": "OCI not enabled yet",
        },
    )
    assert response.status_code == 409
    with Session(engine) as db:
        assert (
            db.scalar(
                select(CloudAccount).where(
                    CloudAccount.provider == "oci",
                    CloudAccount.native_account_id == native_id,
                )
            )
            is None
        )


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_common_account_mutations_remain_admin_only(auth_env, role):
    client, _, tokens, _ = auth_env
    assert client.get("/api/v1/cloud-accounts", headers=headers(tokens, role)).status_code == 200
    assert (
        client.post(
            "/api/v1/cloud-accounts",
            headers=headers(tokens, role),
            json={
                "provider": "aws",
                "native_account_id": "333333333333",
                "name": "Forbidden",
                "configuration": {
                    "role_arn": "arn:aws:iam::333333333333:role/DeepOps",
                    "external_id": "f" * 20,
                    "regions": ["sa-east-1"],
                },
            },
        ).status_code
        == 403
    )
