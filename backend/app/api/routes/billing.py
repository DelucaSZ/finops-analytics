from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import (
    AwsBillingApiRequest,
    BillingBreakdownResponse,
    BillingGroupBy,
    BillingProfileCreate,
    BillingProfileRead,
    BillingProfileUpdate,
    BillingSummaryResponse,
    BillingTimeSeriesResponse,
)
from app.services.aws_billing import AwsBillingService, BillingServiceError
from app.services.aws_cost_explorer import AwsBillingUpstreamError
from app.services.billing_profiles import (
    BillingProfileError,
    BillingProfileService,
    ResolvedBillingRequest,
)

router = APIRouter(
    prefix="/billing/aws",
    tags=["billing"],
    dependencies=[Depends(require_user)],
)


def _raise_billing_error(
    exc: BillingServiceError | AwsBillingUpstreamError | BillingProfileError,
) -> None:
    status_by_code = {
        "ACCOUNT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "PROFILE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ACCESS_DENIED": status.HTTP_403_FORBIDDEN,
        "ACCOUNT_NOT_AWS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_PERIOD": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_GROUPING": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_REQUEST": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_BILLING_SCOPE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_PROFILE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PROFILE_INVALID": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PROFILE_INACTIVE": status.HTTP_409_CONFLICT,
        "PROFILE_NAME_CONFLICT": status.HTTP_409_CONFLICT,
        "PROFILE_CONFLICT": status.HTTP_409_CONFLICT,
        "DEFAULT_CONFLICT": status.HTTP_409_CONFLICT,
        "DEFAULT_PROFILE_REQUIRED": status.HTTP_409_CONFLICT,
        "SYSTEM_PROFILE_PROTECTED": status.HTTP_409_CONFLICT,
        "THROTTLED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "COST_EXPLORER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "PAGINATION_ERROR": status.HTTP_502_BAD_GATEWAY,
        "UPSTREAM_DATA_INVALID": status.HTTP_502_BAD_GATEWAY,
        "UPSTREAM_ERROR": status.HTTP_502_BAD_GATEWAY,
    }
    raise HTTPException(
        status_code=status_by_code.get(exc.code, status.HTTP_502_BAD_GATEWAY),
        detail={"code": exc.code, "message": exc.safe_message},
    ) from exc


def _metadata(
    response: BillingSummaryResponse | BillingTimeSeriesResponse | BillingBreakdownResponse,
    resolved: ResolvedBillingRequest,
    *,
    group_by: BillingGroupBy,
):
    return response.model_copy(
        update={
            "profile_id": resolved.profile_id,
            "profile_name": resolved.profile_name,
            "resolved_options": resolved.options(group_by=group_by),
        }
    )


@router.get("/profiles", response_model=list[BillingProfileRead])
def list_billing_profiles(
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BillingProfileRead]:
    return BillingProfileService(db).list(enabled=enabled)


@router.get("/profiles/{profile_id}", response_model=BillingProfileRead)
def get_billing_profile(
    profile_id: str,
    db: Session = Depends(get_db),
) -> BillingProfileRead:
    try:
        return BillingProfileService(db).get(profile_id)
    except BillingProfileError as exc:
        _raise_billing_error(exc)


@router.post("/profiles", response_model=BillingProfileRead, status_code=status.HTTP_201_CREATED)
def create_billing_profile(
    payload: BillingProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BillingProfileRead:
    try:
        return BillingProfileService(db).create(payload, actor_user_id=user.id, actor=user)
    except BillingProfileError as exc:
        _raise_billing_error(exc)


@router.patch("/profiles/{profile_id}", response_model=BillingProfileRead)
def update_billing_profile(
    profile_id: str,
    payload: BillingProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BillingProfileRead:
    try:
        return BillingProfileService(db).update(profile_id, payload, actor=user)
    except BillingProfileError as exc:
        _raise_billing_error(exc)


@router.post("/profiles/{profile_id}/set-default", response_model=BillingProfileRead)
def set_default_billing_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BillingProfileRead:
    try:
        return BillingProfileService(db).set_default(profile_id, actor=user)
    except BillingProfileError as exc:
        _raise_billing_error(exc)


@router.post("/profiles/{profile_id}/deactivate", response_model=BillingProfileRead)
def deactivate_billing_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BillingProfileRead:
    try:
        return BillingProfileService(db).deactivate(profile_id, actor=user)
    except BillingProfileError as exc:
        _raise_billing_error(exc)


@router.post("/summary", response_model=BillingSummaryResponse)
def aws_billing_summary(
    payload: AwsBillingApiRequest,
    db: Session = Depends(get_db),
) -> BillingSummaryResponse:
    try:
        resolved = BillingProfileService(db).resolve(payload)
        response = AwsBillingService(db).summary(resolved.request)
        return _metadata(response, resolved, group_by=BillingGroupBy.NONE)
    except (BillingServiceError, AwsBillingUpstreamError, BillingProfileError) as exc:
        _raise_billing_error(exc)


@router.post("/timeseries", response_model=BillingTimeSeriesResponse)
def aws_billing_timeseries(
    payload: AwsBillingApiRequest,
    db: Session = Depends(get_db),
) -> BillingTimeSeriesResponse:
    try:
        resolved = BillingProfileService(db).resolve(payload)
        response = AwsBillingService(db).timeseries(resolved.request)
        return _metadata(response, resolved, group_by=resolved.request.group_by)
    except (BillingServiceError, AwsBillingUpstreamError, BillingProfileError) as exc:
        _raise_billing_error(exc)


@router.post("/breakdown", response_model=BillingBreakdownResponse)
def aws_billing_breakdown(
    payload: AwsBillingApiRequest,
    db: Session = Depends(get_db),
) -> BillingBreakdownResponse:
    try:
        resolved = BillingProfileService(db).resolve(payload)
        response = AwsBillingService(db).breakdown(resolved.request)
        return _metadata(response, resolved, group_by=resolved.request.group_by)
    except (BillingServiceError, AwsBillingUpstreamError, BillingProfileError) as exc:
        _raise_billing_error(exc)
