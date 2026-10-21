from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.finding import Finding
from app.models.opportunity_archive_history import (
    OpportunityArchiveAction,
    OpportunityArchiveHistory,
    OpportunityArchiveReason,
)
from app.models.opportunity_history_cycle import (
    OpportunityHistoryCycle,
    OpportunityHistoryCycleStatus,
)
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.services.audit import AuditService, new_correlation_id, sanitize_audit_payload
from app.services.dashboard_aggregation import refresh_summaries_for_findings
from app.services.opportunity_history import OpportunityHistoryCycleService
from app.services.opportunity_query import OpportunityFilters, _apply_filters

BULK_BATCH_SIZE = 500
AUDIT_SAMPLE_SIZE = 20


def _filter_payload(filters: OpportunityFilters) -> dict:
    payload = asdict(filters)
    payload.pop("archive_state", None)
    payload.pop("archived_from", None)
    payload.pop("archived_to", None)
    payload.pop("archive_reason", None)
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in payload.items()
        if value not in (None, "", False)
    }


def _filter_hash(filters: OpportunityFilters) -> str:
    serialized = json.dumps(_filter_payload(filters), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_scope(filters: OpportunityFilters, *, archive_all: bool) -> None:
    if _filter_payload(filters):
        return
    if archive_all:
        return
    raise HTTPException(
        status_code=422,
        detail="Esta operação exige confirmação explícita para arquivar todo o backlog.",
    )


def _active_filters(filters: OpportunityFilters) -> OpportunityFilters:
    return replace(
        filters,
        archive_state="active",
        archived_from=None,
        archived_to=None,
        archive_reason=None,
    )


def _archived_filters(filters: OpportunityFilters) -> OpportunityFilters:
    return replace(
        filters,
        archive_state="archived",
        archived_from=None,
        archived_to=None,
        archive_reason=None,
    )


def _count(db: Session, filters: OpportunityFilters) -> int:
    statement = _apply_filters(select(func.count()).select_from(Finding), filters)
    return int(db.scalar(statement) or 0)


def _group_counts(db: Session, filters: OpportunityFilters, column) -> dict[str, int]:
    statement = select(column, func.count(Finding.id)).select_from(Finding).group_by(column)
    statement = _apply_filters(statement, filters)
    return {str(key or "unknown"): int(count) for key, count in db.execute(statement).all()}


def _savings(db: Session, filters: OpportunityFilters) -> list[dict]:
    statement = (
        select(Finding.currency, func.sum(Finding.estimated_monthly_savings))
        .select_from(Finding)
        .group_by(Finding.currency)
    )
    statement = _apply_filters(statement, filters)
    return [
        {"currency": currency or "USD", "amount": amount or Decimal("0")}
        for currency, amount in db.execute(statement).all()
    ]


def archive_preview(
    db: Session,
    filters: OpportunityFilters,
    *,
    archive_all: bool,
) -> dict:
    _validate_scope(filters, archive_all=archive_all)
    active = _active_filters(filters)
    archived = _archived_filters(filters)
    to_archive = _count(db, active)
    already_archived = _count(db, archived)
    return {
        "matched": to_archive + already_archived,
        "to_archive": to_archive,
        "already_archived": already_archived,
        "by_status": _group_counts(db, active, Finding.status),
        "by_provider": _group_counts(db, active, Finding.provider),
        "by_account": _group_counts(db, active, Finding.account_id),
        "savings": _savings(db, active),
        "filter_hash": _filter_hash(filters),
    }


def period_close_preview(
    db: Session,
    *,
    cycle_id: str,
    filters: OpportunityFilters,
    archive_all: bool,
) -> dict:
    _validate_scope(filters, archive_all=archive_all)
    cycle = db.get(OpportunityHistoryCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Opportunity history cycle not found")
    if cycle.status == OpportunityHistoryCycleStatus.CLOSED.value:
        raise HTTPException(status_code=409, detail="Este período já está fechado.")

    coverage = OpportunityHistoryCycleService.collection_coverage(db, cycle)
    snapshots_to_create = int(
        db.scalar(
            select(func.count(func.distinct(OpportunityObservation.opportunity_id))).where(
                OpportunityObservation.observed_at >= cycle.period_start,
                OpportunityObservation.observed_at < cycle.period_end,
            )
        )
        or 0
    )
    return {
        "cycle_id": cycle.id,
        "cycle_label": cycle.label,
        "snapshots_to_create": snapshots_to_create,
        "collection_runs": int(coverage["total"]),
        "failed_collection_runs": int(coverage["failed"]),
        "running_collection_runs": int(coverage["running"]),
        "archive": archive_preview(db, filters, archive_all=archive_all),
    }


def _append_history(
    db: Session,
    finding: Finding,
    *,
    actor: User,
    operation_at,
    correlation_id: str,
    operation: str,
    cycle_id: str | None,
) -> None:
    context = {
        "operation": operation,
        "correlation_id": correlation_id,
        "status": finding.status,
        "presence_status": finding.presence_status,
    }
    if cycle_id:
        context["cycle_id"] = cycle_id
    db.add(
        OpportunityArchiveHistory(
            opportunity_id=finding.id,
            action=OpportunityArchiveAction.ARCHIVE.value,
            reason=OpportunityArchiveReason.MANUAL.value,
            changed_by=actor.id,
            occurred_at=operation_at,
            context=context,
        )
    )


def _archive_locked(
    db: Session,
    findings: list[Finding],
    *,
    actor: User,
    operation_at,
    correlation_id: str,
    operation: str,
    cycle_id: str | None = None,
) -> tuple[list[Finding], int]:
    updated: list[Finding] = []
    already_archived = 0
    for finding in findings:
        if finding.archived_at is not None:
            already_archived += 1
            continue
        finding.archived_at = operation_at
        finding.archived_by = actor.id
        finding.archive_reason = OpportunityArchiveReason.MANUAL.value
        _append_history(
            db,
            finding,
            actor=actor,
            operation_at=operation_at,
            correlation_id=correlation_id,
            operation=operation,
            cycle_id=cycle_id,
        )
        updated.append(finding)
    if updated:
        refresh_summaries_for_findings(db, updated)
    return updated, already_archived


def _audit_bulk(
    db: Session,
    *,
    actor: User,
    action: str,
    requested: int,
    matched: int,
    archived: int,
    already_archived: int,
    correlation_id: str,
    sample_ids: list[str],
    filters: OpportunityFilters | None = None,
    cycle_id: str | None = None,
) -> None:
    metadata = {
        "requested": requested,
        "matched": matched,
        "archived": archived,
        "already_archived": already_archived,
        "sample_ids": sample_ids[:AUDIT_SAMPLE_SIZE],
        "ids_truncated": archived > AUDIT_SAMPLE_SIZE,
    }
    if filters is not None:
        metadata["filter_hash"] = _filter_hash(filters)
        metadata["filter_summary"] = _filter_payload(filters)
    if cycle_id:
        metadata["cycle_id"] = cycle_id
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action=action,
        entity_type="opportunity_archive_operation",
        entity_id=correlation_id,
        entity_label=f"Archive de {archived} oportunidade(s)",
        source="API",
        metadata=sanitize_audit_payload(metadata, max_bytes=16_384),
        correlation_id=correlation_id,
    )


def bulk_archive(db: Session, opportunity_ids: list[str], actor: User) -> dict:
    ids = sorted(set(opportunity_ids))
    if len(ids) > 500:
        raise HTTPException(status_code=422, detail="Bulk archive supports at most 500 IDs")

    statement = select(Finding).where(Finding.id.in_(ids)).order_by(Finding.id).with_for_update()
    findings = list(db.scalars(statement))
    found = {finding.id for finding in findings}
    missing = [opportunity_id for opportunity_id in ids if opportunity_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail="One or more opportunities were not found")

    operation_at = utcnow()
    correlation_id = new_correlation_id()
    updated, already_archived = _archive_locked(
        db,
        findings,
        actor=actor,
        operation_at=operation_at,
        correlation_id=correlation_id,
        operation="bulk",
    )
    sample_ids = [finding.id for finding in updated[:AUDIT_SAMPLE_SIZE]]
    _audit_bulk(
        db,
        actor=actor,
        action="opportunity.bulk_archive",
        requested=len(ids),
        matched=len(ids),
        archived=len(updated),
        already_archived=already_archived,
        correlation_id=correlation_id,
        sample_ids=sample_ids,
    )
    return {
        "requested": len(ids),
        "matched": len(ids),
        "archived": len(updated),
        "already_archived": already_archived,
        "failed": 0,
        "correlation_id": correlation_id,
        "sample_ids": sample_ids,
        "ids_truncated": len(updated) > AUDIT_SAMPLE_SIZE,
        "cycle_id": None,
    }


def _matching_active_ids(db: Session, filters: OpportunityFilters) -> list[str]:
    statement = _apply_filters(select(Finding.id).select_from(Finding), _active_filters(filters))
    statement = statement.order_by(Finding.id)
    return list(db.scalars(statement))


def archive_by_filter(
    db: Session,
    filters: OpportunityFilters,
    actor: User,
    *,
    archive_all: bool,
    operation: str = "filter",
    correlation_id: str | None = None,
    cycle_id: str | None = None,
    audit_action: str = "opportunity.archive_by_filter",
) -> dict:
    _validate_scope(filters, archive_all=archive_all)
    active_ids = _matching_active_ids(db, filters)
    already_archived = _count(db, _archived_filters(filters))
    operation_at = utcnow()
    correlation_id = correlation_id or new_correlation_id()
    updated_ids: list[str] = []

    for offset in range(0, len(active_ids), BULK_BATCH_SIZE):
        batch_ids = active_ids[offset : offset + BULK_BATCH_SIZE]
        findings = list(
            db.scalars(
                select(Finding)
                .where(Finding.id.in_(batch_ids))
                .order_by(Finding.id)
                .with_for_update()
            )
        )
        updated, _ = _archive_locked(
            db,
            findings,
            actor=actor,
            operation_at=operation_at,
            correlation_id=correlation_id,
            operation=operation,
            cycle_id=cycle_id,
        )
        updated_ids.extend(finding.id for finding in updated)

    sample_ids = updated_ids[:AUDIT_SAMPLE_SIZE]
    _audit_bulk(
        db,
        actor=actor,
        action=audit_action,
        requested=len(active_ids),
        matched=len(active_ids) + already_archived,
        archived=len(updated_ids),
        already_archived=already_archived,
        correlation_id=correlation_id,
        sample_ids=sample_ids,
        filters=filters,
        cycle_id=cycle_id,
    )
    return {
        "requested": len(active_ids),
        "matched": len(active_ids) + already_archived,
        "archived": len(updated_ids),
        "already_archived": already_archived,
        "failed": 0,
        "correlation_id": correlation_id,
        "sample_ids": sample_ids,
        "ids_truncated": len(updated_ids) > AUDIT_SAMPLE_SIZE,
        "cycle_id": cycle_id,
    }


def close_period_and_archive(
    db: Session,
    *,
    cycle_id: str,
    filters: OpportunityFilters,
    archive_all: bool,
    actor: User,
) -> dict:
    _validate_scope(filters, archive_all=archive_all)
    cycle = db.scalar(
        select(OpportunityHistoryCycle)
        .where(OpportunityHistoryCycle.id == cycle_id)
        .with_for_update()
    )
    if cycle is None:
        raise HTTPException(status_code=404, detail="Opportunity history cycle not found")
    if cycle.status == OpportunityHistoryCycleStatus.CLOSED.value:
        raise HTTPException(status_code=409, detail="Este período já está fechado.")

    coverage = OpportunityHistoryCycleService.collection_coverage(db, cycle)
    if coverage["running"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Não é possível fechar este período enquanto existem "
                f"{coverage['running']} coletas em andamento."
            ),
        )

    correlation_id = new_correlation_id()
    closed_cycle = OpportunityHistoryCycleService.close_cycle(
        db,
        cycle_id,
        actor=actor,
        close_reason="MANUAL",
    )
    db.flush()
    result = archive_by_filter(
        db,
        filters,
        actor,
        archive_all=archive_all,
        operation="period_close",
        correlation_id=correlation_id,
        cycle_id=cycle_id,
        audit_action="opportunity.period_close",
    )
    snapshots_created = int((closed_cycle.metadata_json or {}).get("snapshot_count", 0))
    return result | {
        "cycle_closed": True,
        "snapshots_created": snapshots_created,
        "collection_runs": int(coverage["total"]),
        "failed_collection_runs": int(coverage["failed"]),
    }
