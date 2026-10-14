from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_recent_admin
from app.db.session import get_db
from app.models.pricing import PricingCatalogItem
from app.models.user import User
from app.schemas.pricing import (
    PricingAuditPage,
    PricingCreate,
    PricingDeactivate,
    PricingItemRead,
    PricingListRead,
    PricingMetadataRead,
    PricingStatus,
    PricingUpdate,
)
from app.services.pricing_admin import (
    PricingAdminConflictError,
    PricingAdminError,
    PricingAdminNotFoundError,
    PricingAdminValidationError,
)
from app.services.pricing_audit import AuditedPricingCatalogAdminService

OCI_PROVIDER = "oci"
OCI_CURRENCY = "BRL"
MANUAL_SOURCE = "MANUAL"

router = APIRouter(
    prefix="/pricing/oci",
    tags=["pricing"],
    dependencies=[Depends(require_admin)],
)


def _service(db: Session) -> AuditedPricingCatalogAdminService:
    return AuditedPricingCatalogAdminService(db, provider=OCI_PROVIDER)


def _domain_error(exc: PricingAdminError) -> HTTPException:
    if isinstance(exc, PricingAdminNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, PricingAdminConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, PricingAdminValidationError):
        code = status.HTTP_400_BAD_REQUEST
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _commit(db: Session, item: PricingCatalogItem) -> PricingCatalogItem:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pricing_conflict",
                "message": "A pricing entry conflicts with an existing catalog version.",
            },
        ) from exc
    db.refresh(item)
    return item


@router.get("", response_model=PricingListRead)
def list_oci_pricing(
    q: str = Query(default="", max_length=160),
    service: str | None = Query(default=None, max_length=64),
    pricing_status: Annotated[PricingStatus, Query(alias="status")] = "active",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PricingListRead:
    try:
        items, total = _service(db).list_items(
            q=q,
            service=service,
            status=pricing_status,
            limit=limit,
            offset=offset,
        )
    except PricingAdminError as exc:
        raise _domain_error(exc) from exc
    return PricingListRead(items=items, total=total, limit=limit, offset=offset)


@router.get("/meta", response_model=PricingMetadataRead)
def get_oci_pricing_metadata(db: Session = Depends(get_db)) -> PricingMetadataRead:
    metadata = _service(db).metadata()
    return PricingMetadataRead(
        provider=OCI_PROVIDER,
        currency=OCI_CURRENCY,
        **metadata,
    )


@router.get("/{item_id}", response_model=PricingItemRead)
def get_oci_pricing_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> PricingCatalogItem:
    try:
        return _service(db).get_item(item_id)
    except PricingAdminError as exc:
        raise _domain_error(exc) from exc


@router.get("/{item_id}/history", response_model=list[PricingItemRead])
def get_oci_pricing_history(
    item_id: str,
    db: Session = Depends(get_db),
) -> list[PricingCatalogItem]:
    """Temporal catalog versions. Audit events are intentionally a separate resource."""

    try:
        return _service(db).history(item_id)
    except PricingAdminError as exc:
        raise _domain_error(exc) from exc


@router.get("/{item_id}/audit", response_model=PricingAuditPage)
def get_oci_pricing_audit(
    item_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PricingAuditPage:
    try:
        history = _service(db).audit_history(
            item_id,
            page=page,
            page_size=page_size,
        )
        return PricingAuditPage(**history)
    except PricingAdminError as exc:
        raise _domain_error(exc) from exc


@router.post("", response_model=PricingItemRead, status_code=status.HTTP_201_CREATED)
def create_oci_pricing(
    payload: PricingCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> PricingCatalogItem:
    try:
        item = _service(db).create_item_audited(
            actor=actor,
            reason=payload.reason,
            service=payload.service,
            sku=payload.sku,
            description=payload.description,
            unit=payload.unit,
            price=payload.price,
            currency=OCI_CURRENCY,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            enabled=payload.enabled,
            source=MANUAL_SOURCE,
        )
        return _commit(db, item)
    except PricingAdminError as exc:
        db.rollback()
        raise _domain_error(exc) from exc


@router.patch("/{item_id}", response_model=PricingItemRead)
def update_oci_pricing(
    item_id: str,
    payload: PricingUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> PricingCatalogItem:
    try:
        item = _service(db).update_item_audited(
            item_id,
            actor=actor,
            reason=payload.reason,
            price=payload.price,
            description=payload.description,
            effective_from=payload.effective_from,
            source=MANUAL_SOURCE,
        )
        return _commit(db, item)
    except PricingAdminError as exc:
        db.rollback()
        raise _domain_error(exc) from exc


@router.post("/{item_id}/deactivate", response_model=PricingItemRead)
def deactivate_oci_pricing(
    item_id: str,
    payload: PricingDeactivate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> PricingCatalogItem:
    try:
        item = _service(db).deactivate_audited(item_id, actor=actor, reason=payload.reason)
        return _commit(db, item)
    except PricingAdminError as exc:
        db.rollback()
        raise _domain_error(exc) from exc
