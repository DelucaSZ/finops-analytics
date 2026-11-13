"""Administrative read-only AWS catalog and controlled manual synchronization API.

Financial writes remain exclusively in the official 28.3 importer. No AWS calls
are made by catalog GET handlers or the HTTP sync submission handler.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import require_admin, require_recent_admin
from app.db.session import get_db
from app.models.aws_pricing import (
    AwsPricingProduct,
    AwsPricingRateDetail,
    AwsPricingSyncRequest,
    AwsPricingSyncRun,
    AwsPricingSyncState,
)
from app.models.pricing import PricingCatalogItem
from app.models.user import User
from app.services.aws_pricing_sync import (
    AwsPricingSynchronizer,
    _services,
    coverage_report,
    discover_regions,
)

router = APIRouter(
    prefix="/pricing/aws",
    tags=["pricing"],
    dependencies=[Depends(require_admin)],
)
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
RateStatus = Literal[
    "active", "all", "unsupported", "quarantined", "withdrawn", "expired", "future"
]


class SyncSubmission(BaseModel):
    service_code: str = Field(min_length=1, max_length=80)
    region_code: str = Field(min_length=1, max_length=40)
    dry_run: bool = False
    force: bool = False


def _bad(code: str, message: str, http_status: int = 400) -> HTTPException:
    return HTTPException(http_status, detail={"code": code, "message": message})


def _validate(service: str | None, region: str | None) -> None:
    if service is not None and service not in _services(settings.aws_pricing_sync_services):
        raise _bad("service_invalid", "Unsupported or disabled AWS pricing service")
    if region is not None and not _REGION.fullmatch(region):
        raise _bad("region_invalid", "Invalid AWS commercial region")


def _time(at: datetime | None) -> datetime:
    if at is not None and at.tzinfo is None:
        raise _bad("date_invalid", "Reference date must include a timezone")
    return at.astimezone(UTC) if at else datetime.now(UTC)


def _iso(date: datetime | None) -> str | None:
    return date.isoformat() if date else None


def _rate(row: tuple[PricingCatalogItem, AwsPricingRateDetail, AwsPricingProduct]) -> dict:
    item, detail, product = row
    return {
        "id": item.id,
        "service": product.service,
        "service_code": product.service_code,
        "region_code": product.region_code,
        "product_sku": product.product_sku,
        "product_family": product.product_family,
        "description": product.description,
        "product_attributes": product.product_attributes,
        "financial_attributes": product.financial_attributes,
        "rate_code": detail.rate_code,
        "term_code": detail.term_code,
        "purchase_option": detail.purchase_option,
        "offer_term": detail.term_code,
        "billing_unit": detail.billing_unit_aws,
        "unit": item.unit,
        "begin_range": detail.begin_range,
        "end_range": detail.end_range,
        "rate_description": detail.rate_description,
        "pricing_status": detail.pricing_status,
        "price": format(item.price, "f"),
        "currency": item.currency,
        "effective_from": _iso(item.effective_from),
        "effective_until": _iso(item.effective_until),
        "enabled": item.enabled,
        "source": item.source,
        "source_effective_at": _iso(detail.source_effective_at),
        "synced_at": _iso(detail.synced_at),
        "import_batch_id": detail.import_batch_id,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _rate_query():
    return (
        select(PricingCatalogItem, AwsPricingRateDetail, AwsPricingProduct)
        .join(
            AwsPricingRateDetail,
            AwsPricingRateDetail.pricing_item_id == PricingCatalogItem.id,
        )
        .join(
            AwsPricingProduct,
            AwsPricingProduct.id == AwsPricingRateDetail.product_id,
        )
        .where(PricingCatalogItem.provider == "aws", PricingCatalogItem.currency == "USD")
    )


def _paged(db: Session, statement, *, limit: int, offset: int) -> dict:
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.limit(limit).offset(offset)).all()
    return {"items": [_rate(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/meta")
def metadata(
    db: Session = Depends(get_db),
) -> dict:
    _validate(None, None)
    regions = set(discover_regions(db, settings.aws_pricing_sync_extra_regions))
    regions.update(db.scalars(select(AwsPricingProduct.region_code).distinct()))
    regions.update(db.scalars(select(AwsPricingSyncState.region_code).distinct()))
    services = set(_services(settings.aws_pricing_sync_services))
    services.update(db.scalars(select(AwsPricingProduct.service_code).distinct()))
    return {
        "provider": "aws",
        "currency": "USD",
        "source": "AWS_PUBLIC_PRICE_LIST",
        "regions": sorted(regions),
        "services": sorted(services),
        "import_enabled": os.environ.get("AVEN_AWS_PRICING_IMPORT_ENABLED") == "1",
    }


@router.get("/products")
def products(
    region: str = Query(min_length=1, max_length=40),
    service: str | None = Query(default=None, max_length=80),
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _validate(service, region)
    statement = select(AwsPricingProduct).where(AwsPricingProduct.region_code == region)
    if service:
        statement = statement.where(AwsPricingProduct.service_code == service)
    if q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                AwsPricingProduct.product_sku.ilike(like),
                AwsPricingProduct.description.ilike(like),
                AwsPricingProduct.product_family.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(AwsPricingProduct.product_sku).limit(limit).offset(offset))
    return {
        "items": [
            {
                "id": row.id,
                "service_code": row.service_code,
                "service": row.service,
                "region_code": row.region_code,
                "sku": row.product_sku,
                "family": row.product_family,
                "description": row.description,
                "attributes": row.product_attributes,
                "status": row.status,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/rates")
def rates(
    region: str = Query(min_length=1, max_length=40),
    service: str | None = Query(default=None, max_length=80),
    q: str = Query(default="", max_length=160),
    pricing_status: Annotated[RateStatus, Query(alias="status")] = "active",
    at: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _validate(service, region)
    moment = _time(at)
    stmt = _rate_query().where(AwsPricingProduct.region_code == region)
    if service:
        stmt = stmt.where(AwsPricingProduct.service_code == service)
    if pricing_status == "active":
        stmt = stmt.where(
            PricingCatalogItem.enabled.is_(True),
            AwsPricingRateDetail.pricing_status == "active",
            PricingCatalogItem.effective_from <= moment,
            or_(
                PricingCatalogItem.effective_until.is_(None),
                PricingCatalogItem.effective_until > moment,
            ),
        )
    elif pricing_status == "expired":
        stmt = stmt.where(PricingCatalogItem.effective_until <= moment)
    elif pricing_status == "future":
        stmt = stmt.where(PricingCatalogItem.effective_from > moment)
    elif pricing_status != "all":
        stmt = stmt.where(AwsPricingRateDetail.pricing_status == pricing_status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                AwsPricingProduct.product_sku.ilike(like),
                AwsPricingRateDetail.rate_code.ilike(like),
                AwsPricingProduct.description.ilike(like),
                AwsPricingProduct.product_family.ilike(like),
                AwsPricingProduct.service.ilike(like),
                AwsPricingRateDetail.rate_description.ilike(like),
                cast(AwsPricingProduct.product_attributes, String).ilike(like),
            )
        )
    stmt = stmt.order_by(
        AwsPricingProduct.service_code,
        AwsPricingProduct.product_sku,
        AwsPricingRateDetail.rate_code,
        PricingCatalogItem.effective_from.desc(),
    )
    return _paged(db, stmt, limit=limit, offset=offset)


def _get_rate(db: Session, rate_id: str):
    record = db.execute(_rate_query().where(PricingCatalogItem.id == rate_id)).first()
    if record is None:
        raise _bad("rate_not_found", "AWS rate not found", 404)
    return record


@router.get("/rates/{rate_id}")
def rate_detail(rate_id: str, db: Session = Depends(get_db)) -> dict:
    return _rate(_get_rate(db, rate_id))


@router.get("/rates/{rate_id}/history")
def rate_history(
    rate_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    item, detail, product = _get_rate(db, rate_id)
    stmt = (
        _rate_query()
        .where(
            AwsPricingProduct.service_code == product.service_code,
            AwsPricingProduct.region_code == product.region_code,
            AwsPricingProduct.product_sku == product.product_sku,
            AwsPricingRateDetail.rate_code == detail.rate_code,
            PricingCatalogItem.sku == item.sku,
            PricingCatalogItem.unit == item.unit,
        )
        .order_by(PricingCatalogItem.effective_from.desc())
    )
    return _paged(db, stmt, limit=limit, offset=offset)


@router.get("/sync/status")
def sync_status(
    service: str | None = Query(default=None, max_length=80),
    region: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    _validate(service, region)
    synchronizer = AwsPricingSynchronizer(
        session_factory=sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    )
    return {"items": synchronizer.status(service=service, region=region, limit=limit)}


@router.get("/sync/coverage")
def coverage(
    service: str = Query(min_length=1, max_length=80),
    region: str = Query(min_length=1, max_length=40),
    db: Session = Depends(get_db),
) -> dict:
    _validate(service, region)
    report = coverage_report(db, service, region)
    return {"service_code": service, "region_code": region, **report}


def _run(run: AwsPricingSyncRun) -> dict:
    return {
        "id": run.id,
        "service_code": run.service_code,
        "region_code": run.region_code,
        "trigger": run.trigger,
        "status": run.status,
        "attempt": run.attempt,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "next_retry_at": _iso(run.next_retry_at),
        "source_reference": run.source_reference,
        "source_version": run.source_version,
        "batch_id": run.batch_id,
        "products_seen": run.products_seen,
        "rates_seen": run.rates_seen,
        "rates_published": run.rates_published,
        "rates_rejected": run.rates_rejected,
        "metrics": run.metrics,
        "coverage": run.coverage,
        "error_code": run.error_code,
        "error_summary": run.error_summary,
    }


@router.get("/sync/runs")
def sync_runs(
    service: str | None = Query(default=None, max_length=80),
    region: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    _validate(service, region)
    stmt = select(AwsPricingSyncRun)
    if service:
        stmt = stmt.where(AwsPricingSyncRun.service_code == service)
    if region:
        stmt = stmt.where(AwsPricingSyncRun.region_code == region)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AwsPricingSyncRun.started_at.desc(), AwsPricingSyncRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {"items": [_run(x) for x in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/sync/runs/{run_id}")
def sync_run_detail(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(AwsPricingSyncRun, run_id)
    if run is None:
        raise _bad("run_not_found", "AWS pricing synchronization run not found", 404)
    return _run(run)


def _request(row: AwsPricingSyncRequest) -> dict:
    return {
        "id": row.id,
        "service_code": row.service_code,
        "region_code": row.region_code,
        "status": row.status,
        "dry_run": row.dry_run,
        "force": row.force,
        "requested_at": _iso(row.requested_at),
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "result": row.result,
        "error_code": row.error_code,
    }


@router.get("/sync/requests/{request_id}")
def sync_request_detail(request_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(AwsPricingSyncRequest, request_id)
    if row is None:
        raise _bad("request_not_found", "AWS pricing sync request not found", 404)
    return _request(row)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def submit_sync(
    payload: SyncSubmission,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> dict:
    _validate(payload.service_code, payload.region_code)
    if os.environ.get("AVEN_AWS_PRICING_IMPORT_ENABLED") != "1":
        raise _bad("import_disabled", "Official AWS pricing imports are disabled", 409)
    # Only configured/observed regions may be selected through the UI.
    known = set(discover_regions(db, settings.aws_pricing_sync_extra_regions))
    known.update(db.scalars(select(AwsPricingProduct.region_code).distinct()))
    known.update(db.scalars(select(AwsPricingSyncState.region_code).distinct()))
    if payload.region_code not in known:
        raise _bad("region_not_configured", "AWS pricing region is not configured")
    exists = db.scalar(
        select(AwsPricingSyncRequest.id)
        .where(
            AwsPricingSyncRequest.service_code == payload.service_code,
            AwsPricingSyncRequest.region_code == payload.region_code,
            AwsPricingSyncRequest.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    if exists is not None:
        raise _bad("sync_busy", "AWS pricing synchronization already queued or running", 409)
    row = AwsPricingSyncRequest(
        service_code=payload.service_code,
        region_code=payload.region_code,
        requested_by=actor.id,
        dry_run=payload.dry_run,
        force=payload.force,
        status="queued",
        requested_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _bad("sync_busy", "Concurrent AWS pricing synchronization request", 409) from exc
    db.refresh(row)
    return _request(row)
