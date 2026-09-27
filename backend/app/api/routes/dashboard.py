from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.dashboard import DashboardCollectionHealth, DashboardSummary
from app.services.dashboard import collection_health, dashboard_summary

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
    return dashboard_summary(
        db,
        provider=provider.lower() if provider else None,
        account_id=account_id,
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
