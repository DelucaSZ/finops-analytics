from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.opportunity_history import (
    OpportunityHistoryCyclePage,
    OpportunityHistoryCycleRead,
    OpportunityHistorySnapshotPage,
    OpportunityHistorySnapshotRead,
    SnapshotSort,
    SortOrder,
)
from app.services.opportunity_history import (
    OpportunityHistoryCycleService,
    cycle_payload,
    get_cycle,
    get_snapshot,
    list_cycles,
    list_snapshots,
)

router = APIRouter(
    prefix="/opportunity-history",
    tags=["opportunity-history"],
    dependencies=[Depends(require_user)],
)


@router.get("/cycles", response_model=OpportunityHistoryCyclePage)
def cycles(db: Session = Depends(get_db)) -> dict:
    return list_cycles(db)


@router.get("/cycles/current", response_model=OpportunityHistoryCycleRead)
def current_cycle(db: Session = Depends(get_db)) -> dict:
    cycle = OpportunityHistoryCycleService.get_or_create_cycle_for(db, datetime.now(UTC))
    db.commit()
    db.refresh(cycle)
    return cycle_payload(db, cycle)


@router.get("/cycles/{cycle_id}", response_model=OpportunityHistoryCycleRead)
def cycle_detail(cycle_id: str, db: Session = Depends(get_db)) -> dict:
    return cycle_payload(db, get_cycle(db, cycle_id))


@router.post(
    "/cycles/{cycle_id}/close",
    response_model=OpportunityHistoryCycleRead,
    dependencies=[Depends(require_admin)],
)
def close_cycle(
    cycle_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    try:
        cycle = OpportunityHistoryCycleService.close_cycle(
            db,
            cycle_id,
            actor=actor,
            close_reason="MANUAL",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(cycle)
    return cycle_payload(db, cycle)


@router.get("/snapshots", response_model=OpportunityHistorySnapshotPage)
def snapshots(
    cycle_id: str = Query(..., min_length=1),
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
    severity: str | None = Query(default=None, pattern="^(low|medium|high)$"),
    rule: str | None = Query(default=None, max_length=80),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: SnapshotSort = "estimated_savings",
    order: SortOrder = "desc",
    db: Session = Depends(get_db),
) -> dict:
    return list_snapshots(
        db,
        cycle_id=cycle_id,
        provider=provider,
        account_id=account_id,
        region=region,
        service=service,
        resource_type=resource_type,
        status=status,
        presence_status=presence_status,
        severity=severity,
        rule=rule,
        search=search,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


@router.get("/snapshots/{snapshot_id}", response_model=OpportunityHistorySnapshotRead)
def snapshot_detail(snapshot_id: str, db: Session = Depends(get_db)) -> dict:
    return get_snapshot(db, snapshot_id)
