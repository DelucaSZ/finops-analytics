from fastapi import APIRouter, Depends, Query
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
from app.services.dashboard_operational_insights import collection_failure_insights

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_user)],
)


@router.get("/summary", response_model=DashboardSummary)
def summary(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
) -> dict:
    return executive_dashboard_summary(
        db,
        provider=provider.lower() if provider else None,
        account_id=account_id,
    )


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
