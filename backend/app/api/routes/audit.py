from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.security import require_admin
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.mfa import SecurityEvent
from app.models.user import User
from app.schemas.audit import AuditPage

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])

EventType = Literal["security", "administrative", "all"]
SecurityCategory = Literal["auth", "user", "mfa"]


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _security_module(action: str) -> str:
    return action.split(".", 1)[0] if "." in action else "security"


def _admin_filters(
    *,
    module: str | None,
    action: str | None,
    actor_id: str | None,
    entity_type: str | None,
    entity_id: str | None,
    legacy_user_id: str | None,
    from_: datetime | None,
    to: datetime | None,
) -> list:
    filters = []
    if module:
        filters.append(AuditEvent.module == module)
    if action:
        filters.append(AuditEvent.action == action)
    if actor_id:
        filters.append(AuditEvent.actor_id == actor_id)
    if entity_type:
        filters.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        filters.append(AuditEvent.entity_id == entity_id)
    if legacy_user_id:
        filters.extend(
            [
                AuditEvent.entity_type == "user",
                AuditEvent.entity_id == legacy_user_id,
            ]
        )
    if from_:
        filters.append(AuditEvent.created_at >= from_)
    if to:
        filters.append(AuditEvent.created_at <= to)
    return filters


def _security_filters(
    *,
    category: str | None,
    module: str | None,
    action: str | None,
    actor_id: str | None,
    entity_type: str | None,
    entity_id: str | None,
    legacy_user_id: str | None,
    from_: datetime | None,
    to: datetime | None,
) -> tuple[list, bool]:
    filters = []
    possible = True

    prefix = category or module
    if prefix:
        if prefix == "security":
            pass
        elif prefix in {"auth", "user", "mfa"}:
            filters.append(SecurityEvent.action.like(prefix + ".%"))
        else:
            possible = False

    if action:
        filters.append(SecurityEvent.action == action)
    if actor_id:
        filters.append(SecurityEvent.actor_id == actor_id)
    if entity_type and entity_type != "user":
        possible = False
    if entity_id:
        filters.append(SecurityEvent.user_id == entity_id)
    if legacy_user_id:
        filters.append(SecurityEvent.user_id == legacy_user_id)
    if from_:
        filters.append(SecurityEvent.created_at >= from_)
    if to:
        filters.append(SecurityEvent.created_at <= to)
    return filters, possible


def _admin_item(item: AuditEvent) -> dict:
    return {
        "id": item.id,
        "event_kind": "administrative",
        "created_at": item.created_at,
        "actor": {
            "id": item.actor_id,
            "name": item.actor_name_snapshot,
            "email": item.actor_email_snapshot,
        },
        "module": item.module,
        "action": item.action,
        "entity": {
            "type": item.entity_type,
            "id": item.entity_id,
            "label": item.entity_label,
        },
        "source": item.source,
        "reason": None,
        "changes": item.changes or {},
        "metadata": item.metadata_json or {},
        "correlation_id": item.correlation_id,
    }


def _security_item(
    item: SecurityEvent,
    actor: User | None,
    subject: User | None,
) -> dict:
    label = None
    if subject:
        label = f"{subject.name} · {subject.email}"
    return {
        "id": item.id,
        "event_kind": "security",
        "created_at": item.created_at,
        "actor": {
            "id": item.actor_id,
            "name": actor.name if actor else None,
            "email": actor.email if actor else None,
        },
        "module": _security_module(item.action),
        "action": item.action,
        "entity": {
            "type": "user",
            "id": item.user_id,
            "label": label,
        },
        "source": "API",
        "reason": item.reason or None,
        "changes": {},
        "metadata": {},
        "correlation_id": None,
    }


@router.get("", response_model=AuditPage)
def list_audit(
    event_type: EventType = "all",
    category: SecurityCategory | None = None,
    user_id: str | None = Query(default=None, max_length=36),
    module: str | None = Query(default=None, max_length=80),
    action: str | None = Query(default=None, max_length=120),
    actor_id: str | None = Query(default=None, max_length=36),
    entity_type: str | None = Query(default=None, max_length=120),
    entity_id: str | None = Query(default=None, max_length=255),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    include_security = event_type in {"security", "all"}
    include_admin = event_type in {"administrative", "all"}

    # `category` is a compatibility filter for the legacy SecurityEvent endpoint.
    # Supplying it narrows the request to that legacy stream rather than leaking
    # unrelated administrative rows into old clients.
    if category is not None:
        include_admin = False

    fetch_limit = offset + limit
    rows: list[dict] = []
    total = 0

    if include_admin:
        admin_filters = _admin_filters(
            module=module,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            legacy_user_id=user_id,
            from_=from_,
            to=to,
        )
        total += db.scalar(
            select(func.count()).select_from(AuditEvent).where(*admin_filters)
        ) or 0
        admin_rows = db.scalars(
            select(AuditEvent)
            .where(*admin_filters)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(fetch_limit)
        )
        rows.extend(_admin_item(item) for item in admin_rows)

    if include_security:
        security_filters, possible = _security_filters(
            category=category,
            module=module,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            legacy_user_id=user_id,
            from_=from_,
            to=to,
        )
        if possible:
            total += db.scalar(
                select(func.count()).select_from(SecurityEvent).where(*security_filters)
            ) or 0
            actor = aliased(User)
            subject = aliased(User)
            security_rows = db.execute(
                select(SecurityEvent, actor, subject)
                .outerjoin(actor, actor.id == SecurityEvent.actor_id)
                .outerjoin(subject, subject.id == SecurityEvent.user_id)
                .where(*security_filters)
                .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
                .limit(fetch_limit)
            )
            rows.extend(
                _security_item(item, actor_user, subject_user)
                for item, actor_user, subject_user in security_rows
            )

    rows.sort(
        key=lambda item: (_timestamp(item["created_at"]), item["id"]),
        reverse=True,
    )
    return {
        "items": rows[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
