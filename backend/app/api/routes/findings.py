from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.finding import Finding
from app.schemas.finding import FindingRead, FindingStatusUpdate
from app.services.ai import AIProviderError, explain_finding

router = APIRouter(prefix="/findings", tags=["findings"], dependencies=[Depends(require_admin)])

ALLOWED_STATUSES = {"open", "accepted", "dismissed", "resolved"}


@router.get("", response_model=list[FindingRead])
def list_findings(
    account_id: int | None = None,
    rule_key: str | None = None,
    finding_status: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Finding]:
    statement = select(Finding).order_by(
        Finding.estimated_monthly_savings.desc(), Finding.last_seen_at.desc()
    )
    if account_id is not None:
        statement = statement.where(Finding.account_id == account_id)
    if rule_key:
        statement = statement.where(Finding.rule_key == rule_key)
    if finding_status:
        statement = statement.where(Finding.status == finding_status)
    return list(db.scalars(statement.limit(limit)))


@router.patch("/{finding_id}/status", response_model=FindingRead)
def update_finding_status(
    finding_id: str, payload: FindingStatusUpdate, db: Session = Depends(get_db)
) -> Finding:
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported finding status")
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    finding.status = payload.status
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/{finding_id}/explain")
def explain_finding_with_ai(finding_id: str, db: Session = Depends(get_db)) -> dict:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    try:
        explanation = explain_finding(finding)
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"finding_id": finding.id, "provider": "bedrock", "explanation": explanation}
