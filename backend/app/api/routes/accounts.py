import uuid
from datetime import UTC, datetime, timedelta

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.account import AwsAccount
from app.schemas.account import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    ConnectionTestResult,
)
from app.services.aws_auth import assume_account_session, get_caller_identity

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(require_user)])


def _get_account(db: Session, account_id: int) -> AwsAccount:
    account = db.get(AwsAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="AWS account not found")
    return account


@router.get("/external-id", dependencies=[Depends(require_admin)])
def generate_external_id() -> dict[str, str]:
    return {"external_id": f"nuvemiq-{uuid.uuid4()}"}


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)) -> list[AwsAccount]:
    return list(db.scalars(select(AwsAccount).order_by(AwsAccount.name)))


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> AwsAccount:
    role_account_id = payload.role_arn.split(":")[4]
    if role_account_id != payload.aws_account_id:
        raise HTTPException(status_code=422, detail="Role ARN account does not match Account ID")
    account = AwsAccount(**payload.model_dump())
    if account.schedule_enabled:
        account.next_scan_at = datetime.now(UTC)
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="AWS account is already registered") from exc
    db.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)) -> AwsAccount:
    return _get_account(db, account_id)


@router.patch("/{account_id}", response_model=AccountRead, dependencies=[Depends(require_admin)])
def update_account(
    account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)
) -> AwsAccount:
    account = _get_account(db, account_id)
    changes = payload.model_dump(exclude_unset=True)
    role_arn = changes.get("role_arn")
    if role_arn and role_arn.split(":")[4] != account.aws_account_id:
        raise HTTPException(status_code=422, detail="Role ARN account does not match Account ID")
    for field, value in changes.items():
        setattr(account, field, value)
    if changes.get("schedule_enabled") is True and account.next_scan_at is None:
        account.next_scan_at = datetime.now(UTC)
    if changes.get("schedule_enabled") is False:
        account.next_scan_at = None
    if account.schedule_enabled and "scan_interval_hours" in changes:
        account.next_scan_at = datetime.now(UTC) + timedelta(hours=account.scan_interval_hours)
    db.commit()
    db.refresh(account)
    return account


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = _get_account(db, account_id)
    db.delete(account)
    db.commit()


@router.post(
    "/{account_id}/test-connection",
    response_model=ConnectionTestResult,
    dependencies=[Depends(require_admin)],
)
def test_connection(account_id: int, db: Session = Depends(get_db)) -> ConnectionTestResult:
    account = _get_account(db, account_id)
    account.last_connection_test_at = datetime.now(UTC)
    try:
        identity = get_caller_identity(assume_account_session(account))
        if identity.account_id != account.aws_account_id:
            raise ValueError(
                f"Expected account {account.aws_account_id}, received {identity.account_id}"
            )
        account.connection_status = "connected"
        account.last_error = None
        result = ConnectionTestResult(
            ok=True,
            expected_account_id=account.aws_account_id,
            caller_account_id=identity.account_id,
            caller_arn=identity.arn,
        )
    except (BotoCoreError, ClientError, ValueError) as exc:
        account.connection_status = "error"
        account.last_error = str(exc)[:2000]
        result = ConnectionTestResult(
            ok=False,
            expected_account_id=account.aws_account_id,
            error=account.last_error,
        )
    db.commit()
    return result
