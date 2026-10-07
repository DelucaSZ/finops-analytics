import logging
from types import SimpleNamespace

import pytest

from app.api.routes import cloud_accounts as cloud_account_routes
from app.services.collection_errors import (
    GENERIC_ERROR,
    classify_collection_error,
    sanitize_collection_error,
)
from app.services.collection_executors import (
    AwsCollectionExecutor,
    OciCollectionExecutor,
    ProviderExecutionError,
    _log_stage,
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


def test_aws_collector_authorization_error_is_not_connection_failure():
    error = ProviderExecutionError(
        "aws",
        RuntimeError("AccessDenied"),
        connection_failure=False,
        stage="collectors",
    )
    assert error.category == "authorization"
    assert error.stage == "collectors"
    assert error.connection_failure is False


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


class _FakeDb:
    def scalar(self, _statement):
        return "run-correlation-1"


@pytest.mark.parametrize(
    ("provider", "trigger"),
    [
        ("aws", "manual"),
        ("aws", "scheduled"),
        ("oci", "manual"),
        ("oci", "scheduled"),
    ],
)
def test_stage_log_has_common_multicloud_correlation_context(caplog, provider, trigger):
    account = SimpleNamespace(
        provider=provider,
        id=42,
        native_account_id="native-account-1",
    )
    scan = SimpleNamespace(id="scan-correlation-1", trigger=trigger)

    with caplog.at_level(logging.INFO, logger="deepops.collection_executor"):
        _log_stage(
            _FakeDb(),
            account,
            scan,
            event="collection_stage_completed",
            stage="analyzers" if provider == "oci" else "collectors",
            duration_ms=125,
            resource_count=37,
            warning_count=2,
        )

    message = caplog.records[-1].getMessage()
    assert f"provider={provider}" in message
    assert "cloud_account_id=42" in message
    assert "scan_id=scan-correlation-1" in message
    assert "collection_run_id=run-correlation-1" in message
    assert f"trigger={trigger}" in message
    assert "duration_ms=125" in message
    assert "resource_count=37" in message
    assert "warning_count=2" in message
    assert "stage=" in message


def test_stage_error_log_has_safe_category_and_retryability(caplog):
    account = SimpleNamespace(provider="oci", id=42, native_account_id="native-account-1")
    scan = SimpleNamespace(id="scan-correlation-1", trigger="scheduled")
    error = RuntimeError("Throttling SUPER_SECRET_OCI_PRIVATE_KEY")

    with caplog.at_level(logging.INFO, logger="deepops.collection_executor"):
        _log_stage(
            _FakeDb(),
            account,
            scan,
            event="collection_stage_failed",
            stage="usage",
            error=error,
        )

    message = caplog.records[-1].getMessage()
    assert "stage=usage" in message
    assert "error_category=rate_limit" in message
    assert "retryable=true" in message
    assert "SUPER_SECRET_OCI_PRIVATE_KEY" not in message


def test_schedule_audit_records_only_safe_operational_changes(monkeypatch):
    events = []

    def capture(_db, **kwargs):
        events.append(kwargs)

    monkeypatch.setattr(cloud_account_routes, "add_account_audit", capture)
    account = SimpleNamespace(
        schedule_enabled=True,
        scan_interval_hours=24,
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..test",
    )

    cloud_account_routes._audit_schedule_changes(
        object(),
        account=account,
        actor_id="operator-1",
        previous_enabled=False,
        previous_interval=12,
    )

    assert [event["action"] for event in events] == [
        "schedule.enabled",
        "schedule.interval_changed",
    ]
    assert all(event["actor_id"] == "operator-1" for event in events)
    rendered = repr(events)
    for secret in (
        "SUPER_SECRET_OCI_PRIVATE_KEY",
        "SUPER_SECRET_OCI_PASSPHRASE",
        "SUPER_SECRET_AWS_SECRET_KEY",
    ):
        assert secret not in rendered
