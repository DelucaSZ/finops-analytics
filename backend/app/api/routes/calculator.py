"""Authenticated, read-only cloud cost estimates, with verified AWS SKU adapters."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse
from app.services.aws_calculator import estimate_aws_calculator
from app.services.aws_calculator_options import available_regions, aws_options
from app.services.oci_calculator import estimate_oci_calculator, oci_calculator_options

router = APIRouter(prefix="/calculator", tags=["calculator"], dependencies=[Depends(require_user)])


@router.post("/estimate", response_model=CalculatorEstimateResponse)
def estimate(
    request: CalculatorEstimateRequest,
    db: Session = Depends(get_db),
) -> CalculatorEstimateResponse:
    if request.provider == "aws":
        return estimate_aws_calculator(request, db=db)
    return estimate_oci_calculator(request, db)


@router.get("/aws/regions")
def regions(db: Session = Depends(get_db)) -> dict:
    return available_regions(db)


@router.get("/aws/options")
def options(
    service: Literal["ec2", "rds"],
    region: str = Query(min_length=5, max_length=40),
    search: str = Query(min_length=2, max_length=40),
    engine: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1000000),
    db: Session = Depends(get_db),
) -> dict:
    return aws_options(
        db,
        service=service,
        region=region,
        search=search,
        engine=engine,
        limit=limit,
        offset=offset,
    )


@router.get("/oci/options")
def oci_options(
    service: Literal["compute", "db_system"],
    region: str = Query(min_length=5, max_length=80),
    db: Session = Depends(get_db),
) -> dict:
    return oci_calculator_options(db, service=service, region=region)
