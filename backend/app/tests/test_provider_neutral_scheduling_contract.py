from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.account import AwsAccount, CloudAccount, OciAccountConfiguration
from app.schemas.account import (
    CloudAccountCreate,
    CloudAccountUpdate,
    OciAccountConfigurationUpdate,
)
from app.services.cloud_accounts import (
    UnsupportedProviderOperation,
    _provider_neutral_schedule_changes,
)
from app.tests.test_cloud_accounts import (
    TENANCY_OCID,
    _api_key,
    _oci_payload,
    oci_encryption_key as oci_encryption_key,
)
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _aws_payload(native_id: str = "222222222222") -> dict:
    return {
        "provider": "aws",
        "native_account_id": native_id,
        "name": "Provider-neutral AWS",
        "enabled": True,
        "configuration": {
            "role_arn": f"arn:aws:iam::{native_id}:role/DeepOps",
            "external_id": "provider-neutral-schedule",
            "regions": ["sa-east-1"],
            "is_management_account": False,
        },
    }


def test_provider_neutral_schema_accepts_schedule_but_not_next_scan_at():
    create = CloudAccountCreate(**_aws_payload(), schedule_enabled=True, scan_interval_hours=168)
    assert create.schedule_enabled is True
    assert create.scan_interval_hours == 168

    update = CloudAccountUpdate(schedule_enabled=True, scan_interval_hours=24)
    assert update.model_dump(exclude_unset=True) == {
        "schedule_enabled": True,
        "scan_interval_hours": 24,
    }

    with pytest.raises(ValidationError):
        CloudAccountUpdate(schedule_enabled=True, next_scan_at=datetime.now(UTC))

    with pytest.raises(ValidationError):
        OciAccountConfigurationUpdate(schedule_enabled=True)


def test_aws_common_schedule_updates_cloud_account_and_compatibility_mirror(auth_env):
    client, engine, tokens, _ = auth_env
    response = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json=_aws_payload(),
    )
    assert response.status_code == 201, response.text
    account = response.json()
    account_id = account["id"]
    aws_id = account["aws_configuration"]["id"]

    with Session(engine) as db:
        cloud = db.get(CloudAccount, account_id)
        cloud.connection_status = "connected"
        cloud.last_connection_test_at = datetime.now(UTC)
        db.commit()

    enabled = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"schedule_enabled": True, "scan_interval_hours": 24},
    )
    assert enabled.status_code == 200, enabled.text
    enabled_body = enabled.json()
    assert enabled_body["schedule_enabled"] is True
    assert enabled_body["scan_interval_hours"] == 24
    assert enabled_body["next_scan_at"] is not None
    assert enabled_body["connection_status"] == "connected"

    interval = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"scan_interval_hours": 168},
    )
    assert interval.status_code == 200, interval.text
    assert interval.json()["scan_interval_hours"] == 168
    assert interval.json()["next_scan_at"] is not None

    with Session(engine) as db:
        cloud = db.get(CloudAccount, account_id)
        mirror = db.get(AwsAccount, aws_id)
        assert cloud.schedule_enabled is True
        assert mirror.schedule_enabled is True
        assert mirror.scan_interval_hours == cloud.scan_interval_hours == 168
        assert mirror.next_scan_at == cloud.next_scan_at

    disabled = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"schedule_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["schedule_enabled"] is False
    assert disabled.json()["next_scan_at"] is None


def test_legacy_aws_configuration_schedule_is_only_a_compatibility_adapter(auth_env):
    client, engine, tokens, _ = auth_env
    response = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json={
            **_aws_payload("333333333333"),
            "configuration": {
                **_aws_payload("333333333333")["configuration"],
                "schedule_enabled": True,
                "scan_interval_hours": 12,
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["schedule_enabled"] is True
    assert body["scan_interval_hours"] == 12
    assert body["next_scan_at"] is not None

    patched = client.patch(
        f"/api/v1/cloud-accounts/{body['id']}",
        headers=headers(tokens),
        json={"configuration": {"scan_interval_hours": 168}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["scan_interval_hours"] == 168

    with Session(engine) as db:
        cloud = db.get(CloudAccount, body["id"])
        mirror = db.get(AwsAccount, body["aws_configuration"]["id"])
        assert mirror.scan_interval_hours == cloud.scan_interval_hours == 168


def test_oci_schedule_only_update_does_not_touch_provider_configuration_or_connection(auth_env, oci_encryption_key):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    response = client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json=_oci_payload(pem, fingerprint),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    account_id = body["id"]

    with Session(engine) as db:
        cloud = db.get(CloudAccount, account_id)
        configuration = db.get(OciAccountConfiguration, body["oci_configuration"]["id"])
        cloud.connection_status = "connected"
        cloud.last_connection_test_at = datetime.now(UTC)
        before = {
            "user_ocid": configuration.user_ocid,
            "fingerprint": configuration.fingerprint,
            "region": configuration.region,
            "scope_regions": list(configuration.scope_regions),
            "compartment_ocids": list(configuration.compartment_ocids),
            "include_root_compartment": configuration.include_root_compartment,
            "include_subcompartments": configuration.include_subcompartments,
            "credential_revision": configuration.credential_revision,
            "configuration_revision": configuration.configuration_revision,
            "private_key_ciphertext": configuration.private_key_ciphertext,
            "private_key_password_ciphertext": configuration.private_key_password_ciphertext,
        }
        db.commit()

    enabled = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"schedule_enabled": True, "scan_interval_hours": 24},
    )
    assert enabled.status_code == 200, enabled.text
    enabled_body = enabled.json()
    assert enabled_body["schedule_enabled"] is True
    assert enabled_body["scan_interval_hours"] == 24
    assert enabled_body["next_scan_at"] is not None
    assert enabled_body["connection_status"] == "connected"
    assert "private_key_pem" not in enabled_body
    assert "private_key_password" not in enabled_body
    assert "private_key_ciphertext" not in enabled_body["oci_configuration"]
    assert "private_key_password_ciphertext" not in enabled_body["oci_configuration"]

    changed = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"scan_interval_hours": 168},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["scan_interval_hours"] == 168

    with Session(engine) as db:
        configuration = db.get(OciAccountConfiguration, body["oci_configuration"]["id"])
        after = {
            "user_ocid": configuration.user_ocid,
            "fingerprint": configuration.fingerprint,
            "region": configuration.region,
            "scope_regions": list(configuration.scope_regions),
            "compartment_ocids": list(configuration.compartment_ocids),
            "include_root_compartment": configuration.include_root_compartment,
            "include_subcompartments": configuration.include_subcompartments,
            "credential_revision": configuration.credential_revision,
            "configuration_revision": configuration.configuration_revision,
            "private_key_ciphertext": configuration.private_key_ciphertext,
            "private_key_password_ciphertext": configuration.private_key_password_ciphertext,
        }
        assert after == before

    disabled = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"schedule_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["next_scan_at"] is None
    assert disabled.json()["connection_status"] == "connected"


def test_provider_without_scheduling_capability_is_rejected():
    account = CloudAccount(
        provider="azure",
        native_account_id="00000000-0000-0000-0000-000000000000",
        name="Unsupported schedule",
    )
    with pytest.raises(UnsupportedProviderOperation, match="does not support scheduling"):
        _provider_neutral_schedule_changes(
            account,
            {"schedule_enabled": True},
            None,
        )
