from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.opportunity_policy import (
    OpportunityPolicyPreview,
    OpportunityPolicyPreviewRequest,
    OpportunityPolicyRead,
    OpportunityPolicyUpdate,
)
from app.services.opportunity_policy import OpportunityManagementPolicyService

router = APIRouter(
    prefix="/settings/opportunity-policy",
    tags=["opportunity-policy"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=OpportunityPolicyRead)
def get_policy(db: Session = Depends(get_db)) -> dict:
    policy = OpportunityManagementPolicyService.get_or_create(db)
    payload = OpportunityManagementPolicyService.read_payload(db, policy)
    db.commit()
    return payload


@router.put(
    "",
    response_model=OpportunityPolicyRead,
    dependencies=[Depends(require_admin)],
)
def update_policy(
    payload: OpportunityPolicyUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict:
    try:
        policy = OpportunityManagementPolicyService.update(db, payload, actor=actor)
        response = OpportunityManagementPolicyService.read_payload(db, policy)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


@router.post(
    "/preview",
    response_model=OpportunityPolicyPreview,
    dependencies=[Depends(require_admin)],
)
def preview_policy(
    payload: OpportunityPolicyPreviewRequest,
    db: Session = Depends(get_db),
) -> dict:
    # No commit and no mutating service calls: preview is deliberately read-only.
    return OpportunityManagementPolicyService.preview(db, payload)
