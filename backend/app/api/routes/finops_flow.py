from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.finops_flow import (
    FinOpsFlowBreakdowns,
    FinOpsFlowEntryPage,
    FinOpsFlowEntryRead,
    FinOpsFlowOptions,
    FinOpsFlowSummaryItem,
    FinOpsFlowTimeseriesPoint,
)
from app.schemas.finops_ledger import FinOpsLedgerEntryRead
from app.services.finops_flow import FinOpsFlowAnalyticsService, FinOpsFlowFilters

router = APIRouter(
    prefix="/finops/flow",
    tags=["finops-flow"],
    dependencies=[Depends(require_user)],
)


def _filters(
    *,
    provider: str | None,
    account_id: str | None,
    currency: str | None,
    source: str | None,
    entry_type: str | None,
    periodicity: str | None,
    effective_from: datetime | None,
    effective_to: datetime | None,
    search: str | None = None,
) -> FinOpsFlowFilters:
    if effective_from and effective_to:
        left = effective_from if effective_from.tzinfo else effective_from.replace(tzinfo=effective_to.tzinfo)
        right = effective_to if effective_to.tzinfo else effective_to.replace(tzinfo=effective_from.tzinfo)
        if left >= right:
            raise HTTPException(status_code=422, detail="effective_from must precede effective_to")
    return FinOpsFlowFilters(
        provider=provider,
        account_id=account_id,
        currency=currency,
        source=source,
        entry_type=entry_type,
        periodicity=periodicity,
        effective_from=effective_from,
        effective_to=effective_to,
        search=search,
    )


def _entry_read(item: dict[str, Any]) -> FinOpsFlowEntryRead:
    base = FinOpsLedgerEntryRead.model_validate(item["entry"]).model_dump()
    return FinOpsFlowEntryRead(
        **base,
        account_name=item["account_name"],
        created_by_name=item["created_by_name"],
        opportunity_title=item["opportunity_title"],
        opportunity_service=item["opportunity_service"],
        opportunity_resource_id=item["opportunity_resource_id"],
        logical_entry_type=item["logical_entry_type"],
        logical_source=item["logical_source"],
        is_reversal=item["is_reversal"],
        is_reversed=item["is_reversed"],
        reversed_by_id=item["reversed_by_id"],
    )


def _common_filters(
    provider: str | None,
    account_id: str | None,
    currency: str | None,
    source: str | None,
    entry_type: str | None,
    periodicity: str | None,
    effective_from: datetime | None,
    effective_to: datetime | None,
    search: str | None = None,
) -> FinOpsFlowFilters:
    return _filters(
        provider=provider,
        account_id=account_id,
        currency=currency,
        source=source,
        entry_type=entry_type,
        periodicity=periodicity,
        effective_from=effective_from,
        effective_to=effective_to,
        search=search,
    )


@router.get("/summary", response_model=list[FinOpsFlowSummaryItem])
def summary(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    source: str | None = Query(default=None, max_length=24),
    entry_type: str | None = Query(default=None, max_length=24),
    periodicity: str | None = Query(default=None, max_length=16),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    try:
        return FinOpsFlowAnalyticsService(db).summary(
            _common_filters(
                provider,
                account_id,
                currency,
                source,
                entry_type,
                periodicity,
                effective_from,
                effective_to,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/timeseries", response_model=dict[str, Any])
def timeseries(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    source: str | None = Query(default=None, max_length=24),
    entry_type: str | None = Query(default=None, max_length=24),
    periodicity: str | None = Query(default=None, max_length=16),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        granularity, points = FinOpsFlowAnalyticsService(db).timeseries(
            _common_filters(
                provider,
                account_id,
                currency,
                source,
                entry_type,
                periodicity,
                effective_from,
                effective_to,
            )
        )
        return {
            "granularity": granularity,
            "items": [FinOpsFlowTimeseriesPoint(**point) for point in points],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/breakdowns", response_model=FinOpsFlowBreakdowns)
def breakdowns(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    source: str | None = Query(default=None, max_length=24),
    entry_type: str | None = Query(default=None, max_length=24),
    periodicity: str | None = Query(default=None, max_length=16),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    top_n: int = Query(default=10, ge=1, le=25),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return FinOpsFlowAnalyticsService(db).breakdowns(
            _common_filters(
                provider,
                account_id,
                currency,
                source,
                entry_type,
                periodicity,
                effective_from,
                effective_to,
            ),
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/entries", response_model=FinOpsFlowEntryPage)
def entries(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    source: str | None = Query(default=None, max_length=24),
    entry_type: str | None = Query(default=None, max_length=24),
    periodicity: str | None = Query(default=None, max_length=16),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = FinOpsFlowAnalyticsService(db).list_entries(
            _common_filters(
                provider,
                account_id,
                currency,
                source,
                entry_type,
                periodicity,
                effective_from,
                effective_to,
                search,
            ),
            page=page,
            page_size=page_size,
        )
        return {**result, "items": [_entry_read(item) for item in result["items"]]}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/entries/{entry_id}", response_model=FinOpsFlowEntryRead)
def entry_detail(entry_id: str, db: Session = Depends(get_db)) -> FinOpsFlowEntryRead:
    item = FinOpsFlowAnalyticsService(db).get_entry(entry_id)
    if item is None:
        raise HTTPException(status_code=404, detail="FinOps ledger entry not found")
    return _entry_read(item)


@router.get("/options", response_model=FinOpsFlowOptions)
def options(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    try:
        return FinOpsFlowAnalyticsService(db).options(
            _common_filters(
                provider,
                account_id,
                None,
                None,
                None,
                None,
                effective_from,
                effective_to,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
