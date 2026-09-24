from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_operator, require_user
from app.db.session import get_db
from app.models.finding import Finding
from app.schemas.finding import FindingBulkStatusUpdate, FindingRead, FindingStatusUpdate
from app.services.ai import AIProviderError, explain_finding

router = APIRouter(prefix="/findings", tags=["findings"], dependencies=[Depends(require_user)])

ALLOWED_STATUSES = {"open", "accepted", "dismissed", "resolved"}


@router.get("", response_model=list[FindingRead])
def list_findings(
    account_id: int | None = None,
    rule_key: str | None = None,
    finding_status: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Finding]:
    statement = select(Finding).order_by(
        Finding.estimated_monthly_savings.desc(), Finding.last_seen_at.desc(), Finding.id
    )
    if account_id is not None:
        statement = statement.where(Finding.account_id == account_id)
    if rule_key:
        statement = statement.where(Finding.rule_key == rule_key)
    if finding_status:
        statement = statement.where(Finding.status == finding_status)
    return list(db.scalars(statement.offset(offset).limit(limit)))


@router.patch("/bulk/status", dependencies=[Depends(require_operator)])
def update_findings_status(payload: FindingBulkStatusUpdate, db: Session = Depends(get_db)) -> dict:
    finding_ids = list(dict.fromkeys(payload.finding_ids))
    findings = list(
        db.scalars(
            select(Finding)
            .where(Finding.id.in_(finding_ids))
            .order_by(Finding.id)
            .with_for_update()
        )
    )
    if len(findings) != len(finding_ids):
        raise HTTPException(
            status_code=404, detail="Uma ou mais oportunidades não existem. Recarregue a página."
        )
    if any(finding.status != "open" for finding in findings):
        raise HTTPException(
            status_code=409,
            detail="Uma ou mais oportunidades já foram tratadas. Recarregue a página.",
        )
    for finding in findings:
        finding.status = payload.status
    db.commit()
    return {"updated_ids": finding_ids, "updated_count": len(finding_ids)}


@router.patch(
    "/{finding_id}/status", response_model=FindingRead, dependencies=[Depends(require_operator)]
)
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


@router.post("/{finding_id}/explain", dependencies=[Depends(require_operator)])
def explain_finding_with_ai(finding_id: str, db: Session = Depends(get_db)) -> dict:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    try:
        explanation = explain_finding(finding)
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"finding_id": finding.id, "provider": "bedrock", "explanation": explanation}
