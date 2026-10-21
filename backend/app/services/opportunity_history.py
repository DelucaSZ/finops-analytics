from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_history_cycle import (
    OpportunityHistoryCycle,
    OpportunityHistoryCycleStatus,
)
from app.models.opportunity_history_snapshot import OpportunityHistorySnapshot
from app.models.opportunity_observation import OpportunityObservation
from app.models.user import User
from app.services.audit import AuditService, new_correlation_id, sanitize_audit_payload

DEFAULT_CYCLE_TIMEZONE = "UTC"
CLOSE_REASONS = {"MANUAL", "SCHEDULED", "SYSTEM"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _month_bounds(timestamp: datetime) -> tuple[datetime, datetime, str]:
    current = _utc(timestamp)
    start = datetime(current.year, current.month, 1, tzinfo=UTC)
    if current.month == 12:
        end = datetime(current.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    label = f"{start.month:02d}/{start.year}"
    return start, end, label


def _safe_json(payload: Any, *, max_bytes: int = 16_384) -> dict[str, Any]:
    value = sanitize_audit_payload(payload, max_bytes=max_bytes)
    return value if isinstance(value, dict) else {}


def _money_rows(rows) -> list[dict[str, Any]]:
    return [{"currency": currency, "amount": amount or Decimal("0")} for currency, amount in rows]


class OpportunityHistoryCycleService:
    @staticmethod
    def create_cycle(
        db: Session,
        *,
        period_start: datetime,
        period_end: datetime,
        label: str,
        timezone: str = DEFAULT_CYCLE_TIMEZONE,
    ) -> OpportunityHistoryCycle:
        start = _utc(period_start)
        end = _utc(period_end)
        if start >= end:
            raise HTTPException(status_code=422, detail="period_start must be before period_end")

        overlap = db.scalar(
            select(OpportunityHistoryCycle.id).where(
                OpportunityHistoryCycle.period_start < end,
                OpportunityHistoryCycle.period_end > start,
            )
        )
        if overlap is not None:
            raise HTTPException(
                status_code=409,
                detail="Opportunity history cycle overlaps an existing cycle",
            )

        cycle = OpportunityHistoryCycle(
            label=label.strip() or f"{start.isoformat()} — {end.isoformat()}",
            period_start=start,
            period_end=end,
            status=OpportunityHistoryCycleStatus.OPEN.value,
            timezone=timezone or DEFAULT_CYCLE_TIMEZONE,
            metadata_json={},
        )
        db.add(cycle)
        db.flush()
        return cycle

    @classmethod
    def get_or_create_cycle_for(
        cls,
        db: Session,
        timestamp: datetime,
    ) -> OpportunityHistoryCycle:
        start, end, label = _month_bounds(timestamp)
        existing = db.scalar(
            select(OpportunityHistoryCycle).where(
                OpportunityHistoryCycle.period_start == start,
                OpportunityHistoryCycle.period_end == end,
            )
        )
        if existing is not None:
            return existing
        try:
            with db.begin_nested():
                return cls.create_cycle(
                    db,
                    period_start=start,
                    period_end=end,
                    label=label,
                    timezone=DEFAULT_CYCLE_TIMEZONE,
                )
        except IntegrityError:
            existing = db.scalar(
                select(OpportunityHistoryCycle).where(
                    OpportunityHistoryCycle.period_start == start,
                    OpportunityHistoryCycle.period_end == end,
                )
            )
            if existing is not None:
                return existing
            raise

    @staticmethod
    def collection_coverage(db: Session, cycle: OpportunityHistoryCycle) -> dict[str, int]:
        rows = db.execute(
            select(CollectionRun.status, func.count(CollectionRun.id))
            .where(
                CollectionRun.started_at >= cycle.period_start,
                CollectionRun.started_at < cycle.period_end,
            )
            .group_by(CollectionRun.status)
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        total = sum(counts.values())
        return {
            "total": total,
            "success": counts.get(CollectionRunStatus.SUCCESS.value, 0),
            "failed": counts.get(CollectionRunStatus.FAILED.value, 0),
            "running": counts.get(CollectionRunStatus.RUNNING.value, 0),
        }

    @staticmethod
    def _snapshot_source_rows(db: Session, cycle: OpportunityHistoryCycle):
        obs = OpportunityObservation
        in_cycle = and_(obs.observed_at >= cycle.period_start, obs.observed_at < cycle.period_end)

        aggregate = (
            select(
                obs.opportunity_id.label("opportunity_id"),
                func.min(obs.observed_at).label("first_observed_in_cycle_at"),
                func.max(obs.observed_at).label("last_observed_in_cycle_at"),
                func.count(func.distinct(obs.collection_run_id)).label("occurrence_count_in_cycle"),
            )
            .where(in_cycle)
            .group_by(obs.opportunity_id)
            .subquery("history_aggregate")
        )

        latest_ranked = (
            select(
                obs.opportunity_id.label("opportunity_id"),
                obs.collection_run_id.label("collection_run_id"),
                obs.severity.label("severity"),
                obs.current_monthly_cost.label("current_monthly_cost"),
                obs.estimated_monthly_savings.label("estimated_monthly_savings"),
                obs.currency.label("currency"),
                obs.confidence.label("confidence"),
                obs.provider_metadata.label("provider_metadata"),
                obs.evidence.label("evidence"),
                func.row_number()
                .over(
                    partition_by=obs.opportunity_id,
                    order_by=(obs.observed_at.desc(), obs.id.desc()),
                )
                .label("rn"),
            )
            .where(in_cycle)
            .subquery("history_latest_ranked")
        )
        latest = (
            select(
                latest_ranked.c.opportunity_id,
                latest_ranked.c.collection_run_id,
                latest_ranked.c.severity,
                latest_ranked.c.current_monthly_cost,
                latest_ranked.c.estimated_monthly_savings,
                latest_ranked.c.currency,
                latest_ranked.c.confidence,
                latest_ranked.c.provider_metadata,
                latest_ranked.c.evidence,
            )
            .where(latest_ranked.c.rn == 1)
            .subquery("history_latest")
        )

        first_ranked = (
            select(
                obs.opportunity_id.label("opportunity_id"),
                obs.collection_run_id.label("collection_run_id"),
                func.row_number()
                .over(
                    partition_by=obs.opportunity_id,
                    order_by=(obs.observed_at.asc(), obs.id.asc()),
                )
                .label("rn"),
            )
            .where(in_cycle)
            .subquery("history_first_ranked")
        )
        first = (
            select(first_ranked.c.opportunity_id, first_ranked.c.collection_run_id)
            .where(first_ranked.c.rn == 1)
            .subquery("history_first")
        )

        stmt = (
            select(
                Finding,
                CloudAccount.name.label("account_name"),
                aggregate.c.first_observed_in_cycle_at,
                aggregate.c.last_observed_in_cycle_at,
                aggregate.c.occurrence_count_in_cycle,
                latest.c.collection_run_id.label("last_collection_run_id"),
                latest.c.severity,
                latest.c.current_monthly_cost,
                latest.c.estimated_monthly_savings,
                latest.c.currency,
                latest.c.confidence,
                latest.c.provider_metadata,
                latest.c.evidence,
                first.c.collection_run_id.label("first_collection_run_id"),
            )
            .join(aggregate, aggregate.c.opportunity_id == Finding.id)
            .join(latest, latest.c.opportunity_id == Finding.id)
            .join(first, first.c.opportunity_id == Finding.id)
            .outerjoin(
                CloudAccount,
                and_(
                    CloudAccount.provider == Finding.provider,
                    CloudAccount.native_account_id == Finding.account_id,
                ),
            )
            .order_by(Finding.id)
        )
        return db.execute(stmt).all()

    @classmethod
    def close_cycle(
        cls,
        db: Session,
        cycle_id: str,
        *,
        actor: User | None,
        close_reason: str = "MANUAL",
    ) -> OpportunityHistoryCycle:
        reason = close_reason.upper().strip()
        if reason not in CLOSE_REASONS:
            raise HTTPException(status_code=422, detail="Unsupported close reason")

        cycle = db.scalar(
            select(OpportunityHistoryCycle)
            .where(OpportunityHistoryCycle.id == cycle_id)
            .with_for_update()
        )
        if cycle is None:
            raise HTTPException(status_code=404, detail="Opportunity history cycle not found")
        if cycle.status == OpportunityHistoryCycleStatus.CLOSED.value:
            return cycle

        running = int(
            db.scalar(
                select(func.count(CollectionRun.id)).where(
                    CollectionRun.started_at >= cycle.period_start,
                    CollectionRun.started_at < cycle.period_end,
                    CollectionRun.status == CollectionRunStatus.RUNNING.value,
                )
            )
            or 0
        )
        if running:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Este período ainda possui coletas em andamento. "
                    "Aguarde a conclusão antes de fechar o ciclo."
                ),
            )

        existing_snapshots = int(
            db.scalar(
                select(func.count(OpportunityHistorySnapshot.id)).where(
                    OpportunityHistorySnapshot.cycle_id == cycle.id
                )
            )
            or 0
        )
        if existing_snapshots:
            raise HTTPException(
                status_code=409,
                detail="Open cycle contains snapshots and cannot be safely closed",
            )

        captured_at = utcnow()
        snapshots: list[OpportunityHistorySnapshot] = []
        for row in cls._snapshot_source_rows(db, cycle):
            finding: Finding = row[0]
            snapshots.append(
                OpportunityHistorySnapshot(
                    cycle_id=cycle.id,
                    opportunity_id=finding.id,
                    fingerprint=finding.fingerprint,
                    provider=finding.provider,
                    account_id=finding.account_id,
                    account_name=row.account_name,
                    region=finding.region,
                    service=finding.service,
                    resource_type=finding.resource_type,
                    resource_id=finding.resource_id,
                    resource_name=finding.resource_name,
                    rule_key=finding.rule_key,
                    title=finding.title,
                    description=finding.description,
                    status=finding.status,
                    presence_status=finding.presence_status,
                    needs_review=bool(finding.needs_review),
                    archived=finding.archived_at is not None,
                    archive_reason=finding.archive_reason,
                    treated_at=finding.treated_at,
                    rejected_at=finding.rejected_at,
                    resolved_externally_at=finding.resolved_externally_at,
                    treatment_note=finding.treatment_note,
                    rejection_reason=finding.rejection_reason,
                    rejection_note=finding.rejection_note,
                    current_monthly_cost=row.current_monthly_cost,
                    estimated_monthly_savings=row.estimated_monthly_savings,
                    currency=row.currency,
                    severity=row.severity,
                    confidence=row.confidence,
                    first_seen_at=finding.first_seen_at,
                    last_seen_at=finding.last_seen_at,
                    first_observed_in_cycle_at=row.first_observed_in_cycle_at,
                    last_observed_in_cycle_at=row.last_observed_in_cycle_at,
                    occurrence_count_in_cycle=int(row.occurrence_count_in_cycle or 0),
                    total_occurrence_count=int(finding.total_occurrence_count or 0),
                    first_collection_run_id_in_cycle=row.first_collection_run_id,
                    last_collection_run_id_in_cycle=row.last_collection_run_id,
                    provider_metadata=_safe_json(row.provider_metadata),
                    evidence=_safe_json(row.evidence),
                    captured_at=captured_at,
                    capture_reason=reason,
                    metadata_json={},
                )
            )

        db.add_all(snapshots)
        db.flush()

        coverage = cls.collection_coverage(db, cycle)
        cycle.status = OpportunityHistoryCycleStatus.CLOSED.value
        cycle.closed_at = captured_at
        cycle.closed_by = actor.id if actor is not None else None
        cycle.close_reason = reason
        cycle.metadata_json = {
            "snapshot_count": len(snapshots),
            "collection_coverage": coverage,
        }

        totals = cycle_stats(db, cycle.id)
        AuditService.record(
            db,
            actor=actor,
            module="opportunities",
            action="opportunity_cycle.close",
            entity_type="opportunity_history_cycle",
            entity_id=cycle.id,
            entity_label=cycle.label,
            source="SYSTEM" if actor is None else "API",
            metadata={
                "cycle_id": cycle.id,
                "label": cycle.label,
                "period_start": cycle.period_start,
                "period_end": cycle.period_end,
                "snapshot_count": len(snapshots),
                "totals": totals,
                "currencies": sorted(
                    {item["currency"] for item in totals.get("potential_savings", [])}
                    | {item["currency"] for item in totals.get("current_cost", [])}
                ),
                "collection_runs_count": coverage["total"],
                "close_reason": reason,
            },
            correlation_id=new_correlation_id(),
        )
        db.flush()
        return cycle


def cycle_stats(db: Session, cycle_id: str) -> dict[str, Any]:
    status_rows = db.execute(
        select(OpportunityHistorySnapshot.status, func.count(OpportunityHistorySnapshot.id))
        .where(OpportunityHistorySnapshot.cycle_id == cycle_id)
        .group_by(OpportunityHistorySnapshot.status)
    ).all()
    severity_rows = db.execute(
        select(OpportunityHistorySnapshot.severity, func.count(OpportunityHistorySnapshot.id))
        .where(OpportunityHistorySnapshot.cycle_id == cycle_id)
        .group_by(OpportunityHistorySnapshot.severity)
    ).all()
    savings_rows = db.execute(
        select(
            OpportunityHistorySnapshot.currency,
            func.sum(OpportunityHistorySnapshot.estimated_monthly_savings),
        )
        .where(OpportunityHistorySnapshot.cycle_id == cycle_id)
        .group_by(OpportunityHistorySnapshot.currency)
    ).all()
    cost_rows = db.execute(
        select(
            OpportunityHistorySnapshot.currency,
            func.sum(OpportunityHistorySnapshot.current_monthly_cost),
        )
        .where(OpportunityHistorySnapshot.cycle_id == cycle_id)
        .group_by(OpportunityHistorySnapshot.currency)
    ).all()
    providers = int(
        db.scalar(
            select(func.count(func.distinct(OpportunityHistorySnapshot.provider))).where(
                OpportunityHistorySnapshot.cycle_id == cycle_id
            )
        )
        or 0
    )
    accounts = int(
        db.scalar(
            select(func.count(func.distinct(OpportunityHistorySnapshot.account_id))).where(
                OpportunityHistorySnapshot.cycle_id == cycle_id
            )
        )
        or 0
    )
    total = sum(int(count) for _, count in status_rows)
    return {
        "total": total,
        "by_status": {str(key): int(value) for key, value in status_rows},
        "by_severity": {str(key): int(value) for key, value in severity_rows},
        "potential_savings": _money_rows(savings_rows),
        "current_cost": _money_rows(cost_rows),
        "providers": providers,
        "accounts": accounts,
    }


def cycle_payload(db: Session, cycle: OpportunityHistoryCycle) -> dict[str, Any]:
    metadata = cycle.metadata_json or {}
    coverage = metadata.get("collection_coverage")
    if not isinstance(coverage, dict):
        coverage = OpportunityHistoryCycleService.collection_coverage(db, cycle)
    totals = (
        cycle_stats(db, cycle.id)
        if cycle.status == OpportunityHistoryCycleStatus.CLOSED.value
        else {}
    )
    snapshot_count = int(
        db.scalar(
            select(func.count(OpportunityHistorySnapshot.id)).where(
                OpportunityHistorySnapshot.cycle_id == cycle.id
            )
        )
        or 0
    )
    return {
        "id": cycle.id,
        "label": cycle.label,
        "period_start": cycle.period_start,
        "period_end": cycle.period_end,
        "status": cycle.status,
        "timezone": cycle.timezone,
        "created_at": cycle.created_at,
        "closed_at": cycle.closed_at,
        "closed_by": cycle.closed_by,
        "close_reason": cycle.close_reason,
        "snapshot_count": snapshot_count,
        "totals": totals,
        "coverage": coverage,
    }


def list_cycles(db: Session) -> dict[str, Any]:
    cycles = list(
        db.scalars(
            select(OpportunityHistoryCycle).order_by(OpportunityHistoryCycle.period_start.desc())
        )
    )
    return {"items": [cycle_payload(db, cycle) for cycle in cycles], "total": len(cycles)}


def get_cycle(db: Session, cycle_id: str) -> OpportunityHistoryCycle:
    cycle = db.get(OpportunityHistoryCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Opportunity history cycle not found")
    return cycle


def snapshot_payload(snapshot: OpportunityHistorySnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "cycle_id": snapshot.cycle_id,
        "opportunity_id": snapshot.opportunity_id,
        "fingerprint": snapshot.fingerprint,
        "provider": snapshot.provider,
        "account_id": snapshot.account_id,
        "account_name": snapshot.account_name,
        "region": snapshot.region,
        "service": snapshot.service,
        "resource_type": snapshot.resource_type,
        "resource_id": snapshot.resource_id,
        "resource_name": snapshot.resource_name,
        "rule_key": snapshot.rule_key,
        "title": snapshot.title,
        "description": snapshot.description,
        "status": snapshot.status,
        "presence_status": snapshot.presence_status,
        "needs_review": snapshot.needs_review,
        "archived": snapshot.archived,
        "archive_reason": snapshot.archive_reason,
        "treated_at": snapshot.treated_at,
        "rejected_at": snapshot.rejected_at,
        "resolved_externally_at": snapshot.resolved_externally_at,
        "treatment_note": snapshot.treatment_note,
        "rejection_reason": snapshot.rejection_reason,
        "rejection_note": snapshot.rejection_note,
        "current_monthly_cost": snapshot.current_monthly_cost,
        "estimated_monthly_savings": snapshot.estimated_monthly_savings,
        "currency": snapshot.currency,
        "severity": snapshot.severity,
        "confidence": snapshot.confidence,
        "first_seen_at": snapshot.first_seen_at,
        "last_seen_at": snapshot.last_seen_at,
        "first_observed_in_cycle_at": snapshot.first_observed_in_cycle_at,
        "last_observed_in_cycle_at": snapshot.last_observed_in_cycle_at,
        "occurrence_count_in_cycle": snapshot.occurrence_count_in_cycle,
        "total_occurrence_count": snapshot.total_occurrence_count,
        "first_collection_run_id_in_cycle": snapshot.first_collection_run_id_in_cycle,
        "last_collection_run_id_in_cycle": snapshot.last_collection_run_id_in_cycle,
        "provider_metadata": snapshot.provider_metadata or {},
        "evidence": snapshot.evidence or {},
        "captured_at": snapshot.captured_at,
        "capture_reason": snapshot.capture_reason,
        "metadata": snapshot.metadata_json or {},
    }


def list_snapshots(
    db: Session,
    *,
    cycle_id: str,
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    service: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    presence_status: str | None = None,
    severity: str | None = None,
    rule: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "estimated_savings",
    order: str = "desc",
) -> dict[str, Any]:
    cycle = get_cycle(db, cycle_id)
    if cycle.status != OpportunityHistoryCycleStatus.CLOSED.value:
        raise HTTPException(
            status_code=409,
            detail=(
                "Prévia — período ainda não fechado. "
                "Snapshots definitivos existem apenas para ciclos CLOSED."
            ),
        )

    filters = [OpportunityHistorySnapshot.cycle_id == cycle_id]
    if provider:
        filters.append(OpportunityHistorySnapshot.provider == provider.lower())
    if account_id:
        filters.append(OpportunityHistorySnapshot.account_id == account_id)
    if region:
        filters.append(OpportunityHistorySnapshot.region == region)
    if service:
        filters.append(OpportunityHistorySnapshot.service == service)
    if resource_type:
        filters.append(OpportunityHistorySnapshot.resource_type == resource_type)
    if status:
        filters.append(OpportunityHistorySnapshot.status == status)
    if presence_status:
        filters.append(OpportunityHistorySnapshot.presence_status == presence_status)
    if severity:
        filters.append(OpportunityHistorySnapshot.severity == severity)
    if rule:
        filters.append(OpportunityHistorySnapshot.rule_key == rule)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                OpportunityHistorySnapshot.title.ilike(term),
                OpportunityHistorySnapshot.resource_id.ilike(term),
                OpportunityHistorySnapshot.resource_name.ilike(term),
                OpportunityHistorySnapshot.account_id.ilike(term),
                OpportunityHistorySnapshot.account_name.ilike(term),
            )
        )

    sort_columns = {
        "estimated_savings": OpportunityHistorySnapshot.estimated_monthly_savings,
        "current_cost": OpportunityHistorySnapshot.current_monthly_cost,
        "severity": case(
            (OpportunityHistorySnapshot.severity == "high", 3),
            (OpportunityHistorySnapshot.severity == "medium", 2),
            else_=1,
        ),
        "first_observed_in_cycle_at": OpportunityHistorySnapshot.first_observed_in_cycle_at,
        "last_observed_in_cycle_at": OpportunityHistorySnapshot.last_observed_in_cycle_at,
        "status": OpportunityHistorySnapshot.status,
        "resource": OpportunityHistorySnapshot.resource_id,
        "account": OpportunityHistorySnapshot.account_id,
    }
    sort_column = sort_columns.get(sort, OpportunityHistorySnapshot.estimated_monthly_savings)
    direction = asc if order == "asc" else desc
    total = int(db.scalar(select(func.count(OpportunityHistorySnapshot.id)).where(*filters)) or 0)
    items = list(
        db.scalars(
            select(OpportunityHistorySnapshot)
            .where(*filters)
            .order_by(direction(sort_column), OpportunityHistorySnapshot.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [snapshot_payload(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_snapshot(db: Session, snapshot_id: str) -> dict[str, Any]:
    snapshot = db.get(OpportunityHistorySnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Opportunity history snapshot not found")
    return snapshot_payload(snapshot)
