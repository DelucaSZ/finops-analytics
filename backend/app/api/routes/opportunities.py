from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_operator, require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.finding import OpportunityNote, OpportunityReject
from app.schemas.opportunity import (
    BulkReject,
    BulkTransitionBase,
    BulkTransitionResult,
    ObservationPage,
    OpportunityDetail,
    OpportunityPage,
    OpportunitySeverity,
    OpportunitySort,
    OpportunityStats,
    OpportunityStatus,
    SortOrder,
    StatusHistoryPage,
)
from app.services.opportunity_lifecycle import bulk_transition, reject, reopen, treat
from app.services.opportunity_query import (
    OpportunityFilters,
    get_opportunity,
    list_opportunities,
    observation_history,
    opportunity_stats,
    status_history,
)

router = APIRouter(
    prefix="/opportunities",
    tags=["opportunities"],
    dependencies=[Depends(require_user)],
)


def _filters(
    provider: str | None,
    account_id: str | None,
    region: str | None,
    status: str | None,
    severity: str | None,
    rule: str | None,
    collection_run_id: str | None,
    resource_id: str | None,
    search: str | None,
) -> OpportunityFilters:
    return OpportunityFilters(
        provider=provider.lower() if provider else None,
        account_id=account_id,
        region=region,
        status=status,
        severity=severity,
        rule=rule,
        collection_run_id=collection_run_id,
        resource_id=resource_id,
        search=search,
    )


@router.get("", response_model=OpportunityPage)
def list_opportunity_page(
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    opportunity_status: OpportunityStatus | None = Query(default=None, alias="status"),
    severity: OpportunitySeverity | None = None,
    rule: str | None = None,
    collection_run_id: str | None = None,
    resource_id: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: OpportunitySort = "last_seen_at",
    order: SortOrder = "desc",
    db: Session = Depends(get_db),
) -> dict:
    filters = _filters(
        provider,
        account_id,
        region,
        opportunity_status,
        severity,
        rule,
        collection_run_id,
        resource_id,
        search,
    )
    return list_opportunities(
        db,
        filters,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


@router.get("/stats", response_model=OpportunityStats)
def stats(
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    severity: OpportunitySeverity | None = None,
    rule: str | None = None,
    collection_run_id: str | None = None,
    resource_id: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    filters = _filters(
        provider,
        account_id,
        region,
        None,
        severity,
        rule,
        collection_run_id,
        resource_id,
        search,
    )
    return opportunity_stats(db, filters)


def _bulk_result(requested: int, updated_ids: list[str]) -> dict:
    return {
        "requested": requested,
        "updated": len(updated_ids),
        "failed": 0,
        "updated_ids": updated_ids,
        "errors": [],
    }


def _run_bulk(
    payload: BulkTransitionBase,
    db: Session,
    actor: User,
    *,
    action: str,
    reason: str | None = None,
) -> dict:
    try:
        findings = bulk_transition(
            db,
            payload.opportunity_ids,
            actor,
            action=action,
            reason=reason,
            note=payload.note,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _bulk_result(len(findings), [finding.id for finding in findings])


@router.post(
    "/bulk/treat",
    response_model=BulkTransitionResult,
    dependencies=[Depends(require_operator)],
)
def bulk_treat(
    payload: BulkTransitionBase,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _run_bulk(payload, db, actor, action="treat")


@router.post(
    "/bulk/reject",
    response_model=BulkTransitionResult,
    dependencies=[Depends(require_operator)],
)
def bulk_reject(
    payload: BulkReject,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _run_bulk(payload, db, actor, action="reject", reason=payload.reason)


@router.post(
    "/bulk/reopen",
    response_model=BulkTransitionResult,
    dependencies=[Depends(require_operator)],
)
def bulk_reopen(
    payload: BulkTransitionBase,
    db: Session = Depends(get_db),
    actor: User = Depends(require_operator),
) -> dict:
    return _run_bulk(payload, db, actor, action="reopen")


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
