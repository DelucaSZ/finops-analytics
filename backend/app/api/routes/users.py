import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.passwords import hash_password
from app.core.security import require_admin, require_recent_admin
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserInvite, UserRead, UserUpdate
from app.services.authentication import issue_token, revoke_sessions, token_link
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


@router.get("", response_model=list[UserRead])
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.name, User.id).offset(offset).limit(limit)))


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
    db.commit()
