"""Authenticated, read-only estimate boundary for the Task 27.2 calculator core.

Provider adapters in later tasks will supply resolved components. Until then the
API explicitly reports an unsupported service; it never returns mock prices.
"""

from fastapi import APIRouter, Depends

from app.core.security import require_user
from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse
from app.services.calculator_engine import estimate_calculator_cost

router = APIRouter(prefix="/calculator", tags=["calculator"], dependencies=[Depends(require_user)])


@router.post("/estimate", response_model=CalculatorEstimateResponse)
def estimate(request: CalculatorEstimateRequest) -> CalculatorEstimateResponse:
    return estimate_calculator_cost(request, ())
