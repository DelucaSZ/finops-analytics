import hashlib
import json

import oci
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import (
    AwsAccount,
    CloudAccount,
    CloudAccountAuditEvent,
    OciAccountConfiguration,
)
from app.models.collection_run import CollectionRun
from app.schemas.account import CloudAccountBase
from app.services.cloud_accounts import (
    UnsupportedProviderOperation,
    require_aws_configuration,
)
from app.services.oci_auth import (
    OciConnectionError,
    OciConnectionValidation,
    _remote_failure,
)
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


TENANCY_OCID = "ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
USER_OCID = "ocid1.user.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
COMPARTMENT_OCID = "ocid1.compartment.oc1..cccccccccccccccccccccccccccccccc"


@pytest.fixture
def oci_encryption_key(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(key.decode()))
    monkeypatch.setattr(settings, "oci_credentials_key_version", "test-v1")
    return key


def _api_key(passphrase: str | None = None, *, marker: bool = False) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase is not None
        else serialization.NoEncryption()
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        encryption,
    ).decode()
    if marker:
        pem += "OCI_API_KEY\n"
    der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.md5(der, usedforsecurity=False).hexdigest()
    fingerprint = ":".join(digest[index : index + 2] for index in range(0, 32, 2))
    return pem, fingerprint


def _oci_payload(
    private_key_pem: str,
    fingerprint: str,
    *,
    passphrase: str | None = None,
    tenancy_ocid: str = TENANCY_OCID,
    user_ocid: str = USER_OCID,
) -> dict:
    return {
        "provider": "oci",
        "native_account_id": tenancy_ocid,
        "name": "OCI Production",
        "enabled": True,
        "configuration": {
            "user_ocid": user_ocid,
            "fingerprint": fingerprint,
            "region": "sa-saopaulo-1",
            "scope_regions": ["sa-saopaulo-1"],
            "compartment_ocids": [COMPARTMENT_OCID],
            "include_root_compartment": False,
            "include_subcompartments": False,
            "private_key_pem": private_key_pem,
            "private_key_password": passphrase,
        },
    }


def _create_oci(client, tokens, payload):
    return client.post(
        "/api/v1/cloud-accounts",
        headers=headers(tokens),
        json=payload,
    )


def test_structural_oci_identity_accepts_long_tenancy_ocid_without_aws_fields():
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
    with pytest.raises(ValidationError):
        CloudAccountBase(
            provider="oci",
            native_account_id="ocid1.user.oc1..not-a-tenancy",
            name="Wrong OCI type",
        )


def test_non_aws_account_cannot_enter_aws_operational_flow():
    account = CloudAccount(
        provider="oci",
        native_account_id=TENANCY_OCID,
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
    assert common["oci_configuration"] is None
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


def test_oci_create_is_encrypted_sanitized_and_duplicate_safe(
    auth_env, oci_encryption_key
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key(marker=True)
    payload = _oci_payload(pem, fingerprint)

    response = _create_oci(client, tokens, payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "oci"
    assert body["native_account_id"] == TENANCY_OCID
    assert body["aws_configuration"] is None
    assert body["oci_configuration"]["credentials_configured"] is True
    response_text = response.text
    assert pem not in response_text
    assert "private_key_pem" not in response_text
    assert "private_key_ciphertext" not in response_text
    assert "private_key_password" not in response_text

    with Session(engine) as db:
        stored = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == body["id"]
            )
        )
        assert stored.private_key_ciphertext != pem
        decrypted = Fernet(oci_encryption_key).decrypt(
            stored.private_key_ciphertext.encode()
        ).decode()
        assert "BEGIN PRIVATE KEY" in decrypted
        assert "OCI_API_KEY" not in decrypted
        assert stored.credential_key_version == "test-v1"

    duplicate = _create_oci(client, tokens, payload)
    assert duplicate.status_code == 409
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CloudAccount)
                .where(
                    CloudAccount.provider == "oci",
                    CloudAccount.native_account_id == TENANCY_OCID,
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "payload_mutator",
    [
        lambda payload: {**payload, "native_account_id": "ocid1.user.oc1..wrongtype"},
        lambda payload: {
            **payload,
            "configuration": {
                **payload["configuration"],
                "user_ocid": "ocid1.tenancy.oc1..wrongtype",
            },
        },
    ],
)
def test_oci_rejects_wrong_ocid_types_without_echoing_secret(
    auth_env, oci_encryption_key, payload_mutator
):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    payload = payload_mutator(_oci_payload(pem, fingerprint))
    response = _create_oci(client, tokens, payload)
    assert response.status_code == 422
    assert pem not in response.text


def test_provider_specific_configuration_cannot_cross_providers(
    auth_env, oci_encryption_key
):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key()

    aws_with_oci = _oci_payload(pem, fingerprint)
    aws_with_oci["provider"] = "aws"
    aws_with_oci["native_account_id"] = "333333333333"
    assert _create_oci(client, tokens, aws_with_oci).status_code == 422

    oci_with_aws = {
        "provider": "oci",
        "native_account_id": TENANCY_OCID,
        "name": "Wrong config",
        "configuration": {
            "role_arn": "arn:aws:iam::333333333333:role/DeepOps",
            "external_id": "x" * 20,
            "regions": ["sa-east-1"],
        },
    }
    assert _create_oci(client, tokens, oci_with_aws).status_code == 422


def test_oci_invalid_pem_and_fingerprint_are_sanitized(auth_env, oci_encryption_key):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key()

    malformed_pem = "-----BEGIN PRIVATE KEY-----\\n" + ("A" * 96) + "\\n-----END PRIVATE KEY-----"
    malformed = _oci_payload(malformed_pem, fingerprint)
    response = _create_oci(client, tokens, malformed)
    assert response.status_code == 422
    assert "not-a-private-key" not in response.text
    assert response.json()["detail"]["code"] == "local_configuration_invalid"

    mismatch = _oci_payload(pem, "00:" * 15 + "00")
    response = _create_oci(client, tokens, mismatch)
    assert response.status_code == 422
    assert pem not in response.text
    assert "fingerprint" in response.json()["detail"]["message"].lower()


def test_oci_password_protected_key_accepts_correct_and_rejects_wrong_passphrase(
    auth_env, oci_encryption_key
):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key("correct-test-passphrase")

    response = _create_oci(
        client,
        tokens,
        _oci_payload(pem, fingerprint, passphrase="correct-test-passphrase"),
    )
    assert response.status_code == 201, response.text

    second_pem, second_fingerprint = _api_key("another-correct-passphrase")
    payload = _oci_payload(
        second_pem,
        second_fingerprint,
        passphrase="wrong-passphrase",
        tenancy_ocid="ocid1.tenancy.oc1..dddddddddddddddddddddddddddddddd",
        user_ocid="ocid1.user.oc1..eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    )
    response = _create_oci(client, tokens, payload)
    assert response.status_code == 422
    assert "wrong-passphrase" not in response.text
    assert second_pem not in response.text


@pytest.mark.parametrize("configured_key", ["", "not-a-fernet-key"])
def test_oci_missing_or_invalid_encryption_key_fails_closed_without_breaking_aws(
    auth_env, monkeypatch, configured_key
):
    client, engine, tokens, _ = auth_env
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(configured_key))
    pem, fingerprint = _api_key()

    response = _create_oci(client, tokens, _oci_payload(pem, fingerprint))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "local_configuration_invalid"
    assert pem not in response.text

    aws = client.get("/api/v1/cloud-accounts", headers=headers(tokens))
    assert aws.status_code == 200
    assert any(item["provider"] == "aws" for item in aws.json())
    with Session(engine) as db:
        assert db.scalar(
            select(func.count()).select_from(CloudAccount).where(CloudAccount.provider == "oci")
        ) == 0


def test_oci_update_without_key_preserves_ciphertext_and_invalidates_connection(
    auth_env, oci_encryption_key
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    created = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()
    account_id = created["id"]

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        ciphertext = configuration.private_key_ciphertext
        revision = configuration.configuration_revision
        account = db.get(CloudAccount, account_id)
        account.connection_status = "connected"
        account.last_connection_test_at = account.created_at
        db.commit()

    response = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"configuration": {"scope_regions": ["sa-saopaulo-1", "us-ashburn-1"]}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["connection_status"] == "untested"
    assert response.json()["last_connection_test_at"] is None

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        assert configuration.private_key_ciphertext == ciphertext
        assert configuration.configuration_revision == revision + 1

    password_only = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"configuration": {"private_key_password": "do-not-store-alone"}},
    )
    assert password_only.status_code == 422
    assert "do-not-store-alone" not in password_only.text

    removal = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"configuration": {"private_key_pem": None}},
    )
    assert removal.status_code == 422


def test_oci_explicit_credential_removal_is_unambiguous_and_audited(
    auth_env, oci_encryption_key
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    created = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()
    account_id = created["id"]

    response = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"configuration": {"remove_credentials": True}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["oci_configuration"]["credentials_configured"] is False
    assert response.json()["oci_configuration"]["credential_key_version"] is None
    assert response.json()["connection_status"] == "untested"

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        assert configuration.private_key_ciphertext is None
        assert configuration.private_key_password_ciphertext is None
        assert configuration.credential_key_version is None
        event = db.scalar(
            select(CloudAccountAuditEvent)
            .where(
                CloudAccountAuditEvent.account_id == account_id,
                CloudAccountAuditEvent.action == "oci.credentials.remove",
            )
            .order_by(CloudAccountAuditEvent.created_at.desc())
        )
        assert event is not None
        assert "credential removed" in event.detail

    test_response = client.post(
        f"/api/v1/cloud-accounts/{account_id}/test-connection",
        headers=headers(tokens),
    )
    assert test_response.status_code == 200
    assert test_response.json()["ok"] is False
    assert test_response.json()["error_code"] == "local_configuration_invalid"

    pem2, fingerprint2 = _api_key()
    ambiguous = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={
            "configuration": {
                "remove_credentials": True,
                "private_key_pem": pem2,
                "fingerprint": fingerprint2,
            }
        },
    )
    assert ambiguous.status_code == 422
    assert pem2 not in ambiguous.text


def test_oci_credential_replacement_is_validated_before_atomic_swap(
    auth_env, oci_encryption_key, monkeypatch
):
    client, engine, tokens, _ = auth_env
    initial_pem, initial_fingerprint = _api_key()
    created = _create_oci(
        client,
        tokens,
        _oci_payload(initial_pem, initial_fingerprint),
    ).json()
    account_id = created["id"]

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        original_ciphertext = configuration.private_key_ciphertext
        original_credential_revision = configuration.credential_revision

    replacement_pem, replacement_fingerprint = _api_key()
    monkeypatch.setattr(
        "app.services.cloud_accounts.validate_connection",
        lambda _: OciConnectionValidation(("tenancy", "user", "regions")),
    )
    response = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={
            "configuration": {
                "private_key_pem": replacement_pem,
                "fingerprint": replacement_fingerprint,
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["connection_status"] == "connected"
    assert replacement_pem not in response.text

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        validated_ciphertext = configuration.private_key_ciphertext
        assert validated_ciphertext != original_ciphertext
        assert configuration.credential_revision == original_credential_revision + 1
        assert configuration.fingerprint == replacement_fingerprint

    failed_pem, failed_fingerprint = _api_key()

    def reject(_):
        raise OciConnectionError(
            "authentication_failed",
            "OCI rejected the API signing credentials",
        )

    monkeypatch.setattr("app.services.cloud_accounts.validate_connection", reject)
    response = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={
            "configuration": {
                "private_key_pem": failed_pem,
                "fingerprint": failed_fingerprint,
            }
        },
    )
    assert response.status_code == 422
    assert failed_pem not in response.text

    with Session(engine) as db:
        configuration = db.scalar(
            select(OciAccountConfiguration).where(
                OciAccountConfiguration.cloud_account_id == account_id
            )
        )
        assert configuration.private_key_ciphertext == validated_ciphertext
        assert configuration.fingerprint == replacement_fingerprint


def test_oci_connection_test_success_failure_and_missing_local_key(
    auth_env, oci_encryption_key, monkeypatch
):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    account_id = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()["id"]

    monkeypatch.setattr(
        "app.api.routes.cloud_accounts.validate_connection",
        lambda _: OciConnectionValidation(("tenancy", "user", "regions")),
    )
    response = client.post(
        f"/api/v1/cloud-accounts/{account_id}/test-connection",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["verified_checks"] == ["tenancy", "user", "regions"]

    def denied(_):
        raise OciConnectionError(
            "authorization_failed",
            "OCI denied access or did not expose a required IAM resource",
        )

    monkeypatch.setattr("app.api.routes.cloud_accounts.validate_connection", denied)
    response = client.post(
        f"/api/v1/cloud-accounts/{account_id}/test-connection",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "authorization_failed"

    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(""))
    response = client.post(
        f"/api/v1/cloud-accounts/{account_id}/test-connection",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "local_configuration_invalid"


def test_oci_connection_result_cannot_validate_a_newer_configuration(
    auth_env, oci_encryption_key, monkeypatch
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    account_id = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()["id"]

    def concurrent_update(_snapshot):
        with Session(engine) as other:
            configuration = other.scalar(
                select(OciAccountConfiguration).where(
                    OciAccountConfiguration.cloud_account_id == account_id
                )
            )
            configuration.configuration_revision += 1
            account = other.get(CloudAccount, account_id)
            account.connection_status = "untested"
            other.commit()
        return OciConnectionValidation(("tenancy", "user", "regions"))

    monkeypatch.setattr(
        "app.api.routes.cloud_accounts.validate_connection",
        concurrent_update,
    )
    response = client.post(
        f"/api/v1/cloud-accounts/{account_id}/test-connection",
        headers=headers(tokens),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "stale_configuration"

    with Session(engine) as db:
        account = db.get(CloudAccount, account_id)
        assert account.connection_status == "untested"


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            oci.exceptions.ServiceError(
                401,
                "NotAuthenticated",
                {},
                "raw authentication detail",
            ),
            "authentication_failed",
        ),
        (
            oci.exceptions.ServiceError(
                403,
                "NotAuthorized",
                {},
                "raw authorization detail",
            ),
            "authorization_failed",
        ),
        (
            oci.exceptions.ServiceError(
                404,
                "NotFound",
                {},
                "raw hidden-resource detail",
            ),
            "authorization_failed",
        ),
        (
            oci.exceptions.ServiceError(
                429,
                "TooManyRequests",
                {},
                "raw throttle detail",
            ),
            "service_throttled",
        ),
        (
            oci.exceptions.RequestException("Read timed out with internal URL"),
            "network_error",
        ),
    ],
)
def test_oci_sdk_errors_are_classified_without_exposing_raw_messages(
    exception, expected_code
):
    error = _remote_failure(exception)
    assert error.code == expected_code
    assert "raw " not in error.safe_message
    assert "internal URL" not in error.safe_message


def test_oci_audit_is_admin_only_and_contains_no_credential_material(
    auth_env, oci_encryption_key
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    account_id = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()["id"]

    response = client.patch(
        f"/api/v1/cloud-accounts/{account_id}",
        headers=headers(tokens),
        json={"name": "Renamed OCI"},
    )
    assert response.status_code == 200

    audit = client.get(
        f"/api/v1/cloud-accounts/{account_id}/audit",
        headers=headers(tokens),
    )
    assert audit.status_code == 200
    text = json.dumps(audit.json())
    assert pem not in text
    assert "ciphertext" not in text
    assert "private_key" not in text
    assert any(item["action"] == "oci.account.create" for item in audit.json())
    assert any(item["action"] == "oci.account.update" for item in audit.json())

    assert (
        client.get(
            f"/api/v1/cloud-accounts/{account_id}/audit",
            headers=headers(tokens, "operator"),
        ).status_code
        == 403
    )
    with Session(engine) as db:
        assert db.scalar(
            select(func.count())
            .select_from(CloudAccountAuditEvent)
            .where(CloudAccountAuditEvent.account_id == account_id)
        ) >= 2


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_oci_mutations_and_connection_test_remain_admin_only(
    auth_env, oci_encryption_key, role
):
    client, _, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    account_id = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()["id"]

    assert (
        client.patch(
            f"/api/v1/cloud-accounts/{account_id}",
            headers=headers(tokens, role),
            json={"name": "Forbidden"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/cloud-accounts/{account_id}/test-connection",
            headers=headers(tokens, role),
        ).status_code
        == 403
    )


def test_oci_account_cannot_enter_aws_scan_pipeline(
    auth_env, oci_encryption_key
):
    client, engine, tokens, _ = auth_env
    pem, fingerprint = _api_key()
    created = _create_oci(client, tokens, _oci_payload(pem, fingerprint)).json()
    assert created["aws_configuration"] is None

    before = None
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(CollectionRun))

    response = client.post(
        "/api/v1/scans",
        headers=headers(tokens),
        json={"account_id": created["id"]},
    )
    assert response.status_code == 404

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == before


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
