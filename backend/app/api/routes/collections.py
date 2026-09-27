from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BeforeValidator
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.models.collection_run import CollectionRun
from app.schemas.collection import (
    CollectionComparisonResponse,
    CollectionComparisonRun,
    CollectionDetail,
    CollectionOptions,
    CollectionPage,
    CollectionRunRead,
    CollectionSort,
    ComparisonCategory,
)
from app.services import collection_query
from app.services.collection_comparison import (
    CollectionComparisonError,
    compare_collection_runs,
    compatible_baselines,
)
from app.services.collection_query import CollectionFilters, utc

router = APIRouter(
    prefix="/collections",
    tags=["collections"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=CollectionPage | list[CollectionRunRead])
def list_collections(
    provider: str | None = Query(default=None, max_length=16),
    account_id: str | None = Query(default=None, max_length=255),
    run_status: Annotated[
        Literal["RUNNING", "SUCCESS", "FAILED"],
        BeforeValidator(lambda value: value.upper() if isinstance(value, str) else value),
    ]
    | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    analyzer_version: str | None = Query(default=None, max_length=80),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    sort: CollectionSort = "started_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """page/page_size returns an envelope; legacy limit/offset keeps its array contract.

    Period is [date_from, date_to), applied to started_at. Naive dates mean UTC.
    """
    if date_from and date_to and utc(date_from) >= utc(date_to):
        raise HTTPException(status_code=422, detail="date_from must precede date_to")
    paged = page is not None or page_size is not None
    result = collection_query.list_collections(
        db,
        CollectionFilters(
            provider=provider.lower() if provider else None,
            account_id=account_id,
            status=run_status,
            date_from=date_from,
            date_to=date_to,
            analyzer_version=analyzer_version,
        ),
        page=page or 1,
        page_size=(page_size or 50) if paged else limit,
        sort=sort,
        order=order,
        offset=None if paged else offset,
    )
    return result if paged else result["items"]


@router.get("/options", response_model=CollectionOptions)
def collection_options(
    provider: str | None = Query(default=None, max_length=16),
    search: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return collection_query.collection_options(
        db, provider=provider.lower() if provider else None, search=search, limit=limit
    )


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


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_collection(collection_id: str, db: Session = Depends(get_db)):
    run = collection_query.get_collection(db, collection_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    return run
