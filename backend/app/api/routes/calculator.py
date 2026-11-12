"""Authenticated, read-only cloud cost estimates, with verified AWS SKU adapters."""
from fastapi import APIRouter, Depends

from app.core.security import require_user
from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse
from app.services.aws_calculator import estimate_aws_calculator
from app.services.calculator_engine import estimate_calculator_cost

router = APIRouter(prefix="/calculator", tags=["calculator"], dependencies=[Depends(require_user)])


@router.post("/estimate", response_model=CalculatorEstimateResponse)
def estimate(request: CalculatorEstimateRequest) -> CalculatorEstimateResponse:
    if request.provider == "aws":
        return estimate_aws_calculator(request)
    # OCI production adapters will be implemented in follow-up tasks.
    return estimate_calculator_cost(request, ())
