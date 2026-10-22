from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.schemas.opportunity import OpportunityStatus
from app.schemas.opportunity_discovery import (
    DiscoveryType,
    OpportunityRunChanges,
    RunOpportunityPage,
)
from app.services.opportunity_run_comparison import (
    list_run_opportunities,
    opportunity_run_changes,
)

router = APIRouter(
    prefix="/collections",
    tags=["opportunity-discovery"],
    dependencies=[Depends(require_user)],
)


def _target_run(db: Session, collection_run_id: str) -> CollectionRun:
    run = db.get(CollectionRun, collection_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    return run


@router.get("/{collection_run_id}/opportunity-changes", response_model=OpportunityRunChanges)
def opportunity_changes(
    collection_run_id: str,
    db: Session = Depends(get_db),
) -> dict:
    return opportunity_run_changes(db, _target_run(db, collection_run_id))


@router.get("/{collection_run_id}/opportunities", response_model=RunOpportunityPage)
def opportunities_for_run(
    collection_run_id: str,
    discovery_type: DiscoveryType = "observed",
    opportunity_status: OpportunityStatus | None = Query(default=None, alias="status"),
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return list_run_opportunities(
        db,
        _target_run(db, collection_run_id),
        discovery_type=discovery_type,
        page=page,
        page_size=page_size,
        status=opportunity_status,
        include_archived=include_archived,
    )
