from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.finding import Finding
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.audit import AuditService, audit_snapshot, new_correlation_id
from app.services.dashboard_aggregation import refresh_summaries_for_findings
from app.services.opportunity_saving_recognition import OpportunitySavingRecognitionService

OPEN = "open"
TREATED = "treated"
REJECTED = "rejected"
REJECTION_REASONS = {
    "FALSE_POSITIVE",
    "OPERATIONAL_EXCEPTION",
    "ACCEPTABLE_COST",
    "RESOURCE_REQUIRED",
    "RISK_ACCEPTED",
    "OTHER",
}


def _locked(db: Session, opportunity_id: str) -> Finding:
    finding = db.scalar(
        select(Finding).where(Finding.id == opportunity_id).with_for_update()
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return finding


def _audit_snapshot(finding: Finding) -> dict:
    return audit_snapshot(
        {
            "status": finding.status,
            "rejection_reason": finding.rejection_reason,
            "needs_review": finding.needs_review,
        }
    )


def _audit_label(finding: Finding) -> str:
    resource = finding.resource_name or finding.resource_id
    return f"{finding.title} · {resource}"


def _record_lifecycle_audit(
    db: Session,
    *,
    finding: Finding,
    actor: User,
    action: str,
    before: dict,
    metadata: dict | None = None,
) -> None:
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action=f"opportunity.{action}",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_audit_label(finding),
        before=before,
        after=_audit_snapshot(finding),
        source="API",
        metadata=metadata,
    )


def _history(
    db: Session,
    finding: Finding,
    actor: User,
    *,
    to_status: str,
    action: str,
    reason: str | None = None,
    note: str | None = None,
) -> OpportunityStatusHistory:
    event = OpportunityStatusHistory(
        opportunity_id=finding.id,
        from_status=finding.status,
        to_status=to_status,
        action=action,
        reason=reason,
        note=note,
        changed_by=actor.id,
        changed_at=utcnow(),
    )
    db.add(event)
    return event


def _apply_treat(
    db: Session,
    finding: Finding,
    actor: User,
    note: str | None,
) -> OpportunityStatusHistory:
    if finding.status != OPEN:
        raise HTTPException(status_code=409, detail="Only open opportunities can be treated")
    event = _history(db, finding, actor, to_status=TREATED, action="treat", note=note)
    finding.status = TREATED
    finding.treated_at = event.changed_at
    finding.treated_by = actor.id
    finding.treatment_note = note
    finding.needs_review = False
    return event


def _apply_reject(
    db: Session,
    finding: Finding,
    actor: User,
    reason: str,
    note: str | None,
) -> None:
    if finding.status != OPEN:
        raise HTTPException(status_code=409, detail="Only open opportunities can be rejected")
    _history(db, finding, actor, to_status=REJECTED, action="reject", reason=reason, note=note)
    finding.status = REJECTED
    finding.rejected_at = utcnow()
    finding.rejected_by = actor.id
    finding.rejection_reason = reason
    finding.rejection_note = note
    finding.needs_review = False


def _apply_reopen(db: Session, finding: Finding, actor: User, note: str | None) -> None:
    if finding.status not in {TREATED, REJECTED}:
        raise HTTPException(
            status_code=409,
            detail="Only treated or rejected opportunities can be reopened",
        )
    _history(db, finding, actor, to_status=OPEN, action="reopen", note=note)
    finding.status = OPEN
    finding.needs_review = False


def _recognize_treatments(
    db: Session,
    candidates: list[tuple[Finding, OpportunityStatusHistory]],
    actor: User,
) -> None:
    if not candidates:
        return
    db.flush()
    OpportunitySavingRecognitionService(db).recognize_many(candidates, actor)


def treat(
    db: Session,
    opportunity_id: str,
    actor: User,
    note: str | None = None,
) -> Finding:
    finding = _locked(db, opportunity_id)
    before = _audit_snapshot(finding)
    event = _apply_treat(db, finding, actor, note)
    _recognize_treatments(db, [(finding, event)], actor)
    refresh_summaries_for_findings(db, [finding])
    _record_lifecycle_audit(db, finding=finding, actor=actor, action="treat", before=before)
    return finding


def reject(
    db: Session,
    opportunity_id: str,
    actor: User,
    reason: str,
    note: str | None = None,
) -> Finding:
    _validate_rejection(reason, note)
    finding = _locked(db, opportunity_id)
    before = _audit_snapshot(finding)
    _apply_reject(db, finding, actor, reason, note)
    refresh_summaries_for_findings(db, [finding])
    _record_lifecycle_audit(
        db,
        finding=finding,
        actor=actor,
        action="reject",
        before=before,
        metadata={"reason": reason},
    )
    return finding


def reopen(
    db: Session,
    opportunity_id: str,
    actor: User,
    note: str | None = None,
) -> Finding:
    finding = _locked(db, opportunity_id)
    before = _audit_snapshot(finding)
    _apply_reopen(db, finding, actor, note)
    refresh_summaries_for_findings(db, [finding])
    _record_lifecycle_audit(db, finding=finding, actor=actor, action="reopen", before=before)
    return finding


def _validate_rejection(reason: str | None, note: str | None) -> None:
    if reason not in REJECTION_REASONS:
        raise HTTPException(status_code=422, detail="Unsupported rejection reason")
    if reason == "OTHER" and not (note or "").strip():
        raise HTTPException(status_code=422, detail="A note is required for OTHER")


def bulk_transition(
    db: Session,
    opportunity_ids: list[str],
    actor: User,
    *,
    action: str,
    reason: str | None = None,
    note: str | None = None,
) -> list[Finding]:
    ids = list(dict.fromkeys(opportunity_ids))
    if action == "reject":
        _validate_rejection(reason, note)
    if action not in {"treat", "reject", "reopen"}:
        raise HTTPException(status_code=422, detail="Unsupported opportunity action")

    findings = list(
        db.scalars(
            select(Finding).where(Finding.id.in_(ids)).order_by(Finding.id).with_for_update()
        )
    )
    by_id = {finding.id: finding for finding in findings}
    missing = [opportunity_id for opportunity_id in ids if opportunity_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Uma ou mais oportunidades não existem.")

    ordered = [by_id[opportunity_id] for opportunity_id in ids]
    treatment_candidates: list[tuple[Finding, OpportunityStatusHistory]] = []
    for finding in ordered:
        if action == "treat":
            event = _apply_treat(db, finding, actor, note)
            treatment_candidates.append((finding, event))
        elif action == "reject":
            _apply_reject(db, finding, actor, reason or "", note)
        else:
            _apply_reopen(db, finding, actor, note)
    _recognize_treatments(db, treatment_candidates, actor)
    refresh_summaries_for_findings(db, ordered)

    correlation_id = new_correlation_id()
    sample_ids = [finding.id for finding in ordered[:20]]
    metadata = {
        "requested": len(ids),
        "updated": len(ordered),
        "sample_ids": sample_ids,
        "ids_truncated": len(ordered) > len(sample_ids),
    }
    if reason:
        metadata["reason"] = reason
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action=f"opportunity.bulk_{action}",
        entity_type="opportunity_bulk",
        entity_label=f"{len(ordered)} oportunidades",
        source="API",
        metadata=metadata,
        correlation_id=correlation_id,
    )
    return ordered


def _legacy_target(status: str) -> str:
    return {
        "accepted": TREATED,
        "treated": TREATED,
        "dismissed": REJECTED,
        "rejected": REJECTED,
        "open": OPEN,
    }[status]


def _apply_legacy_status(
    db: Session,
    finding: Finding,
    actor: User,
    *,
    status: str,
    reason: str | None = None,
    note: str | None = None,
) -> OpportunityStatusHistory | None:
    target = _legacy_target(status)
    if finding.status == target:
        return None
    if target == OPEN:
        _apply_reopen(db, finding, actor, note)
        return None
    if target == TREATED:
        return _apply_treat(db, finding, actor, note)

    rejection_reason = reason
    rejection_note = note
    if rejection_reason is None:
        rejection_reason = "OTHER"
        rejection_note = rejection_note or "Legacy status update did not provide a rejection reason."
    _validate_rejection(rejection_reason, rejection_note)
    _apply_reject(db, finding, actor, rejection_reason, rejection_note)
    return None


def set_legacy_status(
    db: Session,
    opportunity_id: str,
    actor: User,
    *,
    status: str,
    reason: str | None = None,
    note: str | None = None,
) -> Finding:
    finding = _locked(db, opportunity_id)
    before = _audit_snapshot(finding)
    event = _apply_legacy_status(db, finding, actor, status=status, reason=reason, note=note)
    if event is not None:
        _recognize_treatments(db, [(finding, event)], actor)
    refresh_summaries_for_findings(db, [finding])
    if before != _audit_snapshot(finding):
        target = _legacy_target(status)
        action = (
            "reopen" if target == OPEN else "treat" if target == TREATED else "reject"
        )
        metadata = {"reason": reason} if reason else None
        _record_lifecycle_audit(
            db,
            finding=finding,
            actor=actor,
            action=action,
            before=before,
            metadata=metadata,
        )
    return finding


def bulk_set_legacy_status(
    db: Session,
    opportunity_ids: list[str],
    actor: User,
    *,
    status: str,
    reason: str | None = None,
    note: str | None = None,
) -> list[Finding]:
    ids = list(dict.fromkeys(opportunity_ids))
    findings = list(
        db.scalars(
            select(Finding).where(Finding.id.in_(ids)).order_by(Finding.id).with_for_update()
        )
    )
    by_id = {finding.id: finding for finding in findings}
    missing = [opportunity_id for opportunity_id in ids if opportunity_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Uma ou mais oportunidades não existem.")

    ordered = [by_id[opportunity_id] for opportunity_id in ids]
    treatment_candidates: list[tuple[Finding, OpportunityStatusHistory]] = []
    for finding in ordered:
        event = _apply_legacy_status(
            db,
            finding,
            actor,
            status=status,
            reason=reason,
            note=note,
        )
        if event is not None:
            treatment_candidates.append((finding, event))
    _recognize_treatments(db, treatment_candidates, actor)
    refresh_summaries_for_findings(db, ordered)
    target = _legacy_target(status)
    action = "reopen" if target == OPEN else "treat" if target == TREATED else "reject"
    sample_ids = [finding.id for finding in ordered[:20]]
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action=f"opportunity.bulk_{action}",
        entity_type="opportunity_bulk",
        entity_label=f"{len(ordered)} oportunidades",
        source="API",
        metadata={
            "requested": len(ids),
            "updated": len(ordered),
            "sample_ids": sample_ids,
            "ids_truncated": len(ordered) > len(sample_ids),
            **({"reason": reason} if reason else {}),
        },
        correlation_id=new_correlation_id(),
    )
    return ordered
