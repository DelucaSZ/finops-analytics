"""Authenticated, read-only cloud cost estimates, with verified AWS SKU adapters."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_user
from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse
from app.services.aws_calculator import estimate_aws_calculator
from app.services.aws_calculator_options import available_regions, aws_options
from app.services.aws_calculator_pricing import AwsPriceUnavailable
from app.services.calculator_engine import estimate_calculator_cost

router = APIRouter(prefix="/calculator", tags=["calculator"], dependencies=[Depends(require_user)])


@router.post("/estimate", response_model=CalculatorEstimateResponse)
def estimate(request: CalculatorEstimateRequest) -> CalculatorEstimateResponse:
    if request.provider == "aws":
        return estimate_aws_calculator(request)
    # OCI production adapters will be implemented in follow-up tasks.
    return estimate_calculator_cost(request, ())


@router.get("/aws/regions")
def regions() -> dict:
    try:
        return {"items": available_regions(), "source": "AWS_PUBLIC_PRICE_LIST"}
    except AwsPriceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/aws/options")
def options(
    service: Literal["ec2", "rds"],
    region: str = Query(min_length=5, max_length=40),
    search: str = Query(min_length=2, max_length=40),
    engine: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    try:
        return aws_options(
            service=service,
            region=region,
            search=search,
            engine=engine,
            limit=limit,
            offset=offset,
        )
    except AwsPriceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
