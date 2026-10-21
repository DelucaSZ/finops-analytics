from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.opportunity_history_cycle import OpportunityHistoryCycleStatus
from app.models.opportunity_history_snapshot import OpportunityHistorySnapshot
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.schemas.opportunity_archiving import (
    ArchiveScopeRequest,
    PeriodClosePreviewResponse,
    PeriodCloseRequest,
)
from app.services.audit import AuditService, new_correlation_id
from app.services.opportunity_bulk_archiving import archive_by_filter, preview_archive
from app.services.opportunity_history import OpportunityHistoryCycleService, get_cycle


def _scope(request: PeriodCloseRequest) -> ArchiveScopeRequest:
    return ArchiveScopeRequest(filters=request.filters, archive_all=request.archive_all)


def _ensure_open(cycle) -> None:
    if cycle.status != OpportunityHistoryCycleStatus.OPEN.value:
        raise HTTPException(
            status_code=409,
            detail="Somente um ciclo histórico aberto pode ser fechado operacionalmente.",
        )


def _snapshot_source_count(db: Session, cycle) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(OpportunityObservation.opportunity_id))).where(
                OpportunityObservation.observed_at >= cycle.period_start,
                OpportunityObservation.observed_at < cycle.period_end,
            )
        )
        or 0
    )


def preview_period_close(
    db: Session,
    request: PeriodCloseRequest,
) -> PeriodClosePreviewResponse:
    cycle = get_cycle(db, request.cycle_id)
    _ensure_open(cycle)
    coverage = OpportunityHistoryCycleService.collection_coverage(db, cycle)
    archive_preview = preview_archive(db, _scope(request))
    return PeriodClosePreviewResponse(
        cycle_id=cycle.id,
        label=cycle.label,
        period_start=cycle.period_start,
        period_end=cycle.period_end,
        cycle_status=cycle.status,
        snapshots_to_create=_snapshot_source_count(db, cycle),
        collection_runs=coverage["total"],
        failed_collection_runs=coverage["failed"],
        running_collection_runs=coverage["running"],
        archive=archive_preview,
    )


def close_period_operationally(
    db: Session,
    request: PeriodCloseRequest,
    actor: User,
) -> dict:
    cycle = get_cycle(db, request.cycle_id)
    _ensure_open(cycle)
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
    # close_cycle only flushes. The API route commits after this orchestration returns,
    # so snapshot creation + cycle transition + archive remain one DB transaction.
    cycle = OpportunityHistoryCycleService.close_cycle(
        db,
        cycle.id,
        actor=actor,
        close_reason="MANUAL",
    )

    archive_result = archive_by_filter(
        db,
        _scope(request),
        actor,
        operation="period_close",
        correlation_id=correlation_id,
        cycle_id=cycle.id,
        emit_audit=False,
    )

    snapshots_created = int(
        db.scalar(
            select(func.count(OpportunityHistorySnapshot.id)).where(
                OpportunityHistorySnapshot.cycle_id == cycle.id
            )
        )
        or 0
    )
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action="opportunity.period_close",
        entity_type="opportunity_history_cycle",
        entity_id=cycle.id,
        entity_label=cycle.label,
        source="API",
        correlation_id=correlation_id,
        metadata={
            "cycle_id": cycle.id,
            "snapshot_count": snapshots_created,
            "collection_runs_count": coverage["total"],
            "failed_collection_runs": coverage["failed"],
            "requested": archive_result.requested,
            "updated": archive_result.archived,
            "already_archived": archive_result.already_archived,
            "sample_ids": archive_result.sample_ids,
            "ids_truncated": archive_result.ids_truncated,
            "filter_hash": archive_result.filter_hash,
            "filter_summary": request.filters.meaningful(),
        },
    )
    db.flush()
    return {
        "cycle_closed": True,
        "cycle_id": cycle.id,
        "snapshots_created": snapshots_created,
        "collection_runs": coverage["total"],
        "failed_collection_runs": coverage["failed"],
        "matched": archive_result.matched,
        "archived": archive_result.archived,
        "already_archived": archive_result.already_archived,
        "failed": 0,
        "correlation_id": correlation_id,
        "sample_ids": archive_result.sample_ids,
        "ids_truncated": archive_result.ids_truncated,
        "filter_hash": archive_result.filter_hash,
    }
