from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.cloud import CloudProvider, normalize_provider, validate_native_account_id
from app.models.account import (
    AwsAccount,
    CloudAccount,
    CloudAccountAuditEvent,
    OciAccountConfiguration,
)
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AwsAccountConfigurationCreate,
    AwsAccountConfigurationUpdate,
    CloudAccountCreate,
    CloudAccountUpdate,
    OciAccountConfigurationCreate,
    OciAccountConfigurationUpdate,
)
from app.services.oci_auth import (
    OciConnectionError,
    OciConnectionSnapshot,
    candidate_snapshot,
    validate_connection,
    validate_private_key,
)
from app.services.oci_secrets import OciSecretKeyError, encrypt_secret


class UnsupportedProviderOperation(ValueError):
    pass


class StaleOciConfiguration(RuntimeError):
    pass


@dataclass(frozen=True)
class OciReplacementResult:
    verified_checks: tuple[str, ...]
    tested_at: datetime


def _account_options():
    return (
        selectinload(CloudAccount.aws_configuration),
        selectinload(CloudAccount.oci_configuration),
    )


def list_cloud_accounts(db: Session) -> list[CloudAccount]:
    return list(
        db.scalars(
            select(CloudAccount)
            .options(*_account_options())
            .order_by(CloudAccount.name, CloudAccount.id)
        )
    )


def get_cloud_account(db: Session, cloud_account_id: int) -> CloudAccount | None:
    return db.scalar(
        select(CloudAccount).options(*_account_options()).where(CloudAccount.id == cloud_account_id)
    )


def get_cloud_account_for_update(db: Session, cloud_account_id: int) -> CloudAccount | None:
    return db.scalar(
        select(CloudAccount)
        .options(*_account_options())
        .where(CloudAccount.id == cloud_account_id)
        .with_for_update()
    )


def require_aws_configuration(account: CloudAccount) -> AwsAccount:
    if account.provider != CloudProvider.AWS.value or account.aws_configuration is None:
        raise UnsupportedProviderOperation(
            f"Provider {account.provider} does not have an AWS operational configuration"
        )
    return account.aws_configuration


def require_oci_configuration(account: CloudAccount) -> OciAccountConfiguration:
    if account.provider != CloudProvider.OCI.value or account.oci_configuration is None:
        raise UnsupportedProviderOperation(
            f"Provider {account.provider} does not have an OCI operational configuration"
        )
    return account.oci_configuration


def list_cloud_account_audit(
    db: Session, cloud_account_id: int, *, limit: int = 100
) -> list[CloudAccountAuditEvent]:
    return list(
        db.scalars(
            select(CloudAccountAuditEvent)
            .where(CloudAccountAuditEvent.account_id == cloud_account_id)
            .order_by(CloudAccountAuditEvent.created_at.desc())
            .limit(limit)
        )
    )


def add_account_audit(
    db: Session,
    *,
    account: CloudAccount | None = None,
    account_id: int | None = None,
    provider: str | None = None,
    native_account_id: str | None = None,
    actor_id: str | None,
    action: str,
    result: str,
    detail: str = "",
) -> None:
    if account is not None:
        account_id = account.id
        provider = account.provider
        native_account_id = account.native_account_id
    if provider is None or native_account_id is None:
        raise ValueError("Audit provider and native account identity are required")
    db.add(
        CloudAccountAuditEvent(
            account_id=account_id,
            provider=provider,
            native_account_id=native_account_id,
            actor_id=actor_id,
            action=action,
            result=result,
            detail=detail[:500],
        )
    )


def _apply_schedule(
    account: AwsAccount,
    changes: dict,
    *,
    creating: bool = False,
) -> None:
    if creating:
        if account.schedule_enabled:
            account.next_scan_at = datetime.now(UTC)
        return
    if changes.get("schedule_enabled") is True and account.next_scan_at is None:
        account.next_scan_at = datetime.now(UTC)
    if changes.get("schedule_enabled") is False:
        account.next_scan_at = None
    if account.schedule_enabled and "scan_interval_hours" in changes:
        account.next_scan_at = datetime.now(UTC) + timedelta(hours=account.scan_interval_hours)


def _create_aws_configuration(
    cloud_account: CloudAccount,
    configuration: AwsAccountConfigurationCreate,
) -> AwsAccount:
    account = AwsAccount(
        name=cloud_account.name,
        aws_account_id=cloud_account.native_account_id,
        enabled=cloud_account.enabled,
        connection_status=cloud_account.connection_status,
        last_connection_test_at=cloud_account.last_connection_test_at,
        last_error=cloud_account.last_error,
        **configuration.model_dump(),
    )
    cloud_account.aws_configuration = account
    _apply_schedule(account, configuration.model_dump(), creating=True)
    return account


def _validate_oci_scope(
    *,
    compartment_ocids: list[str],
    include_root_compartment: bool,
    include_subcompartments: bool,
) -> None:
    if include_subcompartments and not (include_root_compartment or compartment_ocids):
        raise ValueError(
            "include_subcompartments requires the tenancy root or at least one compartment"
        )


def _encrypt_oci_credentials(
    private_key_pem: str,
    private_key_password: str | None,
    fingerprint: str,
) -> tuple[str, str | None, str]:
    cleaned = validate_private_key(private_key_pem, private_key_password, fingerprint)
    try:
        encrypted_key, key_version = encrypt_secret(cleaned)
        encrypted_password = (
            encrypt_secret(private_key_password, key_version=key_version)[0]
            if private_key_password is not None
            else None
        )
    except OciSecretKeyError as exc:
        raise OciConnectionError("local_configuration_invalid", str(exc)) from None
    return encrypted_key, encrypted_password, key_version


def _create_oci_configuration(
    cloud_account: CloudAccount,
    configuration: OciAccountConfigurationCreate,
) -> OciAccountConfiguration:
    encrypted_key, encrypted_password, key_version = _encrypt_oci_credentials(
        configuration.private_key_pem,
        configuration.private_key_password,
        configuration.fingerprint,
    )
    item = OciAccountConfiguration(
        user_ocid=configuration.user_ocid,
        fingerprint=configuration.fingerprint,
        region=configuration.region,
        scope_regions=configuration.scope_regions,
        compartment_ocids=configuration.compartment_ocids,
        include_root_compartment=configuration.include_root_compartment,
        include_subcompartments=configuration.include_subcompartments,
        private_key_ciphertext=encrypted_key,
        private_key_password_ciphertext=encrypted_password,
        credential_key_version=key_version,
    )
    cloud_account.oci_configuration = item
    return item


def create_cloud_account(
    db: Session,
    payload: CloudAccountCreate,
    *,
    actor_id: str | None = None,
) -> CloudAccount:
    provider = normalize_provider(payload.provider)
    native_account_id = validate_native_account_id(provider, payload.native_account_id)
    cloud_account = CloudAccount(
        provider=provider,
        native_account_id=native_account_id,
        name=payload.name,
        enabled=payload.enabled,
    )

    if provider == CloudProvider.AWS.value:
        if not isinstance(payload.configuration, AwsAccountConfigurationCreate):
            raise ValueError("AWS configuration is required")
        _create_aws_configuration(cloud_account, payload.configuration)
    elif provider == CloudProvider.OCI.value:
        if not isinstance(payload.configuration, OciAccountConfigurationCreate):
            raise ValueError("OCI configuration is required")
        _create_oci_configuration(cloud_account, payload.configuration)
    else:
        raise UnsupportedProviderOperation(
            f"Provider {provider} account registration is not supported in this stage"
        )

    db.add(cloud_account)
    db.flush()
    if provider == CloudProvider.OCI.value:
        add_account_audit(
            db,
            account=cloud_account,
            actor_id=actor_id,
            action="oci.account.create",
            result="success",
            detail="API signing credential stored encrypted",
        )
    return cloud_account


def _invalidate_connection_state(account: CloudAccount) -> None:
    account.connection_status = "untested"
    account.last_connection_test_at = None
    account.last_error = None


def _update_aws_configuration(
    account: CloudAccount,
    configuration_changes: dict,
) -> None:
    aws_account = require_aws_configuration(account)
    if "role_arn" in configuration_changes:
        role_account_id = configuration_changes["role_arn"].split(":")[4]
        if role_account_id != account.native_account_id:
            raise ValueError("Role ARN account does not match native account identifier")
    for field, value in configuration_changes.items():
        setattr(aws_account, field, value)
    _apply_schedule(aws_account, configuration_changes)


def _oci_update_values(
    configuration: OciAccountConfiguration,
    payload: OciAccountConfigurationUpdate,
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    fields = payload.model_fields_set
    if "private_key_pem" in fields:
        raise ValueError("OCI credential replacement must be validated before it is stored")
    if "private_key_password" in fields:
        raise ValueError("OCI key passphrase can only change together with a new private key")
    if "fingerprint" in fields:
        raise ValueError("OCI fingerprint can only change together with a new private key")

    values = {
        "user_ocid": changes.get("user_ocid", configuration.user_ocid),
        "region": changes.get("region", configuration.region),
        "scope_regions": changes.get("scope_regions", configuration.scope_regions),
        "compartment_ocids": changes.get("compartment_ocids", configuration.compartment_ocids),
        "include_root_compartment": changes.get(
            "include_root_compartment", configuration.include_root_compartment
        ),
        "include_subcompartments": changes.get(
            "include_subcompartments", configuration.include_subcompartments
        ),
    }
    _validate_oci_scope(
        compartment_ocids=values["compartment_ocids"],
        include_root_compartment=values["include_root_compartment"],
        include_subcompartments=values["include_subcompartments"],
    )
    return values


def update_cloud_account(
    db: Session,
    account: CloudAccount,
    payload: CloudAccountUpdate,
    *,
    actor_id: str | None = None,
) -> CloudAccount:
    changes = payload.model_dump(exclude_unset=True)
    configuration_payload = payload.configuration

    if account.provider == CloudProvider.AWS.value:
        if configuration_payload is not None and not isinstance(
            configuration_payload, AwsAccountConfigurationUpdate
        ):
            raise ValueError("OCI configuration is not valid for an AWS account")
        if "name" in changes:
            account.name = changes["name"]
        if "enabled" in changes:
            account.enabled = changes["enabled"]
        if configuration_payload is not None:
            _update_aws_configuration(
                account,
                configuration_payload.model_dump(exclude_unset=True),
            )
    elif account.provider == CloudProvider.OCI.value:
        if configuration_payload is not None and not isinstance(
            configuration_payload, OciAccountConfigurationUpdate
        ):
            raise ValueError("AWS configuration is not valid for an OCI account")
        if configuration_payload is not None and "private_key_pem" in (
            configuration_payload.model_fields_set
        ):
            raise ValueError("Use validated OCI credential replacement for a new private key")

        configuration = require_oci_configuration(account)
        relevant_changed = False
        credentials_removed = False
        if configuration_payload is not None:
            values = _oci_update_values(configuration, configuration_payload)
            for field, value in values.items():
                if getattr(configuration, field) != value:
                    setattr(configuration, field, value)
                    relevant_changed = True
            if (
                configuration_payload.remove_credentials
                and configuration.private_key_ciphertext is not None
            ):
                configuration.private_key_ciphertext = None
                configuration.private_key_password_ciphertext = None
                configuration.credential_key_version = None
                configuration.credential_revision += 1
                relevant_changed = True
                credentials_removed = True

        if "name" in changes:
            account.name = changes["name"]
        if "enabled" in changes:
            account.enabled = changes["enabled"]

        if relevant_changed:
            configuration.configuration_revision += 1
            _invalidate_connection_state(account)
        add_account_audit(
            db,
            account=account,
            actor_id=actor_id,
            action="oci.credentials.remove" if credentials_removed else "oci.account.update",
            result="success",
            detail=(
                "credential removed; connection validation invalidated"
                if credentials_removed
                else "connection validation invalidated"
                if relevant_changed
                else "administrative fields updated"
            ),
        )
    else:
        if configuration_payload is not None:
            raise UnsupportedProviderOperation(
                f"Provider {account.provider} configuration is not supported"
            )
        if "name" in changes:
            account.name = changes["name"]
        if "enabled" in changes:
            account.enabled = changes["enabled"]

    db.flush()
    return account


def prepare_oci_replacement(
    account: CloudAccount,
    payload: CloudAccountUpdate,
) -> tuple[OciConnectionSnapshot, tuple[str, str | None, str], int]:
    configuration = require_oci_configuration(account)
    update = payload.configuration
    if not isinstance(update, OciAccountConfigurationUpdate):
        raise ValueError("OCI configuration is required for credential replacement")
    if "private_key_pem" not in update.model_fields_set or update.private_key_pem is None:
        raise ValueError("A new OCI private key PEM is required")
    if "fingerprint" in update.model_fields_set and update.fingerprint is None:
        raise ValueError("OCI fingerprint cannot be removed")

    changes = update.model_dump(exclude_unset=True)
    fingerprint = changes.get("fingerprint", configuration.fingerprint)
    password = (
        update.private_key_password if "private_key_password" in update.model_fields_set else None
    )
    user_ocid = changes.get("user_ocid", configuration.user_ocid)
    region = changes.get("region", configuration.region)
    scope_regions = changes.get("scope_regions", configuration.scope_regions)
    compartment_ocids = changes.get("compartment_ocids", configuration.compartment_ocids)
    include_root_compartment = changes.get(
        "include_root_compartment", configuration.include_root_compartment
    )
    include_subcompartments = changes.get(
        "include_subcompartments", configuration.include_subcompartments
    )
    _validate_oci_scope(
        compartment_ocids=compartment_ocids,
        include_root_compartment=include_root_compartment,
        include_subcompartments=include_subcompartments,
    )
    encrypted = _encrypt_oci_credentials(
        update.private_key_pem,
        password,
        fingerprint,
    )
    expected_revision = configuration.configuration_revision
    snapshot = candidate_snapshot(
        cloud_account_id=account.id,
        configuration_revision=expected_revision,
        tenancy_ocid=account.native_account_id,
        user_ocid=user_ocid,
        fingerprint=fingerprint,
        region=region,
        scope_regions=scope_regions,
        compartment_ocids=compartment_ocids,
        include_root_compartment=include_root_compartment,
        include_subcompartments=include_subcompartments,
        private_key_pem=update.private_key_pem,
        private_key_password=password,
    )
    return snapshot, encrypted, expected_revision


def apply_validated_oci_replacement(
    db: Session,
    *,
    account_id: int,
    expected_revision: int,
    payload: CloudAccountUpdate,
    encrypted: tuple[str, str | None, str],
    validation_checks: tuple[str, ...],
    tested_at: datetime,
    actor_id: str | None,
) -> CloudAccount:
    account = get_cloud_account_for_update(db, account_id)
    if account is None:
        raise StaleOciConfiguration("OCI account was removed during credential validation")
    configuration = require_oci_configuration(account)
    if configuration.configuration_revision != expected_revision:
        raise StaleOciConfiguration(
            "OCI configuration changed while the replacement credential was being validated"
        )
    update = payload.configuration
    if not isinstance(update, OciAccountConfigurationUpdate):
        raise ValueError("OCI configuration is required")

    changes = update.model_dump(exclude_unset=True)
    for field in (
        "user_ocid",
        "fingerprint",
        "region",
        "scope_regions",
        "compartment_ocids",
        "include_root_compartment",
        "include_subcompartments",
    ):
        if field in changes:
            setattr(configuration, field, changes[field])

    encrypted_key, encrypted_password, key_version = encrypted
    configuration.private_key_ciphertext = encrypted_key
    configuration.private_key_password_ciphertext = encrypted_password
    configuration.credential_key_version = key_version
    configuration.credential_revision += 1
    configuration.configuration_revision += 1

    common_changes = payload.model_dump(exclude_unset=True, exclude={"configuration"})
    if "name" in common_changes:
        account.name = common_changes["name"]
    if "enabled" in common_changes:
        account.enabled = common_changes["enabled"]

    set_connection_state(
        account,
        status="connected",
        tested_at=tested_at,
        error=None,
    )
    add_account_audit(
        db,
        account=account,
        actor_id=actor_id,
        action="oci.credentials.replace",
        result="success",
        detail=f"credential replaced and validated; checks={len(validation_checks)}",
    )
    db.flush()
    return account


def replace_oci_credentials(
    db: Session,
    account: CloudAccount,
    payload: CloudAccountUpdate,
    *,
    actor_id: str | None,
) -> OciReplacementResult:
    snapshot, encrypted, expected_revision = prepare_oci_replacement(account, payload)
    account_id = account.id

    # End the read transaction before performing any remote network calls.
    db.commit()
    validation = validate_connection(snapshot)
    tested_at = datetime.now(UTC)

    try:
        apply_validated_oci_replacement(
            db,
            account_id=account_id,
            expected_revision=expected_revision,
            payload=payload,
            encrypted=encrypted,
            validation_checks=validation.verified_checks,
            tested_at=tested_at,
            actor_id=actor_id,
        )
    except Exception:
        db.rollback()
        raise
    return OciReplacementResult(
        verified_checks=validation.verified_checks,
        tested_at=tested_at,
    )


def create_legacy_aws_account(db: Session, payload: AccountCreate) -> AwsAccount:
    common_payload = CloudAccountCreate(
        provider=CloudProvider.AWS.value,
        native_account_id=payload.aws_account_id,
        name=payload.name,
        enabled=payload.enabled,
        configuration=AwsAccountConfigurationCreate(
            role_arn=payload.role_arn,
            external_id=payload.external_id,
            regions=payload.regions,
            is_management_account=payload.is_management_account,
            schedule_enabled=payload.schedule_enabled,
            scan_interval_hours=payload.scan_interval_hours,
        ),
    )
    return require_aws_configuration(create_cloud_account(db, common_payload))


def update_legacy_aws_account(
    db: Session,
    account: AwsAccount,
    payload: AccountUpdate,
) -> AwsAccount:
    if account.cloud_account is None:
        raise RuntimeError("AWS account is missing its CloudAccount relationship")
    changes = payload.model_dump(exclude_unset=True)
    common: dict = {}
    if "name" in changes:
        common["name"] = changes.pop("name")
    if "enabled" in changes:
        common["enabled"] = changes.pop("enabled")
    configuration = AwsAccountConfigurationUpdate(**changes) if changes else None
    update_cloud_account(
        db,
        account.cloud_account,
        CloudAccountUpdate(configuration=configuration, **common),
    )
    return account


def delete_cloud_account(
    db: Session,
    account: CloudAccount,
    *,
    actor_id: str | None = None,
) -> None:
    if account.provider == CloudProvider.OCI.value:
        add_account_audit(
            db,
            account=account,
            actor_id=actor_id,
            action="oci.account.delete",
            result="success",
            detail="account configuration deleted; OCI API key was not revoked remotely",
        )
    db.delete(account)
    db.flush()


def set_connection_state(
    account: CloudAccount,
    *,
    status: str,
    tested_at: datetime,
    error: str | None,
) -> None:
    account.connection_status = status
    account.last_connection_test_at = tested_at
    account.last_error = error
