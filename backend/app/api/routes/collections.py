from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.schemas.collection import CollectionRunRead

router = APIRouter(
    prefix="/collections",
    tags=["collections"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=list[CollectionRunRead])
def list_collections(
    provider: str | None = None,
    account_id: str | None = None,
    run_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[CollectionRun]:
    statement = select(CollectionRun).order_by(
        CollectionRun.started_at.desc(), CollectionRun.id
    )
    if provider:
        statement = statement.where(CollectionRun.provider == provider.lower())
    if account_id:
        statement = statement.where(CollectionRun.account_id == account_id)
    if run_status:
        statement = statement.where(CollectionRun.status == run_status.upper())
    return list(db.scalars(statement.offset(offset).limit(limit)))


@router.get("/{collection_id}", response_model=CollectionRunRead)
def get_collection(collection_id: str, db: Session = Depends(get_db)) -> CollectionRun:
    run = db.get(CollectionRun, collection_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    return run
