from types import SimpleNamespace

import pytest

from app.services.collection_errors import (
    GENERIC_ERROR,
    classify_collection_error,
    sanitize_collection_error,
)
from app.services.collection_executors import (
    AwsCollectionExecutor,
    OciCollectionExecutor,
    ProviderExecutionError,
)
from app.services.oci_auth import OciConnectionSnapshot


@pytest.mark.parametrize(
    ("error", "category", "retryable"),
    [
        (RuntimeError("local_configuration_invalid"), "configuration", False),
        (RuntimeError("InvalidClientTokenId"), "authentication", False),
        (RuntimeError("AccessDenied"), "authorization", False),
        (RuntimeError("Throttling"), "rate_limit", True),
        (TimeoutError("provider timeout"), "timeout", True),
        (RuntimeError("ServiceError 503 service unavailable"), "provider_service", True),
        (RuntimeError("data coverage partial data"), "data_coverage", None),
        (RuntimeError("Cloud account is disabled"), "validation", False),
        (RuntimeError("unexpected analyzer bug"), "internal", None),
    ],
)
def test_collection_error_taxonomy(error, category, retryable):
    info = classify_collection_error(error)
    assert info.category == category
    assert info.retryable is retryable


def test_persistence_error_taxonomy_uses_exception_type():
    class DatabaseError(Exception):
        pass

    info = classify_collection_error(DatabaseError("SUPER_SECRET_SQL_PARAMETER"))
    assert info.category == "persistence"
    assert info.public_message == GENERIC_ERROR
    assert "SUPER_SECRET_SQL_PARAMETER" not in info.public_message


@pytest.mark.parametrize(
    "secret",
    [
        "SUPER_SECRET_OCI_PRIVATE_KEY",
        "SUPER_SECRET_OCI_PASSPHRASE",
        "SUPER_SECRET_OCI_ENCRYPTION_KEY",
        "SUPER_SECRET_AWS_ACCESS_KEY",
        "SUPER_SECRET_AWS_SECRET_KEY",
        "SUPER_SECRET_AWS_SESSION_TOKEN",
    ],
)
def test_unknown_secrets_never_leave_collection_error_sanitizer(secret):
    error = RuntimeError(f"provider payload contains {secret}")
    assert sanitize_collection_error(error) == GENERIC_ERROR
    wrapped = ProviderExecutionError("oci", error, stage="monitoring")
    assert secret not in str(wrapped)
    assert secret not in wrapped.public_message


def test_oci_snapshot_repr_excludes_plaintext_credentials():
    snapshot = OciConnectionSnapshot(
        cloud_account_id=1,
        configuration_revision=2,
        tenancy_ocid="ocid1.tenancy.oc1..test",
        user_ocid="ocid1.user.oc1..test",
        fingerprint="aa:bb",
        region="sa-saopaulo-1",
        scope_regions=("sa-saopaulo-1",),
        compartment_ocids=(),
        include_root_compartment=True,
        include_subcompartments=True,
        private_key_pem="SUPER_SECRET_OCI_PRIVATE_KEY",
        private_key_password="SUPER_SECRET_OCI_PASSPHRASE",
    )
    rendered = repr(snapshot)
    assert "SUPER_SECRET_OCI_PRIVATE_KEY" not in rendered
    assert "SUPER_SECRET_OCI_PASSPHRASE" not in rendered


def test_provider_execution_error_exposes_operational_metadata_only():
    error = ProviderExecutionError(
        "oci",
        RuntimeError("Throttling provider payload SUPER_SECRET_OCI_PRIVATE_KEY"),
        connection_failure=False,
        stage="usage",
    )
    assert error.provider == "oci"
    assert error.stage == "usage"
    assert error.category == "rate_limit"
    assert error.retryable is True
    assert error.connection_failure is False
    assert "SUPER_SECRET_OCI_PRIVATE_KEY" not in str(error)


def test_aws_authorization_error_does_not_invalidate_connection_status():
    account = SimpleNamespace(connection_status="connected", last_error=None)
    AwsCollectionExecutor().mark_connection_failure(
        account,
        "Acesso negado (AccessDenied). Verifique as permissões da coleta.",
    )
    assert account.connection_status == "connected"
    assert account.last_error is None


def test_aws_authentication_error_can_invalidate_connection_status():
    account = SimpleNamespace(connection_status="connected", last_error=None)
    AwsCollectionExecutor().mark_connection_failure(
        account,
        "Credencial inválida (InvalidClientTokenId). Verifique a autenticação.",
    )
    assert account.connection_status == "error"
    assert "InvalidClientTokenId" in account.last_error


def test_oci_authorization_error_does_not_invalidate_connection_status():
    account = SimpleNamespace(connection_status="connected", last_error=None)
    OciCollectionExecutor().mark_connection_failure(
        account,
        "Sem permissão para consultar esta fonte no provider.",
    )
    assert account.connection_status == "connected"
    assert account.last_error is None
