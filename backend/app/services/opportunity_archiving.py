from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_archive_history import (
    OpportunityArchiveAction,
    OpportunityArchiveHistory,
    OpportunityArchiveReason,
)
from app.models.user import User
from app.services.dashboard_aggregation import refresh_summaries_for_findings


def _locked(db: Session, opportunity_id: str) -> Finding:
    finding = db.scalar(select(Finding).where(Finding.id == opportunity_id).with_for_update())
    if finding is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return finding


def _history(
    db: Session,
    finding: Finding,
    *,
    action: OpportunityArchiveAction,
    reason: OpportunityArchiveReason,
    changed_by: str | None = None,
    collection_run_id: str | None = None,
    context: dict | None = None,
) -> None:
    db.add(
        OpportunityArchiveHistory(
            opportunity_id=finding.id,
            action=action.value,
            reason=reason.value,
            changed_by=changed_by,
            collection_run_id=collection_run_id,
            occurred_at=utcnow(),
            context=context or {},
        )
    )


def archive(db: Session, opportunity_id: str, actor: User) -> Finding:
    """Archive an opportunity without changing human or technical lifecycle state."""

    finding = _locked(db, opportunity_id)
    if finding.archived_at is not None:
        return finding

    archived_at = utcnow()
    finding.archived_at = archived_at
    finding.archived_by = actor.id
    finding.archive_reason = OpportunityArchiveReason.MANUAL.value
    _history(
        db,
        finding,
        action=OpportunityArchiveAction.ARCHIVE,
        reason=OpportunityArchiveReason.MANUAL,
        changed_by=actor.id,
        context={
            "status": finding.status,
            "presence_status": finding.presence_status,
        },
    )
    refresh_summaries_for_findings(db, [finding])
    return finding


def unarchive(db: Session, opportunity_id: str, actor: User) -> Finding:
    """Restore an archived opportunity to operational views without lifecycle mutation."""

    finding = _locked(db, opportunity_id)
    if finding.archived_at is None:
        return finding

    previous = {
        "archived_at": finding.archived_at.isoformat(),
        "archived_by": finding.archived_by,
        "archive_reason": finding.archive_reason,
        "status": finding.status,
        "presence_status": finding.presence_status,
    }
    finding.archived_at = None
    finding.archived_by = None
    finding.archive_reason = None
    _history(
        db,
        finding,
        action=OpportunityArchiveAction.UNARCHIVE,
        reason=OpportunityArchiveReason.MANUAL,
        changed_by=actor.id,
        context=previous,
    )
    refresh_summaries_for_findings(db, [finding])
    return finding


def unarchive_reappeared(db: Session, finding: Finding, run: CollectionRun) -> bool:
    """Automatically surface an archived finding when a valid new observation reappears."""

    if finding.archived_at is None:
        return False

    previous = {
        "archived_at": finding.archived_at.isoformat(),
        "archived_by": finding.archived_by,
        "archive_reason": finding.archive_reason,
        "status": finding.status,
        "presence_status": finding.presence_status,
        "provider": finding.provider,
        "account_id": finding.account_id,
    }
    finding.archived_at = None
    finding.archived_by = None
    finding.archive_reason = None
    _history(
        db,
        finding,
        action=OpportunityArchiveAction.UNARCHIVE,
        reason=OpportunityArchiveReason.REAPPEARED,
        collection_run_id=run.id,
        context=previous,
    )
    return True
