import uuid
from datetime import UTC, datetime

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.schemas.account import (
    CloudAccountCreate,
    CloudAccountRead,
    CloudAccountUpdate,
    ConnectionTestResult,
)
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.cloud_accounts import (
    UnsupportedProviderOperation,
    create_cloud_account,
    delete_cloud_account,
    get_cloud_account,
    list_cloud_accounts,
    require_aws_configuration,
    set_connection_state,
    update_cloud_account,
)
from app.services.collection_errors import sanitize_collection_error

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


@router.get("/aws/external-id", dependencies=[Depends(require_admin)])
def generate_aws_external_id() -> dict[str, str]:
    return {"external_id": f"nuvemiq-{uuid.uuid4()}"}


@router.get("", response_model=list[CloudAccountRead])
def list_accounts(db: Session = Depends(get_db)):
    return list_cloud_accounts(db)


@router.post(
    "",
    response_model=CloudAccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_account(payload: CloudAccountCreate, db: Session = Depends(get_db)):
    try:
        account = create_cloud_account(db, payload)
        account_id = account.id
        db.commit()
        return get_cloud_account(db, account_id)
    except UnsupportedProviderOperation as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this provider and native identifier is already registered",
        ) from exc


@router.get("/{account_id}", response_model=CloudAccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    return _get_account(db, account_id)


@router.patch(
    "/{account_id}",
    response_model=CloudAccountRead,
    dependencies=[Depends(require_admin)],
)
def update_account(
    account_id: int,
    payload: CloudAccountUpdate,
    db: Session = Depends(get_db),
):
    account = _get_account(db, account_id)
    try:
        update_cloud_account(db, account, payload)
        db.commit()
        return get_cloud_account(db, account_id)
    except (UnsupportedProviderOperation, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Account update conflicts with existing data",
        ) from exc


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = _get_account(db, account_id)
    delete_cloud_account(db, account)
    db.commit()


@router.post(
    "/{account_id}/test-connection",
    response_model=ConnectionTestResult,
    dependencies=[Depends(require_admin)],
)
def test_connection(account_id: int, db: Session = Depends(get_db)) -> ConnectionTestResult:
    account = _get_account(db, account_id)
    try:
        aws_account = require_aws_configuration(account)
    except UnsupportedProviderOperation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    tested_at = datetime.now(UTC)
    expected_account_id = account.native_account_id
    try:
        identity = get_caller_identity(assume_account_session(aws_account))
        if identity.account_id != expected_account_id:
            raise ValueError(
                f"Expected account {expected_account_id}, received {identity.account_id}"
            )
        set_connection_state(
            account,
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
            account,
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
