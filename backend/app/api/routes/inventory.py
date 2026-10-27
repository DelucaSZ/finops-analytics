"""Authenticated HTTP query API for persisted provider-neutral Inventory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.cloud import normalize_provider
from app.core.inventory import InventoryPresenceStatus, prepare_inventory_metadata
from app.core.security import require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.inventory import (
    InventoryAccountOption,
    InventoryOptionsResponse,
    InventoryResourceDetailResponse,
    InventoryResourceListResponse,
    InventoryResourceResponse,
    InventorySortDirection,
    InventorySortField,
)
from app.services.inventory_query import (
    InventoryQuery,
    InventoryQueryService,
    InventoryResourceView,
)

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(require_user)],
)


def _provider(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_provider(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported cloud provider") from exc


def _resource_response(view: InventoryResourceView) -> InventoryResourceResponse:
    resource = view.resource
    return InventoryResourceResponse(
        id=resource.id,
        provider=resource.provider,
        cloud_account_id=resource.cloud_account_id,
        native_account_id=resource.native_account_id,
        account_name=view.account_name,
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        native_resource_type=resource.native_resource_type,
        service=resource.service,
        name=resource.name,
        region=resource.region,
        availability_zone=resource.availability_zone,
        lifecycle_status=resource.lifecycle_status,
        native_status=resource.native_status,
        presence_status=resource.presence_status,
        tags=prepare_inventory_metadata(resource.tags or {}, field_name="tags"),
        attributes=prepare_inventory_metadata(resource.attributes or {}, field_name="attributes"),
        first_seen_at=resource.first_seen_at,
        last_seen_at=resource.last_seen_at,
        last_seen_collection_run_id=resource.last_seen_collection_run_id,
    )


@router.get(
    "/resources",
    response_model=InventoryResourceListResponse,
    summary="List persisted Inventory resources",
)
def list_inventory_resources(
    provider: str | None = Query(
        default=None,
        max_length=16,
        description="Canonical cloud provider (for example aws or oci).",
    ),
    account_id: int | None = Query(
        default=None,
        ge=1,
        description="Internal CloudAccount identifier.",
    ),
    region: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    lifecycle_status: str | None = Query(default=None, max_length=64),
    presence_status: InventoryPresenceStatus | None = Query(
        default=None,
        description="Inventory presence state. Omitted means all states.",
    ),
    service: str | None = Query(default=None, max_length=120),
    search: str | None = Query(
        default=None,
        max_length=256,
        description=(
            "Case-insensitive substring search over name, resource ID, native account ID, "
            "resource type, service and region. JSON tags/attributes are not searched."
        ),
    ),
    sort: InventorySortField = Query(default=InventorySortField.LAST_SEEN_AT),
    direction: InventorySortDirection = Query(default=InventorySortDirection.DESC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> InventoryResourceListResponse:
    query = InventoryQuery(
        provider=_provider(provider),
        account_id=account_id,
        region=region,
        resource_type=resource_type,
        lifecycle_status=lifecycle_status,
        presence_status=presence_status.value if presence_status is not None else None,
        service=service,
        search=search,
        sort=sort,
        direction=direction,
        page=page,
        page_size=page_size,
    )
    result = InventoryQueryService().list_resources(db, user=user, query=query)
    return InventoryResourceListResponse(
        items=[_resource_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
    )


@router.get(
    "/options",
    response_model=InventoryOptionsResponse,
    summary="List Inventory filter options from accessible persisted data",
)
def inventory_options(
    provider: str | None = Query(default=None, max_length=16),
    account_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> InventoryOptionsResponse:
    result = InventoryQueryService().options(
        db,
        user=user,
        provider=_provider(provider),
        account_id=account_id,
    )
    return InventoryOptionsResponse(
        providers=list(result.providers),
        accounts=[
            InventoryAccountOption(
                id=item.id,
                name=item.name,
                native_account_id=item.native_account_id,
                provider=item.provider,
            )
            for item in result.accounts
        ],
        regions=list(result.regions),
        resource_types=list(result.resource_types),
        services=list(result.services),
        lifecycle_statuses=list(result.lifecycle_statuses),
        presence_statuses=list(result.presence_statuses),
    )


@router.get(
    "/resources/{resource_id}",
    response_model=InventoryResourceDetailResponse,
    summary="Get one persisted Inventory resource",
)
def inventory_resource_detail(
    resource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> InventoryResourceDetailResponse:
    if resource_id < 1:
        raise HTTPException(status_code=404, detail="Inventory resource not found")
    view = InventoryQueryService().get_resource(db, user=user, resource_id=resource_id)
    if view is None:
        # Deliberately identical for absent and out-of-scope resources.
        raise HTTPException(status_code=404, detail="Inventory resource not found")
    response = _resource_response(view)
    return InventoryResourceDetailResponse(
        **response.model_dump(),
        first_seen_collection_run_id=view.resource.first_seen_collection_run_id,
    )
