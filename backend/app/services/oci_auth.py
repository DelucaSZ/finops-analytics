from __future__ import annotations

import hashlib
from dataclasses import dataclass

import oci
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests import exceptions as requests_exceptions

from app.models.account import CloudAccount, OciAccountConfiguration
from app.services.oci_secrets import OciSecretKeyError, decrypt_secret

CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 7
NO_RETRY = oci.retry.NoneRetryStrategy()


class OciConnectionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class OciConnectionSnapshot:
    cloud_account_id: int
    configuration_revision: int
    tenancy_ocid: str
    user_ocid: str
    fingerprint: str
    region: str
    scope_regions: tuple[str, ...]
    compartment_ocids: tuple[str, ...]
    include_root_compartment: bool
    include_subcompartments: bool
    private_key_pem: str
    private_key_password: str | None


@dataclass(frozen=True)
class OciConnectionValidation:
    verified_checks: tuple[str, ...]


def normalize_private_key_pem(private_key_pem: str) -> str:
    """Remove Oracle's optional leak-detection marker while retaining a standard PEM."""
    lines = private_key_pem.strip().splitlines()
    if lines and lines[-1].strip() == "OCI_API_KEY":
        lines.pop()
    return "\n".join(lines).strip() + "\n"


def _fingerprint(public_key: rsa.RSAPublicKey) -> str:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.md5(der, usedforsecurity=False).hexdigest()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def validate_private_key(
    private_key_pem: str,
    private_key_password: str | None,
    expected_fingerprint: str,
) -> str:
    cleaned = normalize_private_key_pem(private_key_pem)
    password = private_key_password.encode() if private_key_password is not None else None
    try:
        key = serialization.load_pem_private_key(cleaned.encode(), password=password)
    except (TypeError, ValueError):
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI private key PEM or passphrase is invalid",
        ) from None

    if not isinstance(key, rsa.RSAPrivateKey):
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI API signing key must be an RSA private key",
        )
    if key.key_size < 2048:
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI API signing RSA key must be at least 2048 bits",
        )

    actual = _fingerprint(key.public_key())
    if actual.lower() != expected_fingerprint.lower():
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI private key fingerprint does not match the configured fingerprint",
        )
    return cleaned


def snapshot_from_configuration(
    account: CloudAccount,
    configuration: OciAccountConfiguration,
) -> OciConnectionSnapshot:
    if not configuration.private_key_ciphertext or not configuration.credential_key_version:
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI API signing credential is not configured",
        )
    try:
        private_key_pem = decrypt_secret(
            configuration.private_key_ciphertext,
            key_version=configuration.credential_key_version,
        )
        password = (
            decrypt_secret(
                configuration.private_key_password_ciphertext,
                key_version=configuration.credential_key_version,
            )
            if configuration.private_key_password_ciphertext
            else None
        )
    except OciSecretKeyError as exc:
        raise OciConnectionError("local_configuration_invalid", str(exc)) from None

    cleaned = validate_private_key(
        private_key_pem,
        password,
        configuration.fingerprint,
    )
    return OciConnectionSnapshot(
        cloud_account_id=account.id,
        configuration_revision=configuration.configuration_revision,
        tenancy_ocid=account.native_account_id,
        user_ocid=configuration.user_ocid,
        fingerprint=configuration.fingerprint,
        region=configuration.region,
        scope_regions=tuple(configuration.scope_regions),
        compartment_ocids=tuple(configuration.compartment_ocids),
        include_root_compartment=configuration.include_root_compartment,
        include_subcompartments=configuration.include_subcompartments,
        private_key_pem=cleaned,
        private_key_password=password,
    )


def candidate_snapshot(
    *,
    cloud_account_id: int,
    configuration_revision: int,
    tenancy_ocid: str,
    user_ocid: str,
    fingerprint: str,
    region: str,
    scope_regions: list[str],
    compartment_ocids: list[str],
    include_root_compartment: bool,
    include_subcompartments: bool,
    private_key_pem: str,
    private_key_password: str | None,
) -> OciConnectionSnapshot:
    cleaned = validate_private_key(private_key_pem, private_key_password, fingerprint)
    return OciConnectionSnapshot(
        cloud_account_id=cloud_account_id,
        configuration_revision=configuration_revision,
        tenancy_ocid=tenancy_ocid,
        user_ocid=user_ocid,
        fingerprint=fingerprint,
        region=region,
        scope_regions=tuple(scope_regions),
        compartment_ocids=tuple(compartment_ocids),
        include_root_compartment=include_root_compartment,
        include_subcompartments=include_subcompartments,
        private_key_pem=cleaned,
        private_key_password=private_key_password,
    )


def _client(snapshot: OciConnectionSnapshot):
    try:
        signer = oci.signer.Signer(
            tenancy=snapshot.tenancy_ocid,
            user=snapshot.user_ocid,
            fingerprint=snapshot.fingerprint,
            private_key_content=snapshot.private_key_pem,
            pass_phrase=snapshot.private_key_password,
        )
        return oci.identity.IdentityClient(
            {"region": snapshot.region},
            signer=signer,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            retry_strategy=NO_RETRY,
        )
    except (
        oci.exceptions.ClientError,
        TypeError,
        ValueError,
    ):
        raise OciConnectionError(
            "local_configuration_invalid",
            "OCI signing configuration is invalid",
        ) from None


def _remote_failure(exc: Exception) -> OciConnectionError:
    if isinstance(exc, oci.exceptions.ServiceError):
        status = int(exc.status or 0)
        if status == 401:
            return OciConnectionError(
                "authentication_failed",
                "OCI rejected the API signing credentials",
            )
        if status in {403, 404}:
            return OciConnectionError(
                "authorization_failed",
                "OCI denied access or did not expose a required IAM resource",
            )
        if status == 429:
            return OciConnectionError(
                "service_throttled",
                "OCI temporarily rate-limited the connection test",
            )
        if status >= 500:
            return OciConnectionError(
                "service_unavailable",
                "OCI IAM is temporarily unavailable",
            )
        return OciConnectionError(
            "service_error",
            "OCI returned an unexpected service error during the connection test",
        )
    if isinstance(
        exc,
        (
            oci.exceptions.ConnectTimeout,
            oci.exceptions.RequestException,
            requests_exceptions.Timeout,
            requests_exceptions.ConnectionError,
        ),
    ):
        return OciConnectionError(
            "network_error",
            "OCI could not be reached before the connection test timeout",
        )
    if isinstance(exc, oci.exceptions.ClientError):
        return OciConnectionError(
            "local_configuration_invalid",
            "OCI SDK rejected the local signing configuration",
        )
    return OciConnectionError(
        "service_error",
        "OCI connection test failed unexpectedly",
    )


def validate_connection(snapshot: OciConnectionSnapshot) -> OciConnectionValidation:
    client = _client(snapshot)
    checks: list[str] = []
    try:
        tenancy = client.get_tenancy(
            snapshot.tenancy_ocid,
            retry_strategy=NO_RETRY,
        ).data
        if getattr(tenancy, "id", None) != snapshot.tenancy_ocid:
            raise OciConnectionError(
                "authorization_failed",
                "OCI tenancy identity did not match the configured tenancy",
            )
        checks.append("tenancy")

        user = client.get_user(
            snapshot.user_ocid,
            retry_strategy=NO_RETRY,
        ).data
        if getattr(user, "id", None) != snapshot.user_ocid:
            raise OciConnectionError(
                "authorization_failed",
                "OCI user identity did not match the configured user",
            )
        if getattr(user, "compartment_id", None) != snapshot.tenancy_ocid:
            raise OciConnectionError(
                "authorization_failed",
                "OCI user does not belong to the configured tenancy",
            )
        checks.append("user")

        subscriptions = oci.pagination.list_call_get_all_results(
            client.list_region_subscriptions,
            snapshot.tenancy_ocid,
            retry_strategy=NO_RETRY,
        ).data
        subscribed_regions = {
            item.region_name
            for item in subscriptions
            if getattr(item, "region_name", None)
        }
        required_regions = {snapshot.region, *snapshot.scope_regions}
        missing_regions = sorted(required_regions - subscribed_regions)
        if missing_regions:
            raise OciConnectionError(
                "authorization_failed",
                "One or more configured OCI regions are not subscribed in this tenancy",
            )
        checks.append("regions")

        for compartment_ocid in snapshot.compartment_ocids:
            compartment = client.get_compartment(
                compartment_ocid,
                retry_strategy=NO_RETRY,
            ).data
            if getattr(compartment, "id", None) != compartment_ocid:
                raise OciConnectionError(
                    "authorization_failed",
                    "OCI compartment identity did not match the configured scope",
                )
            checks.append(f"compartment:{compartment_ocid}")

        if snapshot.include_root_compartment:
            checks.append("root_compartment")

        if snapshot.include_subcompartments:
            bases = list(snapshot.compartment_ocids)
            if snapshot.include_root_compartment:
                bases.append(snapshot.tenancy_ocid)
            for base_ocid in bases:
                # This call proves that the integration may enumerate children from
                # the configured scope root. Descendant resources themselves are not
                # declared validated by Stage 18.
                client.list_compartments(
                    base_ocid,
                    access_level="ACCESSIBLE",
                    limit=1,
                    retry_strategy=NO_RETRY,
                )
                checks.append(f"subcompartment_listing:{base_ocid}")
    except OciConnectionError:
        raise
    except Exception as exc:
        raise _remote_failure(exc) from None

    return OciConnectionValidation(verified_checks=tuple(checks))
