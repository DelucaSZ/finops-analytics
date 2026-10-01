from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.cloud import CloudProvider
from app.models.account import CloudAccount
from app.services.oci_auth import (
    OciConnectionError,
    OciConnectionSnapshot,
    snapshot_from_configuration,
)


class OciCredentialResolutionError(OciConnectionError):
    """Safe internal error raised while resolving stored OCI signing credentials."""

    def __init__(self, internal_code: str, message: str):
        super().__init__(
            "local_configuration_invalid",
            message,
            internal_code=internal_code,
        )


def _require_text(value: str | None, *, code: str, message: str) -> None:
    if value is None or not value.strip():
        raise OciCredentialResolutionError(code, message)


def resolve_oci_signing_credentials(
    db: Session,
    cloud_account_id: int,
) -> OciConnectionSnapshot:
    """Resolve encrypted OCI signing credentials for trusted backend/worker code only."""

    account = db.scalar(
        select(CloudAccount)
        .options(selectinload(CloudAccount.oci_configuration))
        .where(CloudAccount.id == cloud_account_id)
    )
    if account is None:
        raise OciCredentialResolutionError(
            "account_not_found",
            "OCI cloud account does not exist",
        )
    if account.provider != CloudProvider.OCI.value:
        raise OciCredentialResolutionError(
            "provider_mismatch",
            "Cloud account provider is not OCI",
        )

    configuration = account.oci_configuration
    if configuration is None:
        raise OciCredentialResolutionError(
            "configuration_missing",
            "OCI operational configuration is missing",
        )

    _require_text(
        configuration.user_ocid,
        code="user_ocid_missing",
        message="OCI user OCID is not configured",
    )
    _require_text(
        configuration.fingerprint,
        code="fingerprint_missing",
        message="OCI API signing fingerprint is not configured",
    )
    _require_text(
        configuration.region,
        code="region_missing",
        message="OCI region is not configured",
    )
    _require_text(
        configuration.private_key_ciphertext,
        code="credential_missing",
        message="OCI API signing credential is not configured",
    )
    _require_text(
        configuration.credential_key_version,
        code="credential_key_version_missing",
        message="OCI credential encryption key version is not configured",
    )

    try:
        return snapshot_from_configuration(account, configuration)
    except OciConnectionError as exc:
        raise OciCredentialResolutionError(
            exc.internal_code or "credential_resolution_failed",
            exc.safe_message,
        ) from None
