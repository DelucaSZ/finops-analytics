from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.cloud import CloudProvider, normalize_provider, validate_native_account_id
from app.models.account import AwsAccount, CloudAccount
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AwsAccountConfigurationCreate,
    AwsAccountConfigurationUpdate,
    CloudAccountCreate,
    CloudAccountUpdate,
)


class UnsupportedProviderOperation(ValueError):
    pass


def list_cloud_accounts(db: Session) -> list[CloudAccount]:
    return list(
        db.scalars(
            select(CloudAccount)
            .options(selectinload(CloudAccount.aws_configuration))
            .order_by(CloudAccount.name, CloudAccount.id)
        )
    )


def get_cloud_account(db: Session, cloud_account_id: int) -> CloudAccount | None:
    return db.scalar(
        select(CloudAccount)
        .options(selectinload(CloudAccount.aws_configuration))
        .where(CloudAccount.id == cloud_account_id)
    )


def require_aws_configuration(account: CloudAccount) -> AwsAccount:
    if account.provider != CloudProvider.AWS.value or account.aws_configuration is None:
        raise UnsupportedProviderOperation(
            f"Provider {account.provider} does not have an AWS operational configuration"
        )
    return account.aws_configuration


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


def create_cloud_account(db: Session, payload: CloudAccountCreate) -> CloudAccount:
    provider = normalize_provider(payload.provider)
    native_account_id = validate_native_account_id(provider, payload.native_account_id)
    if provider != CloudProvider.AWS.value:
        raise UnsupportedProviderOperation(
            f"Provider {provider} account registration is not supported in this stage"
        )
    if payload.configuration is None:
        raise ValueError("AWS configuration is required")

    cloud_account = CloudAccount(
        provider=provider,
        native_account_id=native_account_id,
        name=payload.name,
        enabled=payload.enabled,
    )
    _create_aws_configuration(cloud_account, payload.configuration)
    db.add(cloud_account)
    db.flush()
    return cloud_account


def update_cloud_account(
    db: Session,
    account: CloudAccount,
    payload: CloudAccountUpdate,
) -> CloudAccount:
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        account.name = changes["name"]
    if "enabled" in changes:
        account.enabled = changes["enabled"]

    configuration_changes = changes.get("configuration")
    if configuration_changes is not None:
        aws_account = require_aws_configuration(account)
        if "role_arn" in configuration_changes:
            role_account_id = configuration_changes["role_arn"].split(":")[4]
            if role_account_id != account.native_account_id:
                raise ValueError("Role ARN account does not match native account identifier")
        for field, value in configuration_changes.items():
            setattr(aws_account, field, value)
        _apply_schedule(aws_account, configuration_changes)

    db.flush()
    return account


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


def delete_cloud_account(db: Session, account: CloudAccount) -> None:
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
