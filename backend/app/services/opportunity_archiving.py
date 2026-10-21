from __future__ import annotations

from datetime import datetime

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
from app.services.audit import AuditService, audit_snapshot
from app.services.dashboard_aggregation import refresh_summaries_for_findings

REJECTED = "rejected"


def _locked(db: Session, opportunity_id: str) -> Finding:
    finding = db.scalar(select(Finding).where(Finding.id == opportunity_id).with_for_update())
    if finding is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return finding


def _archive_snapshot(finding: Finding) -> dict:
    return audit_snapshot(
        {
            "archived": finding.archived_at is not None,
            "archive_reason": finding.archive_reason,
            "status": finding.status,
            "presence_status": finding.presence_status,
        }
    )


def _label(finding: Finding) -> str:
    return f"{finding.title} · {finding.resource_name or finding.resource_id}"


def _history(
    db: Session,
    finding: Finding,
    *,
    action: OpportunityArchiveAction,
    reason: OpportunityArchiveReason,
    changed_by: str | None = None,
    collection_run_id: str | None = None,
    context: dict | None = None,
    occurred_at: datetime | None = None,
) -> None:
    db.add(
        OpportunityArchiveHistory(
            opportunity_id=finding.id,
            action=action.value,
            reason=reason.value,
            changed_by=changed_by,
            collection_run_id=collection_run_id,
            occurred_at=occurred_at or utcnow(),
            context=context or {},
        )
    )


def archive(db: Session, opportunity_id: str, actor: User) -> Finding:
    finding = _locked(db, opportunity_id)
    if finding.archived_at is not None:
        return finding
    before = _archive_snapshot(finding)
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
        context={"status": finding.status, "presence_status": finding.presence_status},
    )
    refresh_summaries_for_findings(db, [finding])
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action="opportunity.archive",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_label(finding),
        before=before,
        after=_archive_snapshot(finding),
        source="API",
    )
    return finding


def archive_retention_locked(
    db: Session,
    finding: Finding,
    *,
    archived_at: datetime,
    policy: str,
    threshold_days: int,
    reference_timestamp: datetime,
) -> bool:
    if finding.archived_at is not None:
        return False
    before = _archive_snapshot(finding)
    finding.archived_at = archived_at
    finding.archived_by = None
    finding.archive_reason = OpportunityArchiveReason.RETENTION_POLICY.value
    _history(
        db,
        finding,
        action=OpportunityArchiveAction.ARCHIVE,
        reason=OpportunityArchiveReason.RETENTION_POLICY,
        occurred_at=archived_at,
        context={
            "actor": "SYSTEM",
            "policy": policy,
            "threshold_days": threshold_days,
            "reference_timestamp": reference_timestamp.isoformat(),
            "status": finding.status,
            "presence_status": finding.presence_status,
        },
    )
    AuditService.record(
        db,
        actor=None,
        module="opportunities",
        action="opportunity.archive",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_label(finding),
        before=before,
        after=_archive_snapshot(finding),
        source="SYSTEM",
        metadata={
            "policy": policy,
            "threshold_days": threshold_days,
            "reference_timestamp": reference_timestamp.isoformat(),
        },
    )
    return True


def unarchive(db: Session, opportunity_id: str, actor: User) -> Finding:
    finding = _locked(db, opportunity_id)
    if finding.archived_at is None:
        return finding
    if finding.status == REJECTED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Esta oportunidade está rejeitada. Reabra-a para devolvê-la ao backlog operacional."
            ),
        )
    before = _archive_snapshot(finding)
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
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action="opportunity.unarchive",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_label(finding),
        before=before,
        after=_archive_snapshot(finding),
        source="API",
    )
    return finding


def unarchive_for_reopen(db: Session, finding: Finding, actor: User) -> bool:
    """Unarchive a locked rejected finding as part of an explicit reopen transaction."""

    if finding.archived_at is None:
        return False
    if finding.status != REJECTED:
        raise RuntimeError("Reopen unarchive is only valid for rejected opportunities")

    before = _archive_snapshot(finding)
    previous = {
        "archived_at": finding.archived_at.isoformat(),
        "archived_by": finding.archived_by,
        "archive_reason": finding.archive_reason,
        "status": finding.status,
        "presence_status": finding.presence_status,
        "trigger": "reopen",
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
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action="opportunity.unarchive",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_label(finding),
        before=before,
        after=_archive_snapshot(finding),
        source="API",
        metadata={"reason": "REOPEN"},
    )
    return True


def unarchive_reappeared(db: Session, finding: Finding, run: CollectionRun) -> bool:
    # Defense in depth: automatic collection flows can never break an explicit rejection.
    if finding.status == REJECTED:
        return False
    if finding.archived_at is None:
        return False
    before = _archive_snapshot(finding)
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
    AuditService.record(
        db,
        actor=None,
        module="opportunities",
        action="opportunity.unarchive",
        entity_type="opportunity",
        entity_id=finding.id,
        entity_label=_label(finding),
        before=before,
        after=_archive_snapshot(finding),
        source="SYSTEM",
        metadata={"collection_run_id": run.id, "reason": "REAPPEARED"},
    )
    return True
