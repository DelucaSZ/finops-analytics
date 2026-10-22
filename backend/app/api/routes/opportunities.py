from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_operator, require_user
from app.db.session import get_db
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import OpportunityPresenceStatus
from app.models.user import User
from app.schemas.finding import OpportunityNote, OpportunityReject
from app.schemas.opportunity import (
    ArchiveHistoryPage,
    ArchiveOperationResult,
    ArchivePreviewResult,
    ArchiveScopeRequest,
    BulkArchiveRequest,
    BulkReject,
    BulkTransitionBase,
    BulkTransitionResult,
    ObservationPage,
    OpportunityArchiveFilterScope,
    OpportunityArchiveState,
    OpportunityDetail,
    OpportunityOptions,
    OpportunityPage,
    OpportunitySeverity,
    OpportunitySort,
    OpportunityStats,
    OpportunityStatus,
    PeriodCloseRequest,
    PeriodCloseResult,
    SortOrder,
    StatusHistoryPage,
)
from app.schemas.opportunity_presence_history import PresenceHistoryPage
from app.services.collection_comparison import previous_comparable_run
from app.services.dashboard_opportunity_query import (
    dashboard_comparison_stats,
    list_dashboard_comparison_opportunities,
)
from app.services.opportunity_archiving import archive, unarchive
from app.services.opportunity_bulk_archiving import (
    archive_by_filter,
    archive_preview,
    bulk_archive,
    close_period_and_archive,
)
from app.services.opportunity_lifecycle import bulk_transition, reject, reopen, treat
from app.services.opportunity_presence_history import presence_history
from app.services.opportunity_query import (
    OpportunityFilters,
    archive_history,
    get_opportunity,
    list_opportunities,
    observation_history,
    opportunity_options,
    opportunity_stats,
    status_history,
)
from app.services.opportunity_run_comparison import (
    ComparisonContextError,
    resolve_comparison_context,
)

router = APIRouter(
    prefix="/opportunities",
    tags=["opportunities"],
    dependencies=[Depends(require_user)],
)

_RELATIVE_DISCOVERY_TYPES = {"new_vs_previous", "reappeared", "continued"}
_FROZEN_DISCOVERY_TYPES = {"new_vs_previous", "first_seen", "reappeared"}


def _ensure_collection_history_available(
    db: Session,
    collection_run_id: str | None,
) -> CollectionRun | None:
    if not collection_run_id:
        return None
    run = db.get(CollectionRun, collection_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    if not run.detailed_observations_available:
        raise HTTPException(
            status_code=410,
            detail=(
                "COLLECTION_OBSERVATIONS_EXPIRED: As observações detalhadas desta "
                "coleta expiraram pela política de retenção."
            ),
        )
    return run


def _ensure_collection_exists(db: Session, collection_run_id: str | None) -> None:
    if collection_run_id and db.get(CollectionRun, collection_run_id) is None:
        raise HTTPException(status_code=404, detail="Collection run not found")


def _comparison_context(
    db: Session,
    target: CollectionRun | None,
    discovery_type: str | None,
) -> tuple[str | None, bool]:
    if discovery_type not in _RELATIVE_DISCOVERY_TYPES:
        return None, True
    if target is None:
        raise HTTPException(
            status_code=422,
            detail="collection_run_id is required for relative discovery filters",
        )
    if target.status != CollectionRunStatus.SUCCESS:
        raise HTTPException(
            status_code=422,
            detail="Relative discovery filters require a SUCCESS CollectionRun",
        )
    baseline = previous_comparable_run(db, target)
    if baseline is None or not baseline.detailed_observations_available:
        return None, False
    return baseline.id, True


def _frozen_context(db: Session, token: str, discovery_type: str | None):
    if discovery_type not in _FROZEN_DISCOVERY_TYPES:
        raise HTTPException(
            status_code=422,
            detail="comparison_context requires new_vs_previous, first_seen or reappeared",
        )
    try:
        return resolve_comparison_context(db, token)
    except ComparisonContextError as exc:
        status_code = 410 if exc.code == "CONTEXT_EXPIRED" else 422
        raise HTTPException(status_code=status_code, detail=f"{exc.code}: {exc}") from exc


def _validate_temporal_range(
    start: datetime | None,
    end: datetime | None,
    *,
    label: str,
) -> None:
    if start is not None and end is not None and start >= end:
        raise HTTPException(
            status_code=422,
            detail=f"{label}_from must be earlier than {label}_to",
        )


def _filters(
    provider: str | None,
    account_id: str | None,
    region: str | None,
    service: str | None,
    resource_type: str | None,
    status: str | None,
    presence_status: str | None,
    severity: str | None,
    rule: str | None,
    collection_run_id: str | None,
    first_seen_collection_run_id: str | None,
    discovery_type: str | None,
    baseline_collection_run_id: str | None,
    comparison_available: bool,
    resource_id: str | None,
    search: str | None,
    first_seen_from: datetime | None,
    first_seen_to: datetime | None,
    last_seen_from: datetime | None,
    last_seen_to: datetime | None,
    current: bool,
    archive_state: OpportunityArchiveState,
    archived_from: datetime | None,
    archived_to: datetime | None,
    archive_reason: str | None,
) -> OpportunityFilters:
    _validate_temporal_range(first_seen_from, first_seen_to, label="first_seen")
    _validate_temporal_range(last_seen_from, last_seen_to, label="last_seen")
    return OpportunityFilters(
        provider=provider.lower() if provider else None,
        account_id=account_id,
        region=region,
        service=service,
        resource_type=resource_type,
        status=status,
        presence_status=presence_status,
        severity=severity,
        rule=rule,
        collection_run_id=collection_run_id,
        first_seen_collection_run_id=first_seen_collection_run_id,
        discovery_type=discovery_type,
        baseline_collection_run_id=baseline_collection_run_id,
        comparison_available=comparison_available,
        resource_id=resource_id,
        search=search,
        first_seen_from=first_seen_from,
        first_seen_to=first_seen_to,
        last_seen_from=last_seen_from,
        last_seen_to=last_seen_to,
        current=current,
        archive_state=archive_state,
        archived_from=archived_from,
        archived_to=archived_to,
        archive_reason=archive_reason,
    )


def _archive_filters(scope: OpportunityArchiveFilterScope) -> OpportunityFilters:
    return OpportunityFilters(
        provider=scope.provider.lower() if scope.provider else None,
        account_id=scope.account_id,
        region=scope.region,
        service=scope.service,
        resource_type=scope.resource_type,
        status=scope.status,
        presence_status=scope.presence_status.value if scope.presence_status else None,
        severity=scope.severity,
        rule=scope.rule,
        collection_run_id=scope.collection_run_id,
        resource_id=scope.resource_id,
        search=scope.search,
        current=scope.current,
        archive_state="active",
    )


def _comparison_filters(
    provider: str | None,
    account_id: str | None,
    region: str | None,
    service: str | None,
    resource_type: str | None,
    status: str | None,
    presence_status: str | None,
    severity: str | None,
    rule: str | None,
    resource_id: str | None,
    search: str | None,
    first_seen_from: datetime | None,
    first_seen_to: datetime | None,
    last_seen_from: datetime | None,
    last_seen_to: datetime | None,
    archive_state: OpportunityArchiveState,
    archived_from: datetime | None,
    archived_to: datetime | None,
    archive_reason: str | None,
) -> OpportunityFilters:
    return _filters(
        provider,
        account_id,
        region,
        service,
        resource_type,
        status,
        presence_status,
        severity,
        rule,
        None,
        None,
        None,
        None,
        True,
        resource_id,
        search,
        first_seen_from,
        first_seen_to,
        last_seen_from,
        last_seen_to,
        False,
        archive_state,
        archived_from,
        archived_to,
        archive_reason,
    )


@router.get("", response_model=OpportunityPage)
def list_opportunity_page(
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    service: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    opportunity_status: OpportunityStatus | None = Query(default=None, alias="status"),
    presence_status: OpportunityPresenceStatus | None = None,
    severity: OpportunitySeverity | None = None,
    rule: str | None = None,
    collection_run_id: str | None = Query(default=None, max_length=36),
    first_seen_collection_run_id: str | None = Query(default=None, max_length=36),
    discovery_type: str | None = Query(
        default=None, pattern="^(observed|first_seen|new_vs_previous|reappeared|continued)$"
    ),
    comparison_context: str | None = Query(default=None, max_length=8192),
    resource_id: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    first_seen_from: datetime | None = None,
    first_seen_to: datetime | None = None,
    last_seen_from: datetime | None = None,
    last_seen_to: datetime | None = None,
    current: bool = False,
    archive_state: OpportunityArchiveState = "active",
    archived_from: datetime | None = None,
    archived_to: datetime | None = None,
    archive_reason: str | None = Query(default=None, pattern="^(MANUAL|RETENTION_POLICY)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: OpportunitySort = "last_seen_at",
    order: SortOrder = "desc",
    db: Session = Depends(get_db),
) -> dict:
    if comparison_context:
        if collection_run_id or first_seen_collection_run_id:
            raise HTTPException(
                status_code=422, detail="comparison_context cannot be combined with run filters"
            )
        contexts = _frozen_context(db, comparison_context, discovery_type)
        filters = _comparison_filters(
            provider,
            account_id,
            region,
            service,
            resource_type,
            opportunity_status,
            presence_status.value if presence_status else None,
            severity,
            rule,
            resource_id,
            search,
            first_seen_from,
            first_seen_to,
            last_seen_from,
            last_seen_to,
            archive_state,
            archived_from,
            archived_to,
            archive_reason,
        )
        return list_dashboard_comparison_opportunities(
            db,
            filters,
            contexts,
            discovery_type=discovery_type,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )

    target = _ensure_collection_history_available(db, collection_run_id)
    _ensure_collection_exists(db, first_seen_collection_run_id)
    baseline_id, comparison_available = _comparison_context(db, target, discovery_type)
    filters = _filters(
        provider,
        account_id,
        region,
        service,
        resource_type,
        opportunity_status,
        presence_status.value if presence_status else None,
        severity,
        rule,
        collection_run_id,
        first_seen_collection_run_id,
        discovery_type,
        baseline_id,
        comparison_available,
        resource_id,
        search,
        first_seen_from,
        first_seen_to,
        last_seen_from,
        last_seen_to,
        current,
        archive_state,
        archived_from,
        archived_to,
        archive_reason,
    )
    return list_opportunities(db, filters, page=page, page_size=page_size, sort=sort, order=order)


@router.get("/stats", response_model=OpportunityStats)
def stats(
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    service: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    presence_status: OpportunityPresenceStatus | None = None,
    severity: OpportunitySeverity | None = None,
    rule: str | None = None,
    collection_run_id: str | None = Query(default=None, max_length=36),
    first_seen_collection_run_id: str | None = Query(default=None, max_length=36),
    discovery_type: str | None = Query(
        default=None, pattern="^(observed|first_seen|new_vs_previous|reappeared|continued)$"
    ),
    comparison_context: str | None = Query(default=None, max_length=8192),
    resource_id: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    first_seen_from: datetime | None = None,
    first_seen_to: datetime | None = None,
    last_seen_from: datetime | None = None,
    last_seen_to: datetime | None = None,
    current: bool = False,
    archive_state: OpportunityArchiveState = "active",
    archived_from: datetime | None = None,
    archived_to: datetime | None = None,
    archive_reason: str | None = Query(default=None, pattern="^(MANUAL|RETENTION_POLICY)$"),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if comparison_context:
        if collection_run_id or first_seen_collection_run_id:
            raise HTTPException(
                status_code=422, detail="comparison_context cannot be combined with run filters"
            )
        contexts = _frozen_context(db, comparison_context, discovery_type)
        filters = _comparison_filters(
            provider,
            account_id,
            region,
            service,
            resource_type,
            None,
            presence_status.value if presence_status else None,
            severity,
            rule,
            resource_id,
            search,
            first_seen_from,
            first_seen_to,
            last_seen_from,
            last_seen_to,
            archive_state,
            archived_from,
            archived_to,
            archive_reason,
        )
        return dashboard_comparison_stats(db, filters, contexts, discovery_type=discovery_type)

    target = _ensure_collection_history_available(db, collection_run_id)
    _ensure_collection_exists(db, first_seen_collection_run_id)
    baseline_id, comparison_available = _comparison_context(db, target, discovery_type)
    filters = _filters(
        provider,
        account_id,
        region,
        service,
        resource_type,
        None,
        presence_status.value if presence_status else None,
        severity,
        rule,
        collection_run_id,
        first_seen_collection_run_id,
        discovery_type,
        baseline_id,
        comparison_available,
        resource_id,
        search,
        first_seen_from,
        first_seen_to,
        last_seen_from,
        last_seen_to,
        current,
        archive_state,
        archived_from,
        archived_to,
        archive_reason,
    )
    return opportunity_stats(db, filters)


@router.get("/options", response_model=OpportunityOptions)
def options(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=255),
    archive_state: OpportunityArchiveState = "active",
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    return opportunity_options(
        db,
        provider=provider,
        account_id=account_id,
        search=search,
        archive_state=archive_state,
        limit=limit,
    )


def _bulk_result(requested: int, updated_ids: list[str]) -> dict:
    return {
        "requested": requested,
        "updated": len(updated_ids),
        "failed": 0,
        "updated_ids": updated_ids,
        "errors": [],
    }


def _run_bulk(
    payload: BulkTransitionBase, db: Session, actor: User, *, action: str, reason: str | None = None
) -> dict:
    try:
        findings = bulk_transition(
            db, payload.opportunity_ids, actor, action=action, reason=reason, note=payload.note
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _bulk_result(len(findings), [finding.id for finding in findings])


@router.post(
    "/bulk/treat", response_model=BulkTransitionResult, dependencies=[Depends(require_operator)]
)
def bulk_treat(
    payload: BulkTransitionBase,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _run_bulk(payload, db, actor, action="treat")


@router.post(
    "/bulk/reject", response_model=BulkTransitionResult, dependencies=[Depends(require_operator)]
)
def bulk_reject(
    payload: BulkReject, db: Session = Depends(get_db), actor: User = Depends(require_operator)
) -> dict:
    return _run_bulk(payload, db, actor, action="reject", reason=payload.reason)


@router.post(
    "/bulk/reopen", response_model=BulkTransitionResult, dependencies=[Depends(require_operator)]
)
def bulk_reopen(
    payload: BulkTransitionBase,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _run_bulk(payload, db, actor, action="reopen")


@router.post(
    "/bulk/archive", response_model=ArchiveOperationResult, dependencies=[Depends(require_operator)]
)
def bulk_archive_opportunities(
    payload: BulkArchiveRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    try:
        result = bulk_archive(db, payload.opportunity_ids, actor)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post(
    "/archive-preview",
    response_model=ArchivePreviewResult,
    dependencies=[Depends(require_operator)],
)
def preview_archive_scope(payload: ArchiveScopeRequest, db: Session = Depends(get_db)) -> dict:
    return archive_preview(db, _archive_filters(payload.filters), archive_all=payload.archive_all)


@router.post(
    "/archive-by-filter",
    response_model=ArchiveOperationResult,
    dependencies=[Depends(require_operator)],
)
def archive_matching_opportunities(
    payload: ArchiveScopeRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    try:
        result = archive_by_filter(
            db, _archive_filters(payload.filters), actor, archive_all=payload.archive_all
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post(
    "/period-close", response_model=PeriodCloseResult, dependencies=[Depends(require_admin)]
)
def close_operational_period(
    payload: PeriodCloseRequest, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> dict:
    try:
        result = close_period_and_archive(
            db,
            cycle_id=payload.cycle_id,
            filters=_archive_filters(payload.filters),
            archive_all=payload.archive_all,
            actor=actor,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
def detail(opportunity_id: str, db: Session = Depends(get_db)) -> dict:
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@router.get("/{opportunity_id}/history", response_model=ObservationPage)
def history(
    opportunity_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = observation_history(db, opportunity_id, page=page, page_size=page_size)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return result


@router.get("/{opportunity_id}/status-history", response_model=StatusHistoryPage)
def decision_history(
    opportunity_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = status_history(db, opportunity_id, page=page, page_size=page_size)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return result


@router.get("/{opportunity_id}/presence-history", response_model=PresenceHistoryPage)
def technical_presence_history(
    opportunity_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = presence_history(db, opportunity_id, page=page, page_size=page_size)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return result


@router.get("/{opportunity_id}/archive-history", response_model=ArchiveHistoryPage)
def operational_archive_history(
    opportunity_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    result = archive_history(db, opportunity_id, page=page, page_size=page_size)
    if result is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return result


@router.post(
    "/{opportunity_id}/archive",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_operator)],
)
def archive_opportunity(
    opportunity_id: str, db: Session = Depends(get_db), actor: User = Depends(require_operator)
) -> dict:
    try:
        archive(db, opportunity_id, actor)
        db.commit()
    except Exception:
        db.rollback()
        raise
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@router.post(
    "/{opportunity_id}/unarchive",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_operator)],
)
def unarchive_opportunity(
    opportunity_id: str, db: Session = Depends(get_db), actor: User = Depends(require_operator)
) -> dict:
    unarchive(db, opportunity_id, actor)
    db.commit()
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@router.post(
    "/{opportunity_id}/treat",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_operator)],
)
def treat_opportunity(
    opportunity_id: str,
    payload: OpportunityNote,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    treat(db, opportunity_id, actor, payload.note)
    db.commit()
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@router.post(
    "/{opportunity_id}/reject",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_operator)],
)
def reject_opportunity(
    opportunity_id: str,
    payload: OpportunityReject,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    reject(db, opportunity_id, actor, payload.reason, payload.note)
    db.commit()
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@router.post(
    "/{opportunity_id}/reopen",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_operator)],
)
def reopen_opportunity(
    opportunity_id: str,
    payload: OpportunityNote,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    reopen(db, opportunity_id, actor, payload.note)
    db.commit()
    item = get_opportunity(db, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item
