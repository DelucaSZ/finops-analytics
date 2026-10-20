from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cloud import CloudProvider
from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.policy import Policy
from app.models.user import User
from app.schemas.policy import PolicyRead, PolicyUpdate
from app.services.audit import AuditService, audit_snapshot
from app.services.policies import (
    RULES,
    get_effective_policy,
    get_policy_row,
    list_effective_policies,
    upsert_policy,
)
from app.services.provider_capabilities import (
    ProviderOperation,
    UnsupportedProviderOperation,
    require_provider_operation,
)

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_user)])


def _validate_rule(rule_key: str) -> None:
    if rule_key not in RULES:
        raise HTTPException(status_code=404, detail="Rule not found")


def _validate_account(db: Session, account_id: int) -> None:
    account = db.get(AwsAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="AWS account not found")
    cloud_account = account.cloud_account
    if cloud_account is None or cloud_account.provider != CloudProvider.AWS.value:
        raise HTTPException(status_code=409, detail="AWS account configuration is invalid")
    try:
        require_provider_operation(cloud_account.provider, ProviderOperation.FINOPS_POLICIES)
    except UnsupportedProviderOperation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _policy_snapshot(
    row: Policy | None,
    *,
    rule_key: str,
    scope: str,
    account_id: int | None,
) -> dict:
    return audit_snapshot(
        {
            "rule_key": rule_key,
            "scope": scope,
            "account_id": account_id,
            "override_exists": row is not None,
            "enabled": row.enabled if row is not None else None,
            "config": row.config if row is not None else {},
        }
    )


def _policy_entity_id(rule_key: str, scope: str, account_id: int | None) -> str:
    return f"{scope}:{account_id}:{rule_key}" if account_id is not None else f"{scope}:{rule_key}"


def _record_policy_change(
    db: Session,
    *,
    actor: User,
    rule_key: str,
    scope: str,
    account_id: int | None,
    before: dict,
    after: dict,
    action: str,
) -> None:
    AuditService.record(
        db,
        actor=actor,
        module="policies",
        action=action,
        entity_type="policy",
        entity_id=_policy_entity_id(rule_key, scope, account_id),
        entity_label=RULES[rule_key].name,
        before=before,
        after=after,
        source="API",
        metadata={"scope": scope, "account_id": account_id},
    )


def _update_action(before: dict, after: dict) -> str:
    changed = [
        key for key in ("override_exists", "enabled", "config") if before.get(key) != after.get(key)
    ]
    if changed == ["enabled"]:
        return "policy.enable" if after.get("enabled") else "policy.disable"
    return "policy.update"


@router.get("/global", response_model=list[PolicyRead])
def global_policies(db: Session = Depends(get_db)) -> list[dict]:
    return list_effective_policies(db)


@router.put("/global/{rule_key}", response_model=PolicyRead)
def update_global_policy(
    rule_key: str,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    _validate_rule(rule_key)
    before = _policy_snapshot(
        get_policy_row(db, rule_key, "global"),
        rule_key=rule_key,
        scope="global",
        account_id=None,
    )
    row = upsert_policy(
        db,
        rule_key=rule_key,
        scope="global",
        account_id=None,
        enabled=payload.enabled,
        config=payload.config,
        commit=False,
    )
    after = _policy_snapshot(row, rule_key=rule_key, scope="global", account_id=None)
    if before != after:
        _record_policy_change(
            db,
            actor=actor,
            rule_key=rule_key,
            scope="global",
            account_id=None,
            before=before,
            after=after,
            action=_update_action(before, after),
        )
    db.commit()
    return get_effective_policy(db, rule_key)


@router.delete("/global/{rule_key}", status_code=status.HTTP_204_NO_CONTENT)
def reset_global_policy(
    rule_key: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    _validate_rule(rule_key)
    row = get_policy_row(db, rule_key, "global")
    if row:
        before = _policy_snapshot(row, rule_key=rule_key, scope="global", account_id=None)
        db.delete(row)
        after = _policy_snapshot(None, rule_key=rule_key, scope="global", account_id=None)
        _record_policy_change(
            db,
            actor=actor,
            rule_key=rule_key,
            scope="global",
            account_id=None,
            before=before,
            after=after,
            action="policy.reset",
        )
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
    actor: User = Depends(require_admin),
) -> dict:
    _validate_rule(rule_key)
    _validate_account(db, account_id)
    before = _policy_snapshot(
        get_policy_row(db, rule_key, "account", account_id),
        rule_key=rule_key,
        scope="account",
        account_id=account_id,
    )
    row = upsert_policy(
        db,
        rule_key=rule_key,
        scope="account",
        account_id=account_id,
        enabled=payload.enabled,
        config=payload.config,
        commit=False,
    )
    after = _policy_snapshot(row, rule_key=rule_key, scope="account", account_id=account_id)
    if before != after:
        _record_policy_change(
            db,
            actor=actor,
            rule_key=rule_key,
            scope="account",
            account_id=account_id,
            before=before,
            after=after,
            action=_update_action(before, after),
        )
    db.commit()
    return get_effective_policy(db, rule_key, account_id)


@router.delete("/accounts/{account_id}/{rule_key}", status_code=status.HTTP_204_NO_CONTENT)
def reset_account_policy(
    account_id: int,
    rule_key: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    _validate_rule(rule_key)
    _validate_account(db, account_id)
    row = get_policy_row(db, rule_key, "account", account_id)
    if row:
        before = _policy_snapshot(row, rule_key=rule_key, scope="account", account_id=account_id)
        db.delete(row)
        after = _policy_snapshot(None, rule_key=rule_key, scope="account", account_id=account_id)
        _record_policy_change(
            db,
            actor=actor,
            rule_key=rule_key,
            scope="account",
            account_id=account_id,
            before=before,
            after=after,
            action="policy.reset",
        )
        db.commit()
