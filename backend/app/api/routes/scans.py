from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_operator, require_user
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.scan import Scan
from app.schemas.scan import ScanCreate, ScanRead

router = APIRouter(prefix="/scans", tags=["scans"], dependencies=[Depends(require_user)])


@router.get("", response_model=list[ScanRead])
def list_scans(
    account_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Scan]:
    statement = select(Scan).order_by(Scan.created_at.desc()).limit(limit)
    if account_id is not None:
        statement = statement.where(Scan.account_id == account_id)
    return list(db.scalars(statement))


@router.post(
    "",
    response_model=ScanRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_operator)],
)
def create_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> Scan:
    account = db.get(AwsAccount, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="AWS account not found")
    if not account.enabled:
        raise HTTPException(status_code=409, detail="AWS account is disabled")
    pending = db.scalar(
        select(Scan).where(
            Scan.account_id == payload.account_id, Scan.status.in_(["pending", "running"])
        )
    )
    if pending:
        raise HTTPException(status_code=409, detail="A scan is already pending or running")
    scan = Scan(account_id=payload.account_id, trigger="manual")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


@router.get("/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: str, db: Session = Depends(get_db)) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
