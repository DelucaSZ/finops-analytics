from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.billing_profile import BillingProfile
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
from app.services.audit import AuditService, audit_snapshot
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


def _profile_snapshot(profile: BillingProfile) -> dict:
    return audit_snapshot(
        {
            "name": profile.name,
            "description": profile.description,
            "granularity": profile.granularity,
            "metric": profile.metric,
            "group_by": profile.group_by,
            "exclude_record_types": list(profile.exclude_record_types),
            "is_default": profile.is_default,
            "enabled": profile.enabled,
            "is_system": profile.is_system,
        }
    )


def _record_profile(
    db: Session,
    *,
    actor: User,
    profile: BillingProfile,
    action: str,
    before: dict | None,
    after: dict | None,
    metadata: dict | None = None,
) -> None:
    AuditService.record(
        db,
        actor=actor,
        module="billing",
        action=action,
        entity_type="billing_profile",
        entity_id=profile.id,
        entity_label=profile.name,
        before=before,
        after=after,
        source="API",
        metadata=metadata,
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


@router.post(
    "/profiles",
    response_model=BillingProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_billing_profile(
    payload: BillingProfileCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> BillingProfileRead:
    try:
        profile = BillingProfileService(db).create(
            payload,
            actor_user_id=actor.id,
            commit=False,
        )
        _record_profile(
            db,
            actor=actor,
            profile=profile,
            action="billing.profile_create",
            before=None,
            after=_profile_snapshot(profile),
        )
        db.commit()
        db.refresh(profile)
        return profile
    except BillingProfileError as exc:
        db.rollback()
        _raise_billing_error(exc)
    except Exception:
        db.rollback()
        raise


@router.patch("/profiles/{profile_id}", response_model=BillingProfileRead)
def update_billing_profile(
    profile_id: str,
    payload: BillingProfileUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> BillingProfileRead:
    service = BillingProfileService(db)
    try:
        current = service.get(profile_id)
        before = _profile_snapshot(current)
        profile = service.update(profile_id, payload, commit=False)
        after = _profile_snapshot(profile)
        if before != after:
            _record_profile(
                db,
                actor=actor,
                profile=profile,
                action="billing.profile_update",
                before=before,
                after=after,
            )
        db.commit()
        db.refresh(profile)
        return profile
    except BillingProfileError as exc:
        db.rollback()
        _raise_billing_error(exc)
    except Exception:
        db.rollback()
        raise


@router.post("/profiles/{profile_id}/set-default", response_model=BillingProfileRead)
def set_default_billing_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> BillingProfileRead:
    service = BillingProfileService(db)
    try:
        current = service.get(profile_id)
        before = _profile_snapshot(current)
        previous_default = next((item for item in service.list() if item.is_default), None)
        profile = service.set_default(profile_id, commit=False)
        after = _profile_snapshot(profile)
        if before != after:
            _record_profile(
                db,
                actor=actor,
                profile=profile,
                action="billing.profile_set_default",
                before=before,
                after=after,
                metadata={
                    "previous_default_profile_id": (
                        previous_default.id if previous_default else None
                    ),
                    "previous_default_profile_name": (
                        previous_default.name if previous_default else None
                    ),
                },
            )
        db.commit()
        db.refresh(profile)
        return profile
    except BillingProfileError as exc:
        db.rollback()
        _raise_billing_error(exc)
    except Exception:
        db.rollback()
        raise


@router.post("/profiles/{profile_id}/deactivate", response_model=BillingProfileRead)
def deactivate_billing_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> BillingProfileRead:
    service = BillingProfileService(db)
    try:
        current = service.get(profile_id)
        before = _profile_snapshot(current)
        profile = service.deactivate(profile_id, commit=False)
        after = _profile_snapshot(profile)
        if before != after:
            _record_profile(
                db,
                actor=actor,
                profile=profile,
                action="billing.profile_deactivate",
                before=before,
                after=after,
            )
        db.commit()
        db.refresh(profile)
        return profile
    except BillingProfileError as exc:
        db.rollback()
        _raise_billing_error(exc)
    except Exception:
        db.rollback()
        raise


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
