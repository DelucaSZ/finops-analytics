from app.models.account import CloudAccount
from app.services.collection_errors import GENERIC_ERROR, sanitize_collection_error
from app.services.collection_executors import OciCollectionExecutor


def _account() -> CloudAccount:
    return CloudAccount(
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..test",
        name="OCI connection status test",
        enabled=True,
        connection_status="connected",
    )


def test_safe_oci_auth_failure_marks_connection_error_without_echoing_detail():
    account = _account()
    error = sanitize_collection_error(
        RuntimeError("OCI authentication failure: provider diagnostic must not be exposed")
    )

    assert error is not None
    assert "provider diagnostic" not in error

    OciCollectionExecutor().mark_connection_failure(account, error)

    assert account.connection_status == "error"
    assert account.last_error == error


def test_generic_collection_failure_does_not_reclassify_oci_connection():
    account = _account()

    OciCollectionExecutor().mark_connection_failure(account, GENERIC_ERROR)

    assert account.connection_status == "connected"
    assert account.last_error is None
