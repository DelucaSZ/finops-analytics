from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.finding import Finding
from app.models.opportunity_archive_history import (
    OpportunityArchiveAction,
    OpportunityArchiveReason,
)
from app.models.user import User
from app.schemas.opportunity_archiving import (
    MAX_BULK_ARCHIVE_IDS,
    ArchivePreviewResponse,
    ArchiveScopeRequest,
    OpportunityArchiveFilters,
)
from app.services.audit import AuditService, new_correlation_id
from app.services.dashboard_aggregation import (
    refresh_account_summary_after_lifecycle,
    refresh_summaries_for_findings,
)
from app.services.opportunity_archiving import _history
from app.services.opportunity_query import OpportunityFilters, _apply_filters

# The current deployment operates on a few thousand findings per cycle. Keeping the
# mutation synchronous preserves one DB transaction. Larger scopes must be refined
# until a durable background-job abstraction is introduced deliberately.
MAX_SYNC_ARCHIVE_MATCHES = 20_000
ARCHIVE_BATCH_SIZE = 500
ARCHIVE_ID_SAMPLE_SIZE = 20


@dataclass(frozen=True)
class ArchiveOperationResult:
    requested: int
    matched: int
    archived: int
    already_archived: int
    correlation_id: str
    sample_ids: list[str]
    ids_truncated: bool
    filter_hash: str | None = None
    cycle_id: str | None = None

    def payload(self) -> dict:
        return {
            "requested": self.requested,
            "matched": self.matched,
            "archived": self.archived,
            "already_archived": self.already_archived,
            "failed": 0,
            "correlation_id": self.correlation_id,
            "cycle_id": self.cycle_id,
            "sample_ids": self.sample_ids,
            "ids_truncated": self.ids_truncated,
            "filter_hash": self.filter_hash,
        }


def _query_filters(filters: OpportunityArchiveFilters, *, archive_state: str) -> OpportunityFilters:
    return OpportunityFilters(**filters.model_dump(mode="python"), archive_state=archive_state)


def _filter_hash(filters: OpportunityArchiveFilters, archive_all: bool) -> str:
    canonical = json.dumps(
        {"filters": filters.meaningful(), "archive_all": archive_all},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_scope(scope: ArchiveScopeRequest) -> None:
    if scope.filters.is_empty and not scope.archive_all:
        raise HTTPException(
            status_code=422,
            detail=(
                "Esta operação não possui filtros. Envie archive_all=true para confirmar "
                "explicitamente o arquivamento de todo o backlog operacional."
            ),
        )


def _count(db: Session, filters: OpportunityFilters) -> int:
    stmt = _apply_filters(select(func.count(Finding.id)), filters)
    return int(db.scalar(stmt) or 0)


def _group_counts(db: Session, filters: OpportunityFilters, *columns) -> list[tuple]:
    stmt = select(*columns, func.count(Finding.id)).select_from(Finding)
    stmt = _apply_filters(stmt, filters).group_by(*columns).order_by(*columns)
    return list(db.execute(stmt).all())


def preview_archive(db: Session, scope: ArchiveScopeRequest) -> ArchivePreviewResponse:
    _validate_scope(scope)
    active_filters = _query_filters(scope.filters, archive_state="active")
    archived_filters = replace(active_filters, archive_state="archived")

    to_archive = _count(db, active_filters)
    already_archived = _count(db, archived_filters)

    by_status = {
        str(status): int(count)
        for status, count in _group_counts(db, active_filters, Finding.status)
    }
    by_provider = {
        str(provider): int(count)
        for provider, count in _group_counts(db, active_filters, Finding.provider)
    }

    account_rows = _group_counts(db, active_filters, Finding.provider, Finding.account_id)
    # Keep the preview bounded. The total cardinality is returned separately.
    by_account = {
        f"{provider}:{account_id}": int(count) for provider, account_id, count in account_rows[:100]
    }

    currency_stmt = select(
        Finding.currency,
        func.sum(Finding.current_monthly_cost),
        func.sum(Finding.estimated_monthly_savings),
    ).select_from(Finding)
    currency_stmt = (
        _apply_filters(currency_stmt, active_filters)
        .group_by(Finding.currency)
        .order_by(Finding.currency)
    )
    currencies = [
        {
            "currency": str(currency),
            "current_monthly_cost": current_cost or Decimal("0"),
            "estimated_monthly_savings": savings or Decimal("0"),
        }
        for currency, current_cost, savings in db.execute(currency_stmt).all()
    ]

    return ArchivePreviewResponse(
        matched=to_archive + already_archived,
        to_archive=to_archive,
        already_archived=already_archived,
        by_status=by_status,
        by_provider=by_provider,
        by_account=by_account,
        account_count=len(account_rows),
        currencies=currencies,
        filter_hash=_filter_hash(scope.filters, scope.archive_all),
        generated_at=utcnow(),
        archive_all=scope.archive_all,
    )


def _archive_locked_many(
    db: Session,
    findings: list[Finding],
    *,
    actor: User,
    operation: str,
    correlation_id: str,
    operation_at: datetime,
    filter_hash: str | None = None,
    cycle_id: str | None = None,
) -> list[Finding]:
    updated: list[Finding] = []
    for finding in findings:
        if finding.archived_at is not None:
            continue
        finding.archived_at = operation_at
        finding.archived_by = actor.id
        finding.archive_reason = OpportunityArchiveReason.MANUAL.value
        context = {
            "operation": operation,
            "correlation_id": correlation_id,
            "status": finding.status,
            "presence_status": finding.presence_status,
        }
        if filter_hash:
            context["filter_hash"] = filter_hash
        if cycle_id:
            context["cycle_id"] = cycle_id
        _history(
            db,
            finding,
            action=OpportunityArchiveAction.ARCHIVE,
            reason=OpportunityArchiveReason.MANUAL,
            changed_by=actor.id,
            context=context,
            occurred_at=operation_at,
        )
        updated.append(finding)
    return updated


def _record_bulk_audit(
    db: Session,
    *,
    actor: User,
    action: str,
    operation: str,
    correlation_id: str,
    requested: int,
    archived: int,
    already_archived: int,
    sample_ids: list[str],
    filter_hash: str | None = None,
    filter_summary: dict | None = None,
    cycle_id: str | None = None,
) -> None:
    metadata = {
        "operation": operation,
        "requested": requested,
        "updated": archived,
        "already_archived": already_archived,
        "sample_ids": sample_ids,
        "ids_truncated": archived > len(sample_ids),
    }
    if filter_hash:
        metadata["filter_hash"] = filter_hash
    if filter_summary:
        metadata["filter_summary"] = filter_summary
    if cycle_id:
        metadata["cycle_id"] = cycle_id
    AuditService.record(
        db,
        actor=actor,
        module="opportunities",
        action=action,
        entity_type="opportunity_bulk",
        entity_label=f"{archived} oportunidades arquivadas",
        source="API",
        metadata=metadata,
        correlation_id=correlation_id,
    )


def archive_by_ids(db: Session, opportunity_ids: list[str], actor: User) -> ArchiveOperationResult:
    ids = list(dict.fromkeys(opportunity_ids))
    if not ids:
        raise HTTPException(status_code=422, detail="Informe ao menos uma oportunidade.")
    if len(ids) > MAX_BULK_ARCHIVE_IDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"O arquivamento por IDs aceita no máximo {MAX_BULK_ARCHIVE_IDS} oportunidades. "
                "Use archive-by-filter para escopos maiores."
            ),
        )

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
    already_archived = sum(1 for finding in ordered if finding.archived_at is not None)
    correlation_id = new_correlation_id()
    operation_at = utcnow()
    updated = _archive_locked_many(
        db,
        ordered,
        actor=actor,
        operation="bulk",
        correlation_id=correlation_id,
        operation_at=operation_at,
    )
    refresh_summaries_for_findings(db, updated)

    sample_ids = [finding.id for finding in updated[:ARCHIVE_ID_SAMPLE_SIZE]]
    _record_bulk_audit(
        db,
        actor=actor,
        action="opportunity.bulk_archive",
        operation="bulk",
        correlation_id=correlation_id,
        requested=len(ids),
        archived=len(updated),
        already_archived=already_archived,
        sample_ids=sample_ids,
    )
    return ArchiveOperationResult(
        requested=len(ids),
        matched=len(ids),
        archived=len(updated),
        already_archived=already_archived,
        correlation_id=correlation_id,
        sample_ids=sample_ids,
        ids_truncated=len(updated) > len(sample_ids),
    )


def _archive_resolved_ids_in_batches(
    db: Session,
    target_ids: list[str],
    *,
    actor: User,
    operation: str,
    correlation_id: str,
    operation_at: datetime,
    filter_hash: str,
    cycle_id: str | None,
) -> tuple[int, list[str]]:
    archived = 0
    sample_ids: list[str] = []
    summary_scopes: set[tuple[str, str]] = set()

    for offset in range(0, len(target_ids), ARCHIVE_BATCH_SIZE):
        batch_ids = target_ids[offset : offset + ARCHIVE_BATCH_SIZE]
        findings = list(
            db.scalars(
                select(Finding)
                .where(Finding.id.in_(batch_ids))
                .order_by(Finding.id)
                .with_for_update()
            )
        )
        updated = _archive_locked_many(
            db,
            findings,
            actor=actor,
            operation=operation,
            correlation_id=correlation_id,
            operation_at=operation_at,
            filter_hash=filter_hash,
            cycle_id=cycle_id,
        )
        archived += len(updated)
        summary_scopes.update((finding.provider, finding.account_id) for finding in updated)
        remaining_sample_slots = ARCHIVE_ID_SAMPLE_SIZE - len(sample_ids)
        if remaining_sample_slots > 0:
            sample_ids.extend(finding.id for finding in updated[:remaining_sample_slots])
        # Flush each batch without committing. This bounds pending ORM state while the
        # route still owns one all-or-nothing transaction for the complete operation.
        db.flush()

    for provider, account_id in sorted(summary_scopes):
        refresh_account_summary_after_lifecycle(
            db,
            provider=provider,
            account_id=account_id,
        )
    return archived, sample_ids


def archive_by_filter(
    db: Session,
    scope: ArchiveScopeRequest,
    actor: User,
    *,
    operation: str = "filter",
    correlation_id: str | None = None,
    cycle_id: str | None = None,
    emit_audit: bool = True,
) -> ArchiveOperationResult:
    _validate_scope(scope)
    active_filters = _query_filters(scope.filters, archive_state="active")
    archived_filters = replace(active_filters, archive_state="archived")
    active_count = _count(db, active_filters)
    if active_count > MAX_SYNC_ARCHIVE_MATCHES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"O escopo contém {active_count} oportunidades ativas e excede o limite síncrono "
                f"de {MAX_SYNC_ARCHIVE_MATCHES}. Refine os filtros antes de arquivar."
            ),
        )

    target_ids = list(
        db.scalars(_apply_filters(select(Finding.id), active_filters).order_by(Finding.id))
    )
    if len(target_ids) > MAX_SYNC_ARCHIVE_MATCHES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"O escopo contém {len(target_ids)} oportunidades ativas e excede o limite "
                f"síncrono de {MAX_SYNC_ARCHIVE_MATCHES}. Refine os filtros antes de arquivar."
            ),
        )

    already_archived_before = _count(db, archived_filters)
    correlation = correlation_id or new_correlation_id()
    operation_at = utcnow()
    digest = _filter_hash(scope.filters, scope.archive_all)
    archived, sample_ids = _archive_resolved_ids_in_batches(
        db,
        target_ids,
        actor=actor,
        operation=operation,
        correlation_id=correlation,
        operation_at=operation_at,
        filter_hash=digest,
        cycle_id=cycle_id,
    )
    # A concurrent archive can win after scope resolution but before our row lock. Treat
    # those rows as idempotent/already archived instead of reporting a silent mismatch.
    concurrently_archived = max(0, len(target_ids) - archived)
    already_archived = already_archived_before + concurrently_archived

    if emit_audit:
        _record_bulk_audit(
            db,
            actor=actor,
            action="opportunity.archive_by_filter",
            operation=operation,
            correlation_id=correlation,
            requested=len(target_ids),
            archived=archived,
            already_archived=already_archived,
            sample_ids=sample_ids,
            filter_hash=digest,
            filter_summary=scope.filters.meaningful(),
            cycle_id=cycle_id,
        )
    return ArchiveOperationResult(
        requested=len(target_ids),
        matched=len(target_ids) + already_archived_before,
        archived=archived,
        already_archived=already_archived,
        correlation_id=correlation,
        sample_ids=sample_ids,
        ids_truncated=archived > len(sample_ids),
        filter_hash=digest,
        cycle_id=cycle_id,
    )
