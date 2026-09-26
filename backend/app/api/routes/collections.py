from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.schemas.collection import (
    CollectionComparisonResponse,
    CollectionComparisonRun,
    CollectionRunRead,
    ComparisonCategory,
)
from app.services.collection_comparison import (
    CollectionComparisonError,
    compare_collection_runs,
    compatible_baselines,
)

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
    statement = select(CollectionRun).order_by(CollectionRun.started_at.desc(), CollectionRun.id)
    if provider:
        statement = statement.where(CollectionRun.provider == provider.lower())
    if account_id:
        statement = statement.where(CollectionRun.account_id == account_id)
    if run_status:
        statement = statement.where(CollectionRun.status == run_status.upper())
    return list(db.scalars(statement.offset(offset).limit(limit)))


def _collection_or_404(db: Session, collection_id: str) -> CollectionRun:
    run = db.get(CollectionRun, collection_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    return run


def _comparison_error(exc: CollectionComparisonError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"{exc.code}: {exc}",
    )


@router.get(
    "/{collection_id}/comparison-options",
    response_model=list[CollectionComparisonRun],
)
def comparison_options(
    collection_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    target = _collection_or_404(db, collection_id)
    try:
        baselines = compatible_baselines(db, target, limit=limit)
    except CollectionComparisonError as exc:
        raise _comparison_error(exc) from exc
    return [
        {
            "id": run.id,
            "provider": run.provider,
            "account_id": run.account_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status,
            "rules_version": run.analyzer_version,
        }
        for run in baselines
    ]


@router.get(
    "/{collection_id}/compare",
    response_model=CollectionComparisonResponse,
)
def compare_collection(
    collection_id: str,
    baseline_id: str | None = None,
    category: ComparisonCategory = "NEW",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    target = _collection_or_404(db, collection_id)
    baseline = None
    if baseline_id is not None:
        baseline = _collection_or_404(db, baseline_id)
    try:
        return compare_collection_runs(
            db,
            target,
            baseline=baseline,
            category=category,
            page=page,
            page_size=page_size,
        )
    except CollectionComparisonError as exc:
        raise _comparison_error(exc) from exc


@router.get("/{collection_id}", response_model=CollectionRunRead)
def get_collection(collection_id: str, db: Session = Depends(get_db)) -> CollectionRun:
    return _collection_or_404(db, collection_id)
