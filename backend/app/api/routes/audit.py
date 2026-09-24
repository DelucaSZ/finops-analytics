from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.security import require_admin
from app.db.session import get_db
from app.models.mfa import SecurityEvent
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("")
def list_events(
    category: Literal["auth", "user", "mfa"] | None = None,
    user_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    filters = []
    if category:
        filters.append(SecurityEvent.action.startswith(category + "."))
    if user_id:
        filters.append(SecurityEvent.user_id == user_id)
    actor = aliased(User)
    subject = aliased(User)
    rows = db.execute(
        select(SecurityEvent, actor.name, actor.email, subject.name, subject.email)
        .outerjoin(actor, SecurityEvent.actor_id == actor.id)
        .join(subject, SecurityEvent.user_id == subject.id)
        .where(*filters)
        .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "total": db.scalar(select(func.count()).select_from(SecurityEvent).where(*filters)),
        "items": [
            {
                "id": event.id,
                "action": event.action,
                "reason": event.reason,
                "created_at": event.created_at,
                "actor_id": event.actor_id,
                "actor_name": actor_name,
                "actor_email": actor_email,
                "user_id": event.user_id,
                "user_name": name,
                "user_email": email,
            }
            for event, actor_name, actor_email, name, email in rows
        ],
    }
