import uuid
from datetime import UTC, datetime

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider
from app.core.security import require_admin, require_operator, require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.account import (
    CloudAccountAuditRead,
    CloudAccountCreate,
    CloudAccountRead,
    CloudAccountUpdate,
    ConnectionTestResult,
    OciAccountConfigurationUpdate,
    ProviderCapabilitiesRead,
)
from app.schemas.scan import ScanRead
from app.services.audit import AuditService, audit_snapshot
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.cloud_accounts import (
    StaleOciConfiguration,
    UnsupportedProviderOperation,
    add_account_audit,
    create_cloud_account,
    delete_cloud_account,
    get_cloud_account,
    get_cloud_account_for_update,
    list_cloud_account_audit,
    list_cloud_accounts,
    replace_oci_credentials,
    require_aws_configuration,
    require_oci_configuration,
    set_connection_state,
    update_cloud_account,
)
from app.services.collection_errors import sanitize_collection_error
from app.services.oci_auth import OciConnectionError, validate_connection
from app.services.oci_credentials import resolve_oci_signing_credentials
from app.services.provider_capabilities import (
    ProviderOperation,
    list_provider_capabilities,
    require_provider_operation,
)
from app.services.scan_queue import CollectionPreconditionError, queue_manual_collection

router = APIRouter(
    prefix="/cloud-accounts",
    tags=["cloud-accounts"],
    dependencies=[Depends(require_user)],
)


def _get_account(db: Session, account_id: int):
    account = get_cloud_account(db, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    return account


def _account_label(account) -> str:
    return f"{account.provider.upper()} · {account.name} · {account.native_account_id}"


def _account_snapshot(account) -> dict:
    data = {
        "provider": account.provider,
        "native_account_id": account.native_account_id,
        "name": account.name,
        "enabled": account.enabled,
        "schedule_enabled": account.schedule_enabled,
        "scan_interval_hours": account.scan_interval_hours,
        "connection_status": account.connection_status,
    }
    if account.provider == CloudProvider.AWS.value and account.aws_configuration is not None:
        config = account.aws_configuration
        data["configuration"] = {
            "role_arn": config.role_arn,
            "regions": list(config.regions or []),
            "is_management_account": config.is_management_account,
        }
    elif account.provider == CloudProvider.OCI.value and account.oci_configuration is not None:
        config = account.oci_configuration
        data["configuration"] = {
            "user_ocid": config.user_ocid,
            "fingerprint": config.fingerprint,
            "region": config.region,
            "scope_regions": list(config.scope_regions or []),
            "compartment_ocids": list(config.compartment_ocids or []),
            "include_root_compartment": config.include_root_compartment,
            "include_subcompartments": config.include_subcompartments,
            "credentials_configured": config.credentials_configured,
        }
    return audit_snapshot(data)


def _record_account(
    db: Session,
    *,
    actor: User,
    account,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
) -> None:
    AuditService.record(
        db,
        actor=actor,
        module="accounts",
        action=action,
        entity_type="cloud_account",
        entity_id=account.id,
        entity_label=_account_label(account),
        before=before,
        after=after,
        source="API",
        metadata=metadata,
    )


def _oci_failure_status(error: OciConnectionError) -> int:
    if error.code in {"network_error", "service_throttled", "service_unavailable"}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_422_UNPROCESSABLE_ENTITY


def _record_failed_oci_mutation(
    db: Session,
    *,
    actor_id: str,
    account_id: int | None,
    native_account_id: str,
    action: str,
    result: str,
    detail: str,
) -> None:
    db.rollback()
    add_account_audit(
        db,
        account_id=account_id,
        provider=CloudProvider.OCI.value,
        native_account_id=native_account_id,
        actor_id=actor_id,
        action=action,
        result=result,
        detail=detail,
    )
    db.commit()


def _audit_schedule_changes(
    db: Session,
    *,
    account,
    actor_id: str,
    previous_enabled: bool,
    previous_interval: int,
) -> None:
    if account.schedule_enabled != previous_enabled:
        add_account_audit(
            db,
            account=account,
            actor_id=actor_id,
            action=("schedule.enabled" if account.schedule_enabled else "schedule.disabled"),
            result="success",
            detail=(
                f"previous={str(previous_enabled).lower()} "
                f"new={str(account.schedule_enabled).lower()}"
            ),
        )
    if account.scan_interval_hours != previous_interval:
        add_account_audit(
            db,
            account=account,
            actor_id=actor_id,
            action="schedule.interval_changed",
            result="success",
            detail=f"previous_hours={previous_interval} new_hours={account.scan_interval_hours}",
        )


@router.get("/aws/external-id", dependencies=[Depends(require_admin)])
def generate_aws_external_id() -> dict[str, str]:
    return {"external_id": f"nuvemiq-{uuid.uuid4()}"}


@router.get("/capabilities", response_model=list[ProviderCapabilitiesRead])
def provider_capabilities() -> list[dict]:
    return list_provider_capabilities()


@router.get("", response_model=list[CloudAccountRead])
def list_accounts(db: Session = Depends(get_db)):
    return list_cloud_accounts(db)


@router.post("", response_model=CloudAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: CloudAccountCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    actor_id = actor.id
    try:
        account = create_cloud_account(db, payload, actor_id=actor_id)
        account_id = account.id
        _record_account(
            db,
            actor=actor,
            account=account,
            action="account.create",
            after=_account_snapshot(account),
        )
        db.commit()
        return get_cloud_account(db, account_id)
    except OciConnectionError as exc:
        if payload.provider == CloudProvider.OCI.value:
            _record_failed_oci_mutation(
                db,
                actor_id=actor_id,
                account_id=None,
                native_account_id=payload.native_account_id,
                action="oci.account.create",
                result="failure",
                detail=exc.code,
            )
        else:
            db.rollback()
        raise HTTPException(
            status_code=_oci_failure_status(exc),
            detail={"code": exc.code, "message": exc.safe_message},
        ) from exc
    except UnsupportedProviderOperation as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        if payload.provider == CloudProvider.OCI.value:
            _record_failed_oci_mutation(
                db,
                actor_id=actor_id,
                account_id=None,
                native_account_id=payload.native_account_id,
                action="oci.account.create",
                result="failure",
                detail="duplicate_account",
            )
        else:
            db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this provider and native identifier is already registered",
        ) from exc


@router.get("/{account_id}", response_model=CloudAccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    return _get_account(db, account_id)


@router.post("/{account_id}/scans", response_model=ScanRead, status_code=status.HTTP_202_ACCEPTED)
def create_account_scan(
    account_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
):
    account = _get_account(db, account_id)
    try:
        scan = queue_manual_collection(db, account, actor_id=actor.id)
        db.commit()
        db.refresh(scan)
        return scan
    except (UnsupportedProviderOperation, CollectionPreconditionError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{account_id}/audit", response_model=list[CloudAccountAuditRead])
def get_account_audit(
    account_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_account(db, account_id)
    return list_cloud_account_audit(db, account_id, limit=limit)


@router.patch("/{account_id}", response_model=CloudAccountRead)
def update_account(
    account_id: int,
    payload: CloudAccountUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    actor_id = actor.id
    account = _get_account(db, account_id)
    before = _account_snapshot(account)
    native_account_id = account.native_account_id
    provider = account.provider
    previous_schedule_enabled = account.schedule_enabled
    previous_scan_interval_hours = account.scan_interval_hours
    configuration = payload.configuration
    replacing_oci_credential = (
        provider == CloudProvider.OCI.value
        and isinstance(configuration, OciAccountConfigurationUpdate)
        and "private_key_pem" in configuration.model_fields_set
    )

    try:
        if replacing_oci_credential:
            result = replace_oci_credentials(db, account, payload, actor_id=actor_id)
            _audit_schedule_changes(
                db,
                account=account,
                actor_id=actor_id,
                previous_enabled=previous_schedule_enabled,
                previous_interval=previous_scan_interval_hours,
            )
            after = _account_snapshot(account)
            if before != after:
                _record_account(
                    db,
                    actor=actor,
                    account=account,
                    action="account.update",
                    before=before,
                    after=after,
                    metadata={"credential_replaced": True},
                )
            db.commit()
            refreshed = get_cloud_account(db, account_id)
            if refreshed is None:
                raise HTTPException(status_code=404, detail="Cloud account not found")
            refreshed.last_connection_test_at = result.tested_at
            return refreshed

        update_cloud_account(db, account, payload, actor_id=actor_id)
        _audit_schedule_changes(
            db,
            account=account,
            actor_id=actor_id,
            previous_enabled=previous_schedule_enabled,
            previous_interval=previous_scan_interval_hours,
        )
        after = _account_snapshot(account)
        if before != after:
            action = "account.update"
            changed = sorted(
                key for key in set(before) | set(after) if before.get(key) != after.get(key)
            )
            if changed == ["enabled"]:
                action = "account.enable" if account.enabled else "account.disable"
            elif set(changed).issubset({"schedule_enabled", "scan_interval_hours"}):
                action = "account.schedule_update"
            _record_account(
                db,
                actor=actor,
                account=account,
                action=action,
                before=before,
                after=after,
            )
        db.commit()
        return get_cloud_account(db, account_id)
    except OciConnectionError as exc:
        if provider == CloudProvider.OCI.value:
            _record_failed_oci_mutation(
                db,
                actor_id=actor_id,
                account_id=account_id,
                native_account_id=native_account_id,
                action=(
                    "oci.credentials.replace"
                    if replacing_oci_credential
                    else "oci.account.update"
                ),
                result="failure",
                detail=exc.code,
            )
        else:
            db.rollback()
        raise HTTPException(
            status_code=_oci_failure_status(exc),
            detail={"code": exc.code, "message": exc.safe_message},
        ) from exc
    except StaleOciConfiguration as exc:
        _record_failed_oci_mutation(
            db,
            actor_id=actor_id,
            account_id=account_id,
            native_account_id=native_account_id,
            action="oci.credentials.replace",
            result="stale",
            detail="configuration_changed_during_validation",
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (UnsupportedProviderOperation, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Account update conflicts with existing data",
        ) from exc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    account = _get_account(db, account_id)
    before = _account_snapshot(account)
    label = _account_label(account)
    delete_cloud_account(db, account, actor_id=actor.id)
    AuditService.record(
        db,
        actor=actor,
        module="accounts",
        action="account.delete",
        entity_type="cloud_account",
        entity_id=account_id,
        entity_label=label,
        before=before,
        source="API",
    )
    db.commit()


def _test_aws_connection(account, db: Session, actor: User) -> ConnectionTestResult:
    try:
        aws_account = require_aws_configuration(account)
    except UnsupportedProviderOperation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    before = _account_snapshot(account)
    tested_at = datetime.now(UTC)
    expected_account_id = account.native_account_id
    try:
        identity = get_caller_identity(assume_account_session(aws_account))
        if identity.account_id != expected_account_id:
            raise ValueError(
                f"Expected account {expected_account_id}, received {identity.account_id}"
            )
        set_connection_state(account, status="connected", tested_at=tested_at, error=None)
        result = ConnectionTestResult(
            ok=True,
            provider=CloudProvider.AWS.value,
            expected_account_id=expected_account_id,
            caller_account_id=identity.account_id,
            caller_arn=identity.arn,
            verified_checks=["sts:GetCallerIdentity"],
        )
    except (BotoCoreError, ClientError, ValueError) as exc:
        error = sanitize_collection_error(exc)[:2000]
        set_connection_state(account, status="error", tested_at=tested_at, error=error)
        result = ConnectionTestResult(
            ok=False,
            provider=CloudProvider.AWS.value,
            expected_account_id=expected_account_id,
            error_code="aws_connection_failed",
            error=error,
        )
    _record_account(
        db,
        actor=actor,
        account=account,
        action="account.connection_test",
        before=before,
        after=_account_snapshot(account),
        metadata={
            "provider": account.provider,
            "result": "success" if result.ok else "failure",
        },
    )
    db.commit()
    return result


def _persist_oci_test_result(
    db: Session,
    *,
    account_id: int,
    expected_revision: int,
    actor: User,
    tested_at: datetime,
    error: OciConnectionError | None,
    verified_checks: tuple[str, ...],
) -> ConnectionTestResult:
    account = get_cloud_account_for_update(db, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    before = _account_snapshot(account)
    configuration = require_oci_configuration(account)
    if configuration.configuration_revision != expected_revision:
        add_account_audit(
            db,
            account=account,
            actor_id=actor.id,
            action="oci.connection.test",
            result="stale",
            detail="configuration_changed_during_test",
        )
        _record_account(
            db,
            actor=actor,
            account=account,
            action="account.connection_test",
            before=before,
            after=_account_snapshot(account),
            metadata={"provider": account.provider, "result": "stale"},
        )
        db.commit()
        return ConnectionTestResult(
            ok=False,
            provider=CloudProvider.OCI.value,
            expected_account_id=account.native_account_id,
            error_code="stale_configuration",
            error="OCI configuration changed while the connection test was running",
        )

    if error is None:
        set_connection_state(account, status="connected", tested_at=tested_at, error=None)
        add_account_audit(
            db,
            account=account,
            actor_id=actor.id,
            action="oci.connection.test",
            result="success",
            detail=f"checks={len(verified_checks)}",
        )
        result = ConnectionTestResult(
            ok=True,
            provider=CloudProvider.OCI.value,
            expected_account_id=account.native_account_id,
            caller_account_id=account.native_account_id,
            verified_checks=list(verified_checks),
        )
    else:
        set_connection_state(
            account,
            status="error",
            tested_at=tested_at,
            error=error.safe_message[:2000],
        )
        add_account_audit(
            db,
            account=account,
            actor_id=actor.id,
            action="oci.connection.test",
            result="failure",
            detail=error.code,
        )
        result = ConnectionTestResult(
            ok=False,
            provider=CloudProvider.OCI.value,
            expected_account_id=account.native_account_id,
            error_code=error.code,
            error=error.safe_message,
        )
    _record_account(
        db,
        actor=actor,
        account=account,
        action="account.connection_test",
        before=before,
        after=_account_snapshot(account),
        metadata={
            "provider": account.provider,
            "result": "success" if result.ok else "failure",
        },
    )
    db.commit()
    return result


def _test_oci_connection(account, db: Session, actor: User) -> ConnectionTestResult:
    configuration = require_oci_configuration(account)
    account_id = account.id
    expected_revision = configuration.configuration_revision

    try:
        snapshot = resolve_oci_signing_credentials(db, account.id)
    except OciConnectionError as exc:
        tested_at = datetime.now(UTC)
        db.rollback()
        return _persist_oci_test_result(
            db,
            account_id=account_id,
            expected_revision=expected_revision,
            actor=actor,
            tested_at=tested_at,
            error=exc,
            verified_checks=(),
        )

    db.commit()
    try:
        validation = validate_connection(snapshot)
        remote_error = None
        checks = validation.verified_checks
    except OciConnectionError as exc:
        remote_error = exc
        checks = ()

    return _persist_oci_test_result(
        db,
        account_id=account_id,
        expected_revision=expected_revision,
        actor=actor,
        tested_at=datetime.now(UTC),
        error=remote_error,
        verified_checks=checks,
    )


@router.post("/{account_id}/test-connection", response_model=ConnectionTestResult)
def test_connection(
    account_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> ConnectionTestResult:
    account = _get_account(db, account_id)
    try:
        require_provider_operation(account.provider, ProviderOperation.CONNECTION_TEST)
    except UnsupportedProviderOperation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if account.provider == CloudProvider.AWS.value:
        return _test_aws_connection(account, db, actor)
    if account.provider == CloudProvider.OCI.value:
        return _test_oci_connection(account, db, actor)
    raise HTTPException(
        status_code=409,
        detail=f"Provider {account.provider} does not have a connection test in this stage",
    )
