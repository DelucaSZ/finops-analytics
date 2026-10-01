import hashlib

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.core.config import Settings, settings
from app.db.base import Base
from app.models.account import CloudAccount, OciAccountConfiguration
from app.services.collection_executors import has_collection_executor
from app.services.oci_credentials import (
    OciCredentialResolutionError,
    resolve_oci_signing_credentials,
)
from app.services.provider_capabilities import get_provider_capabilities

TENANCY_OCID = "ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
USER_OCID = "ocid1.user.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PRIVATE_KEY_MARKER = "SUPER_SECRET_PRIVATE_KEY_VALUE"
PASSPHRASE_MARKER = "SUPER_SECRET_PASSPHRASE_VALUE"
ENCRYPTION_KEY_MARKER = "SUPER_SECRET_ENCRYPTION_KEY_VALUE"
CIPHERTEXT_MARKER = "SUPER_SECRET_CIPHERTEXT_VALUE"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'oci-credentials.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(key.decode()))
    monkeypatch.setattr(settings, "oci_credentials_key_version", "test-v1")
    return key


def _api_key(passphrase: str | None = None) -> tuple[str, str]:
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
    der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.md5(der, usedforsecurity=False).hexdigest()
    fingerprint = ":".join(digest[index : index + 2] for index in range(0, 32, 2))
    return pem, fingerprint


def _oci_account(
    db: Session,
    encryption_key: bytes,
    *,
    passphrase: str | None = None,
) -> tuple[int, OciAccountConfiguration, str]:
    pem, fingerprint = _api_key(passphrase)
    cipher = Fernet(encryption_key)
    account = CloudAccount(
        provider="oci",
        native_account_id=TENANCY_OCID,
        name="OCI Test",
        enabled=True,
        connection_status="connected",
    )
    account.oci_configuration = OciAccountConfiguration(
        user_ocid=USER_OCID,
        fingerprint=fingerprint,
        region="sa-saopaulo-1",
        scope_regions=["sa-saopaulo-1"],
        compartment_ocids=[],
        include_root_compartment=True,
        include_subcompartments=False,
        private_key_ciphertext=cipher.encrypt(pem.encode()).decode(),
        private_key_password_ciphertext=(
            cipher.encrypt(passphrase.encode()).decode() if passphrase is not None else None
        ),
        credential_key_version="test-v1",
    )
    db.add(account)
    db.commit()
    return account.id, account.oci_configuration, pem


def test_resolver_loads_valid_private_key_without_remote_oci_calls(db, encryption_key, monkeypatch):
    account_id, _, pem = _oci_account(db, encryption_key)

    def fail_if_client_created(*_args, **_kwargs):
        pytest.fail("OCI SDK client must not be created while resolving credentials")

    monkeypatch.setattr("app.services.oci_auth.oci.identity.IdentityClient", fail_if_client_created)

    credentials = resolve_oci_signing_credentials(db, account_id)

    assert credentials.cloud_account_id == account_id
    assert credentials.tenancy_ocid == TENANCY_OCID
    assert credentials.user_ocid == USER_OCID
    assert credentials.private_key_pem == pem
    assert credentials.private_key_password is None


def test_resolver_loads_private_key_and_passphrase(db, encryption_key):
    account_id, _, pem = _oci_account(
        db,
        encryption_key,
        passphrase=PASSPHRASE_MARKER,
    )

    credentials = resolve_oci_signing_credentials(db, account_id)

    assert credentials.private_key_pem == pem
    assert credentials.private_key_password == PASSPHRASE_MARKER


def test_resolver_rejects_missing_oci_configuration(db):
    account = CloudAccount(
        provider="oci",
        native_account_id=TENANCY_OCID,
        name="OCI Missing Config",
        enabled=True,
    )
    db.add(account)
    db.commit()

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account.id)

    assert exc_info.value.internal_code == "configuration_missing"


def test_resolver_rejects_missing_encryption_key(db, encryption_key, monkeypatch):
    account_id, _, _ = _oci_account(db, encryption_key)
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(""))

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account_id)

    assert exc_info.value.internal_code == "encryption_key_missing"


def test_resolver_rejects_malformed_encryption_key_without_leaking_it(
    db, encryption_key, monkeypatch
):
    account_id, _, _ = _oci_account(db, encryption_key)
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(ENCRYPTION_KEY_MARKER))

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account_id)

    assert exc_info.value.internal_code == "encryption_key_invalid"
    assert ENCRYPTION_KEY_MARKER not in str(exc_info.value)


def test_resolver_rejects_invalid_ciphertext_without_leaking_it(db, encryption_key):
    account_id, configuration, _ = _oci_account(db, encryption_key)
    configuration.private_key_ciphertext = CIPHERTEXT_MARKER
    db.commit()

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account_id)

    assert exc_info.value.internal_code == "credential_decryption_failed"
    assert CIPHERTEXT_MARKER not in str(exc_info.value)


def test_resolver_rejects_missing_private_key(db, encryption_key):
    account_id, configuration, _ = _oci_account(db, encryption_key)
    configuration.private_key_ciphertext = None
    db.commit()

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account_id)

    assert exc_info.value.internal_code == "credential_missing"


@pytest.mark.parametrize("provider", ["aws", "unknown-cloud"])
def test_resolver_rejects_non_oci_provider(db, provider):
    account = CloudAccount(
        provider=provider,
        native_account_id="123456789012",
        name="Not OCI",
        enabled=True,
    )
    db.add(account)
    db.commit()

    with pytest.raises(OciCredentialResolutionError) as exc_info:
        resolve_oci_signing_credentials(db, account.id)

    assert exc_info.value.internal_code == "provider_mismatch"


def test_plaintext_secrets_are_redacted_from_repr_and_logs(db, encryption_key, caplog):
    account_id, _, pem = _oci_account(
        db,
        encryption_key,
        passphrase=PASSPHRASE_MARKER,
    )

    credentials = resolve_oci_signing_credentials(db, account_id)
    representation = repr(credentials)

    assert pem not in representation
    assert PRIVATE_KEY_MARKER not in representation
    assert PASSPHRASE_MARKER not in representation
    assert pem not in caplog.text
    assert PASSPHRASE_MARKER not in caplog.text


def test_worker_uses_shared_settings_without_enabling_oci_collection(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "oci_credentials_key", SecretStr(key))

    assert worker.settings is settings
    assert worker.settings.oci_credentials_key.get_secret_value() == key
    assert get_provider_capabilities("oci").manual_collection is False
    assert get_provider_capabilities("oci").scheduling is False
    assert has_collection_executor("oci") is False


def test_aws_only_settings_do_not_require_oci_key(monkeypatch):
    monkeypatch.delenv("NUVEMIQ_OCI_CREDENTIALS_KEY", raising=False)

    configured = Settings(_env_file=None)

    assert configured.oci_credentials_key.get_secret_value() == ""


def test_malformed_oci_key_is_validated_lazily(monkeypatch):
    monkeypatch.setenv("NUVEMIQ_OCI_CREDENTIALS_KEY", ENCRYPTION_KEY_MARKER)

    configured = Settings(_env_file=None)

    assert configured.oci_credentials_key.get_secret_value() == ENCRYPTION_KEY_MARKER
