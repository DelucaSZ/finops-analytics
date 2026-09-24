import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.passwords import hash_password
from app.core.security import require_admin, require_recent_admin
from app.db.base import utcnow
from app.db.session import get_db
from app.models.auth import LoginSession
from app.models.mfa import MfaCredential
from app.models.user import User, UserRole
from app.schemas.user import UserAdminRead, UserCreate, UserInvite, UserRead, UserUpdate
from app.services.authentication import issue_token, live_sessions, revoke_sessions, token_link
from app.services.mfa import event
from app.services.users import lock_user_changes

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


def _lock_and_recheck_admin(db: Session, actor: User) -> None:
    previous_version = actor.token_version
    lock_user_changes(db)
    db.refresh(actor)
    if (
        not actor.is_active
        or actor.role != UserRole.ADMIN
        or actor.token_version != previous_version
    ):
        raise HTTPException(status_code=403, detail="Administrator access changed; sign in again")


def _commit(db: Session, user: User) -> User:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from exc
    db.refresh(user)
    return user


@router.get("", response_model=list[UserAdminRead])
def list_users(
    q: str = Query(default="", max_length=254),
    state: Literal["active", "inactive", "pending"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[dict]:
    filters = []
    if q.strip():
        filters.append(
            or_(
                User.name.icontains(q.strip(), autoescape=True),
                User.email.icontains(q.strip(), autoescape=True),
            )
        )
    if state == "inactive":
        filters.append(User.is_active.is_(False))
    elif state == "pending":
        filters.extend([User.is_active.is_(True), User.password_set.is_(False)])
    elif state == "active":
        filters.extend([User.is_active.is_(True), User.password_set.is_(True)])
    rows = db.execute(
        select(User, MfaCredential)
        .outerjoin(MfaCredential, MfaCredential.user_id == User.id)
        .where(*filters)
        .order_by(User.name, User.id)
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            **UserRead.model_validate(user).model_dump(),
            "mfa_enabled": bool(mfa and mfa.secret),
            "mfa_reset_required": bool(mfa and mfa.reset_required),
        }
        for user, mfa in rows
    ]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> User:
    password_hash = hash_password(payload.password.get_secret_value())
    _lock_and_recheck_admin(db, actor)
    user = User(
        name=payload.name, email=payload.email, role=payload.role, password_hash=password_hash
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email is already registered") from exc
    event(db, user.id, "user.created", actor.id)
    return _commit(db, user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> User:
    _lock_and_recheck_admin(db, actor)
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    removing_admin = changes.get("role", user.role) != UserRole.ADMIN or not changes.get(
        "is_active", user.is_active
    )
    if user.role == UserRole.ADMIN and user.is_active and user.password_set and removing_admin:
        admin_count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN, User.is_active.is_(True), User.password_set.is_(True)
            )
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409, detail="Cannot remove the last active administrator"
            )
    if any(
        field in changes and changes[field] != getattr(user, field)
        for field in ("email", "role", "is_active")
    ):
        user.token_version += 1
        revoke_sessions(db, user.id)
    changed_fields = sorted(
        field for field, value in changes.items() if value != getattr(user, field)
    )
    if changed_fields:
        event(
            db,
            user.id,
            "user.updated",
            actor.id,
            "Campos alterados: "
            + ", ".join(
                {"name": "nome", "email": "e-mail", "role": "perfil", "is_active": "situação"}[
                    field
                ]
                for field in changed_fields
            ),
        )
    for field, value in changes.items():
        setattr(user, field, value)
    return _commit(db, user)


@router.post("/invitations", status_code=201)
def invite_user(
    payload: UserInvite, db: Session = Depends(get_db), actor: User = Depends(require_recent_admin)
) -> dict:
    password_hash = hash_password(secrets.token_urlsafe(48))
    _lock_and_recheck_admin(db, actor)
    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        password_hash=password_hash,
        password_set=False,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email is already registered") from exc
    event(db, user.id, "user.invited", actor.id)
    raw, expiry = issue_token(db, user, "invite")
    db.commit()
    return {
        "user": UserRead.model_validate(user),
        "url": token_link(raw, "invite"),
        "expires_at": expiry,
    }


def _issue_access(user_id: str, purpose: str, db: Session, actor: User) -> dict:
    _lock_and_recheck_admin(db, actor)
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        raise HTTPException(404, "User not found")
    if not user.is_active or (purpose == "invite") == user.password_set:
        raise HTTPException(409, "Estado da conta incompatível com esta operação")
    event(
        db,
        user.id,
        "user.invitation_renewed" if purpose == "invite" else "user.password_reset_issued",
        actor.id,
    )
    raw, expiry = issue_token(db, user, purpose)
    db.commit()
    return {"url": token_link(raw, purpose), "expires_at": expiry}


@router.post("/{user_id}/invitation")
def renew_invitation(
    user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_recent_admin)
) -> dict:
    return _issue_access(user_id, "invite", db, actor)


@router.post("/{user_id}/password-reset")
def generate_password_reset(
    user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_recent_admin)
) -> dict:
    return _issue_access(user_id, "reset", db, actor)


@router.delete("/{user_id}/sessions", status_code=204)
def revoke_user_sessions(
    user_id: str, db: Session = Depends(get_db), actor: User = Depends(require_recent_admin)
) -> None:
    _lock_and_recheck_admin(db, actor)
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    revoke_sessions(db, user_id)
    event(db, user_id, "user.sessions_revoked", actor.id)
    db.commit()


@router.get("/{user_id}/sessions")
def user_sessions(user_id: str, db: Session = Depends(get_db)) -> list[dict]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return (
        [
            {
                "id": item.id,
                "created_at": item.created_at,
                "last_seen_at": item.last_seen_at,
                "expires_at": item.expires_at,
                "user_agent": item.user_agent,
            }
            for item in live_sessions(db, user)
        ]
        if user.is_active
        else []
    )


@router.delete("/{user_id}/sessions/{session_id}", status_code=204)
def revoke_one_user_session(
    user_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> None:
    _lock_and_recheck_admin(db, actor)
    item = db.get(LoginSession, session_id, populate_existing=True)
    if item is None or item.user_id != user_id:
        raise HTTPException(404, "Sessão não encontrada")
    item.revoked_at = utcnow()
    event(db, user_id, "user.session_revoked", actor.id)
    db.commit()
