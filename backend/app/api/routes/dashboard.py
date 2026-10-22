from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.dashboard import (
    DashboardCollectionHealth,
    DashboardOperationalInsights,
    DashboardSummary,
)
from app.services.dashboard import collection_health
from app.services.dashboard_executive import executive_dashboard_summary
from app.services.dashboard_new_opportunities import (
    DashboardComparisonContextError,
    dashboard_new_opportunity_stats,
    dashboard_new_since_previous,
    list_dashboard_new_opportunities,
)
from app.services.dashboard_operational_insights import collection_failure_insights
from app.services.opportunity_query import OpportunityFilters

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_user)],
)


def _comparison_filters(
    *,
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
) -> OpportunityFilters:
    if first_seen_from and first_seen_to and first_seen_from >= first_seen_to:
        raise HTTPException(status_code=422, detail="first_seen_from must be earlier than first_seen_to")
    if last_seen_from and last_seen_to and last_seen_from >= last_seen_to:
        raise HTTPException(status_code=422, detail="last_seen_from must be earlier than last_seen_to")
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
        resource_id=resource_id,
        search=search,
        first_seen_from=first_seen_from,
        first_seen_to=first_seen_to,
        last_seen_from=last_seen_from,
        last_seen_to=last_seen_to,
        archive_state="all",
    )


def _raise_comparison_error(exc: DashboardComparisonContextError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=f"{exc.code}: {exc}",
    ) from exc


@router.get("/summary", response_model=DashboardSummary)
def summary(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
) -> dict:
    normalized_provider = provider.lower() if provider else None
    payload = executive_dashboard_summary(
        db,
        provider=normalized_provider,
        account_id=account_id,
    )
    payload["opportunities"]["new_since_previous"] = dashboard_new_since_previous(
        db,
        provider=normalized_provider,
        account_id=account_id,
    )
    return payload


@router.get("/comparison-opportunities")
def comparison_opportunities(
    comparison_context: str = Query(..., min_length=10, max_length=12_000),
    comparison_kind: str = Query(
        default="new_vs_previous",
        pattern="^(new_vs_previous|first_seen|reappeared)$",
    ),
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    region: str | None = Query(default=None, max_length=120),
    service: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, pattern="^(open|treated|rejected)$"),
    presence_status: str | None = Query(
        default=None,
        pattern="^(active|missing|resolved_externally)$",
    ),
    severity: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    rule: str | None = Query(default=None, max_length=255),
    resource_id: str | None = Query(default=None, max_length=512),
    search: str | None = Query(default=None, max_length=200),
    first_seen_from: datetime | None = None,
    first_seen_to: datetime | None = None,
    last_seen_from: datetime | None = None,
    last_seen_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(
        default="last_seen_at",
        pattern="^(created_at|first_seen_at|last_seen_at|archived_at|severity|estimated_savings|status)$",
    ),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> dict:
    filters = _comparison_filters(
        provider=provider,
        account_id=account_id,
        region=region,
        service=service,
        resource_type=resource_type,
        status=status,
        presence_status=presence_status,
        severity=severity,
        rule=rule,
        resource_id=resource_id,
        search=search,
        first_seen_from=first_seen_from,
        first_seen_to=first_seen_to,
        last_seen_from=last_seen_from,
        last_seen_to=last_seen_to,
    )
    try:
        return list_dashboard_new_opportunities(
            db,
            comparison_context=comparison_context,
            comparison_kind=comparison_kind,
            filters=filters,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )
    except DashboardComparisonContextError as exc:
        _raise_comparison_error(exc)


@router.get("/comparison-opportunities/stats")
def comparison_opportunity_stats(
    comparison_context: str = Query(..., min_length=10, max_length=12_000),
    comparison_kind: str = Query(
        default="new_vs_previous",
        pattern="^(new_vs_previous|first_seen|reappeared)$",
    ),
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    region: str | None = Query(default=None, max_length=120),
    service: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    presence_status: str | None = Query(
        default=None,
        pattern="^(active|missing|resolved_externally)$",
    ),
    severity: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    rule: str | None = Query(default=None, max_length=255),
    resource_id: str | None = Query(default=None, max_length=512),
    search: str | None = Query(default=None, max_length=200),
    first_seen_from: datetime | None = None,
    first_seen_to: datetime | None = None,
    last_seen_from: datetime | None = None,
    last_seen_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    filters = _comparison_filters(
        provider=provider,
        account_id=account_id,
        region=region,
        service=service,
        resource_type=resource_type,
        status=None,
        presence_status=presence_status,
        severity=severity,
        rule=rule,
        resource_id=resource_id,
        search=search,
        first_seen_from=first_seen_from,
        first_seen_to=first_seen_to,
        last_seen_from=last_seen_from,
        last_seen_to=last_seen_to,
    )
    try:
        return dashboard_new_opportunity_stats(
            db,
            comparison_context=comparison_context,
            comparison_kind=comparison_kind,
            filters=filters,
        )
    except DashboardComparisonContextError as exc:
        _raise_comparison_error(exc)


@router.get("/operational-insights", response_model=DashboardOperationalInsights)
def operational_insights(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    max_items: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    return collection_failure_insights(
        db,
        provider=provider.lower() if provider else None,
        account_id=account_id,
        max_items=max_items,
    )


@router.get("/collection-health", response_model=DashboardCollectionHealth)
def health(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=8, ge=1, le=25),
    db: Session = Depends(get_db),
) -> dict:
    return collection_health(
        db,
        provider=provider.lower() if provider else None,
        account_id=account_id,
        limit=limit,
    )
