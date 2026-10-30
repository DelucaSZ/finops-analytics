from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.services.rds_reservations_pipeline import (
    RdsReservationsPipelineBusy,
    get_rds_reservations_operational_status,
    refresh_rds_reservations,
)

router = APIRouter(
    prefix="/rds/reservations",
    tags=["rds-reservations-pipeline"],
    dependencies=[Depends(require_admin)],
)


@router.post("/refresh")
def refresh(
    cloud_account_id: int | None = Query(default=None, ge=1),
    validate_billing: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return refresh_rds_reservations(
            db,
            cloud_account_id=cloud_account_id,
            validate_billing=validate_billing,
        )
    except RdsReservationsPipelineBusy as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RDS_RESERVATIONS_REFRESH_RUNNING",
                "message": str(exc),
            },
        ) from exc


@router.get("/operational-status")
def operational_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_rds_reservations_operational_status(db)
