from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.services.rds_reservation_opportunities import (
    generate_rds_reservation_opportunities,
    rds_reservation_opportunity_summary,
)

router = APIRouter(
    prefix="/rds/reservation-opportunities",
    tags=["rds-reservation-opportunities"],
    dependencies=[Depends(require_admin)],
)


@router.post("/run")
def generate_opportunities(
    coverage_run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = generate_rds_reservation_opportunities(db, coverage_run_id=coverage_run_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return result.to_dict()


@router.get("/summary")
def get_summary(
    coverage_run_id: int | None = Query(default=None, ge=1),
    account: str | None = Query(default=None, max_length=12),
    region: str | None = Query(default=None, max_length=32),
    engine: str | None = Query(default=None, max_length=64),
    family: str | None = Query(default=None, max_length=32),
    instance_class: str | None = Query(default=None, max_length=64),
    opportunity_status: str | None = Query(default=None, pattern="^(open|treated|rejected)$"),
    severity: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return rds_reservation_opportunity_summary(
            db,
            coverage_run_id=coverage_run_id,
            account=account,
            region=region,
            engine=engine,
            family=family,
            instance_class=instance_class,
            opportunity_status=opportunity_status,
            severity=severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
