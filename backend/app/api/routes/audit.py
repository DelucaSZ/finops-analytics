from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.security import require_admin
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.mfa import SecurityEvent
from app.models.user import User
from app.schemas.audit import AuditPage, AuditUserOption

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])

EventKind = Literal["security", "administrative", "all"]
SecurityCategory = Literal["auth", "user", "mfa"]
AuditSource = Literal["UI", "API", "SYSTEM"]


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _security_module(action: str) -> str:
    return action.split(".", 1)[0] if "." in action else "security"


def _matching_user_ids(text: str):
    value = text.strip()
    return select(User.id).where(
        or_(
            User.name.icontains(value, autoescape=True),
            User.email.icontains(value, autoescape=True),
        )
    )


def _admin_filters(
    *,
    module: str | None,
    action: str | None,
    actor_id: str | None,
    actor_search: str | None,
    subject_user_id: str | None,
    subject_user_search: str | None,
    entity_type: str | None,
    entity_id: str | None,
    source: str | None,
    correlation_id: str | None,
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
    if actor_search and actor_search.strip():
        text = actor_search.strip()
        filters.append(
            or_(
                AuditEvent.actor_name_snapshot.icontains(text, autoescape=True),
                AuditEvent.actor_email_snapshot.icontains(text, autoescape=True),
                AuditEvent.actor_id.in_(_matching_user_ids(text)),
            )
        )
    if subject_user_id:
        filters.extend(
            [AuditEvent.entity_type == "user", AuditEvent.entity_id == subject_user_id]
        )
    if subject_user_search and subject_user_search.strip():
        text = subject_user_search.strip()
        filters.extend(
            [
                AuditEvent.entity_type == "user",
                or_(
                    AuditEvent.entity_label.icontains(text, autoescape=True),
                    AuditEvent.entity_id.in_(_matching_user_ids(text)),
                ),
            ]
        )
    if entity_type:
        filters.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        filters.append(AuditEvent.entity_id == entity_id)
    if source:
        filters.append(AuditEvent.source == source)
    if correlation_id:
        filters.append(AuditEvent.correlation_id == correlation_id)
    if legacy_user_id:
        filters.extend([AuditEvent.entity_type == "user", AuditEvent.entity_id == legacy_user_id])
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
    actor_search: str | None,
    subject_user_id: str | None,
    subject_user_search: str | None,
    entity_type: str | None,
    entity_id: str | None,
    source: str | None,
    correlation_id: str | None,
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
    if actor_search and actor_search.strip():
        filters.append(SecurityEvent.actor_id.in_(_matching_user_ids(actor_search.strip())))
    if subject_user_id:
        filters.append(SecurityEvent.user_id == subject_user_id)
    if subject_user_search and subject_user_search.strip():
        filters.append(SecurityEvent.user_id.in_(_matching_user_ids(subject_user_search.strip())))
    if entity_type and entity_type != "user":
        possible = False
    if entity_id:
        filters.append(SecurityEvent.user_id == entity_id)
    if source and source != "API":
        possible = False
    if correlation_id:
        possible = False
    if legacy_user_id:
        filters.append(SecurityEvent.user_id == legacy_user_id)
    if from_:
        filters.append(SecurityEvent.created_at >= from_)
    if to:
        filters.append(SecurityEvent.created_at <= to)
    return filters, possible


def _admin_item(item: AuditEvent) -> dict:
    legacy_user_id = item.entity_id if item.entity_type == "user" else None
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
        "before": item.before_data or {},
        "after": item.after_data or {},
        "changes": item.changes or {},
        "metadata": item.metadata_json or {},
        "correlation_id": item.correlation_id,
        "actor_id": item.actor_id,
        "actor_name": item.actor_name_snapshot,
        "actor_email": item.actor_email_snapshot,
        "user_id": legacy_user_id,
        "user_name": None,
        "user_email": None,
    }


def _security_item(item: SecurityEvent, actor: User | None, subject: User | None) -> dict:
    actor_name = actor.name if actor else None
    actor_email = actor.email if actor else None
    user_name = subject.name if subject else None
    user_email = subject.email if subject else None
    label = f"{user_name} · {user_email}" if subject else None
    return {
        "id": item.id,
        "event_kind": "security",
        "created_at": item.created_at,
        "actor": {"id": item.actor_id, "name": actor_name, "email": actor_email},
        "module": _security_module(item.action),
        "action": item.action,
        "entity": {"type": "user", "id": item.user_id, "label": label},
        "source": "API",
        "reason": item.reason or "",
        "before": {},
        "after": {},
        "changes": {},
        "metadata": {},
        "correlation_id": None,
        "actor_id": item.actor_id,
        "actor_name": actor_name,
        "actor_email": actor_email,
        "user_id": item.user_id,
        "user_name": user_name,
        "user_email": user_email,
    }


@router.get("/users", response_model=list[AuditUserOption])
def search_audit_users(
    q: str = Query(default="", max_length=254),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[User]:
    statement = select(User)
    if q.strip():
        text = q.strip()
        statement = statement.where(
            or_(
                User.name.icontains(text, autoescape=True),
                User.email.icontains(text, autoescape=True),
            )
        )
    return list(db.scalars(statement.order_by(User.name, User.email, User.id).limit(limit)))


@router.get("", response_model=AuditPage)
def list_audit(
    event_kind: EventKind | None = None,
    event_type: EventKind | None = None,
    category: SecurityCategory | None = None,
    user_id: str | None = Query(default=None, max_length=36),
    module: str | None = Query(default=None, max_length=80),
    action: str | None = Query(default=None, max_length=120),
    actor_id: str | None = Query(default=None, max_length=36),
    actor_search: str | None = Query(default=None, max_length=254),
    subject_user_id: str | None = Query(default=None, max_length=36),
    subject_user_search: str | None = Query(default=None, max_length=254),
    entity_type: str | None = Query(default=None, max_length=120),
    entity_id: str | None = Query(default=None, max_length=255),
    source: AuditSource | None = None,
    correlation_id: str | None = Query(default=None, max_length=36),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    selected_kind = event_kind or event_type or "all"
    include_security = selected_kind in {"security", "all"}
    include_admin = selected_kind in {"administrative", "all"}
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
            actor_search=actor_search,
            subject_user_id=subject_user_id,
            subject_user_search=subject_user_search,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            correlation_id=correlation_id,
            legacy_user_id=user_id,
            from_=from_,
            to=to,
        )
        total += db.scalar(select(func.count()).select_from(AuditEvent).where(*admin_filters)) or 0
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
            actor_search=actor_search,
            subject_user_id=subject_user_id,
            subject_user_search=subject_user_search,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            correlation_id=correlation_id,
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

    rows.sort(key=lambda item: (_timestamp(item["created_at"]), item["id"]), reverse=True)
    return {
        "items": rows[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
