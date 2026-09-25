from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_operator, require_user
from app.db.session import get_db
from app.models.finding import Finding
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.schemas.finding import (
    FindingRead,
    LegacyOpportunityStatus,
    OpportunityBulkAction,
    OpportunityBulkStatus,
    OpportunityNote,
    OpportunityReject,
)
from app.services.ai import AIProviderError, explain_finding
from app.services.opportunity_lifecycle import (
    bulk_set_legacy_status,
    bulk_transition,
    reject,
    reopen,
    set_legacy_status,
    treat,
)

router = APIRouter(
    prefix="/findings",
    tags=["findings"],
    dependencies=[Depends(require_user)],
)
ALLOWED_STATUSES = {"open", "treated", "rejected"}


@router.get("", response_model=list[FindingRead])
def list_findings(
    account_id: int | None = None,
    rule_key: str | None = None,
    finding_status: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Finding]:
    if finding_status and finding_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported opportunity status")
    statement = select(Finding).order_by(
        Finding.estimated_monthly_savings.desc(),
        Finding.last_seen_at.desc(),
        Finding.id,
    )
    if account_id is not None:
        statement = statement.where(Finding.account_id == account_id)
    if rule_key:
        statement = statement.where(Finding.rule_key == rule_key)
    if finding_status:
        statement = statement.where(Finding.status == finding_status)
    return list(db.scalars(statement.offset(offset).limit(limit)))


@router.post(
    "/{finding_id}/treat",
    response_model=FindingRead,
    dependencies=[Depends(require_operator)],
)
def treat_finding(
    finding_id: str,
    payload: OpportunityNote,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> Finding:
    finding = treat(db, finding_id, actor, payload.note)
    db.commit()
    db.refresh(finding)
    return finding


@router.post(
    "/{finding_id}/reject",
    response_model=FindingRead,
    dependencies=[Depends(require_operator)],
)
def reject_finding(
    finding_id: str,
    payload: OpportunityReject,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> Finding:
    finding = reject(db, finding_id, actor, payload.reason, payload.note)
    db.commit()
    db.refresh(finding)
    return finding


@router.post(
    "/{finding_id}/reopen",
    response_model=FindingRead,
    dependencies=[Depends(require_operator)],
)
def reopen_finding(
    finding_id: str,
    payload: OpportunityNote,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> Finding:
    finding = reopen(db, finding_id, actor, payload.note)
    db.commit()
    db.refresh(finding)
    return finding


def _bulk_action(
    payload: OpportunityBulkAction,
    db: Session,
    actor: User,
) -> dict:
    ids = list(dict.fromkeys(payload.finding_ids))
    try:
        findings = bulk_transition(
            db,
            ids,
            actor,
            action=payload.action,
            reason=payload.reason,
            note=payload.note,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "requested_count": len(ids),
        "updated_count": len(findings),
        "updated_ids": [finding.id for finding in findings],
    }


@router.post("/bulk/action", dependencies=[Depends(require_operator)])
@router.patch("/bulk/action", dependencies=[Depends(require_operator)])
def bulk_action(
    payload: OpportunityBulkAction,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _bulk_action(payload, db, actor)


@router.patch("/bulk/status", dependencies=[Depends(require_operator)])
def legacy_bulk_status(
    payload: OpportunityBulkAction | OpportunityBulkStatus,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    if isinstance(payload, OpportunityBulkAction):
        return _bulk_action(payload, db, actor)

    ids = list(dict.fromkeys(payload.finding_ids))
    try:
        findings = bulk_set_legacy_status(
            db,
            ids,
            actor,
            status=payload.status,
            reason=payload.reason,
            note=payload.note,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "requested_count": len(ids),
        "updated_count": len(findings),
        "updated_ids": [finding.id for finding in findings],
    }


@router.patch(
    "/{finding_id}/status",
    response_model=FindingRead,
    dependencies=[Depends(require_operator)],
)
def legacy_status(
    finding_id: str,
    payload: LegacyOpportunityStatus,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> Finding:
    try:
        finding = set_legacy_status(
            db,
            finding_id,
            actor,
            status=payload.status,
            reason=payload.reason,
            note=payload.note,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(finding)
    return finding


@router.get("/{finding_id}/history")
def finding_history(finding_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Finding, finding_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    rows = list(
        db.scalars(
            select(OpportunityStatusHistory)
            .where(OpportunityStatusHistory.opportunity_id == finding_id)
            .order_by(OpportunityStatusHistory.changed_at.desc())
        )
    )
    return [
        {
            "id": item.id,
            "from_status": item.from_status,
            "to_status": item.to_status,
            "action": item.action,
            "reason": item.reason,
            "note": item.note,
            "changed_by": item.changed_by,
            "changed_at": item.changed_at,
        }
        for item in rows
    ]


@router.post("/{finding_id}/explain", dependencies=[Depends(require_operator)])
def explain_finding_with_ai(
    finding_id: str,
    db: Session = Depends(get_db),
) -> dict:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    try:
        explanation = explain_finding(finding)
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"finding_id": finding.id, "provider": "bedrock", "explanation": explanation}
