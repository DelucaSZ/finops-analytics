from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.billing import (
    AwsBillingRequest,
    BillingBreakdownResponse,
    BillingSummaryResponse,
    BillingTimeSeriesResponse,
)
from app.services.aws_billing import AwsBillingService, BillingServiceError
from app.services.aws_cost_explorer import AwsBillingUpstreamError

router = APIRouter(
    prefix="/billing/aws",
    tags=["billing"],
    dependencies=[Depends(require_user)],
)


def _raise_billing_error(exc: BillingServiceError | AwsBillingUpstreamError) -> None:
    status_by_code = {
        "ACCOUNT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ACCESS_DENIED": status.HTTP_403_FORBIDDEN,
        "ACCOUNT_NOT_AWS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_PERIOD": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_GROUPING": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_REQUEST": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_BILLING_SCOPE": status.HTTP_422_UNPROCESSABLE_ENTITY,
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


@router.post("/summary", response_model=BillingSummaryResponse)
def aws_billing_summary(
    payload: AwsBillingRequest,
    db: Session = Depends(get_db),
) -> BillingSummaryResponse:
    try:
        return AwsBillingService(db).summary(payload)
    except (BillingServiceError, AwsBillingUpstreamError) as exc:
        _raise_billing_error(exc)


@router.post("/timeseries", response_model=BillingTimeSeriesResponse)
def aws_billing_timeseries(
    payload: AwsBillingRequest,
    db: Session = Depends(get_db),
) -> BillingTimeSeriesResponse:
    try:
        return AwsBillingService(db).timeseries(payload)
    except (BillingServiceError, AwsBillingUpstreamError) as exc:
        _raise_billing_error(exc)


@router.post("/breakdown", response_model=BillingBreakdownResponse)
def aws_billing_breakdown(
    payload: AwsBillingRequest,
    db: Session = Depends(get_db),
) -> BillingBreakdownResponse:
    try:
        return AwsBillingService(db).breakdown(payload)
    except (BillingServiceError, AwsBillingUpstreamError) as exc:
        _raise_billing_error(exc)
