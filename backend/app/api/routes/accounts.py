import uuid
from datetime import UTC, datetime

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
from app.services.cloud_accounts import (
    create_legacy_aws_account,
    delete_cloud_account,
    set_connection_state,
    update_legacy_aws_account,
)
from app.services.collection_errors import sanitize_collection_error

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
    try:
        account = create_legacy_aws_account(db, payload)
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
    try:
        update_legacy_aws_account(db, account, payload)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.refresh(account)
    return account


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = _get_account(db, account_id)
    if account.cloud_account is None:
        raise HTTPException(status_code=409, detail="AWS account is missing its cloud account")
    delete_cloud_account(db, account.cloud_account)
    db.commit()


@router.post(
    "/{account_id}/test-connection",
    response_model=ConnectionTestResult,
    dependencies=[Depends(require_admin)],
)
def test_connection(account_id: int, db: Session = Depends(get_db)) -> ConnectionTestResult:
    account = _get_account(db, account_id)
    cloud_account = account.cloud_account
    if cloud_account is None:
        raise HTTPException(status_code=409, detail="AWS account is missing its cloud account")

    tested_at = datetime.now(UTC)
    expected_account_id = cloud_account.native_account_id
    try:
        identity = get_caller_identity(assume_account_session(account))
        if identity.account_id != expected_account_id:
            raise ValueError(
                f"Expected account {expected_account_id}, received {identity.account_id}"
            )
        set_connection_state(
            cloud_account,
            status="connected",
            tested_at=tested_at,
            error=None,
        )
        result = ConnectionTestResult(
            ok=True,
            expected_account_id=expected_account_id,
            caller_account_id=identity.account_id,
            caller_arn=identity.arn,
        )
    except (BotoCoreError, ClientError, ValueError) as exc:
        error = sanitize_collection_error(exc)[:2000]
        set_connection_state(
            cloud_account,
            status="error",
            tested_at=tested_at,
            error=error,
        )
        result = ConnectionTestResult(
            ok=False,
            expected_account_id=expected_account_id,
            error=error,
        )
    db.commit()
    return result
