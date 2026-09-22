from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.account import AwsAccount
from app.schemas.policy import PolicyRead, PolicyUpdate
from app.services.policies import (
    RULES,
    get_effective_policy,
    get_policy_row,
    list_effective_policies,
    upsert_policy,
)

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_admin)])


def _validate_rule(rule_key: str) -> None:
    if rule_key not in RULES:
        raise HTTPException(status_code=404, detail="Rule not found")


def _validate_account(db: Session, account_id: int) -> None:
    if db.get(AwsAccount, account_id) is None:
        raise HTTPException(status_code=404, detail="AWS account not found")


@router.get("/global", response_model=list[PolicyRead])
def global_policies(db: Session = Depends(get_db)) -> list[dict]:
    return list_effective_policies(db)


@router.put("/global/{rule_key}", response_model=PolicyRead)
def update_global_policy(
    rule_key: str, payload: PolicyUpdate, db: Session = Depends(get_db)
) -> dict:
    _validate_rule(rule_key)
    upsert_policy(
        db,
        rule_key=rule_key,
        scope="global",
        account_id=None,
        enabled=payload.enabled,
        config=payload.config,
    )
    return get_effective_policy(db, rule_key)


@router.delete("/global/{rule_key}", status_code=status.HTTP_204_NO_CONTENT)
def reset_global_policy(rule_key: str, db: Session = Depends(get_db)) -> None:
    _validate_rule(rule_key)
    row = get_policy_row(db, rule_key, "global")
    if row:
        db.delete(row)
        db.commit()


@router.get("/accounts/{account_id}", response_model=list[PolicyRead])
def account_policies(account_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _validate_account(db, account_id)
    return list_effective_policies(db, account_id)


@router.put("/accounts/{account_id}/{rule_key}", response_model=PolicyRead)
def update_account_policy(
    account_id: int,
    rule_key: str,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
) -> dict:
    _validate_rule(rule_key)
    _validate_account(db, account_id)
    upsert_policy(
        db,
        rule_key=rule_key,
        scope="account",
        account_id=account_id,
        enabled=payload.enabled,
        config=payload.config,
    )
    return get_effective_policy(db, rule_key, account_id)


@router.delete("/accounts/{account_id}/{rule_key}", status_code=status.HTTP_204_NO_CONTENT)
def reset_account_policy(account_id: int, rule_key: str, db: Session = Depends(get_db)) -> None:
    _validate_rule(rule_key)
    _validate_account(db, account_id)
    row = get_policy_row(db, rule_key, "account", account_id)
    if row:
        db.delete(row)
        db.commit()
