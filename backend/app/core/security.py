import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password, password_hasher, verify_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models.auth import LoginSession
from app.models.user import User, UserRole
from app.services import mfa
from app.services.authentication import COOKIE, browser_request, csrf_token, digest


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not verify_password(password, user.password_hash if user else None):
        return None
    if user is None or not user.is_active or not user.password_set:
        return None
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user


def require_session(request: Request, db: Session = Depends(get_db)) -> LoginSession:
    raw = request.cookies.get(COOKIE, "")
    invalid = HTTPException(401, "Sessão expirada. Entre novamente.")
    if len(raw) != 43:
        raise invalid
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(raw)))
    user = db.get(User, session.user_id) if session else None
    now = utcnow()
    cutoff = now - timedelta(minutes=settings.session_idle_minutes)
    if (
        session is None
        or user is None
        or not user.is_active
        or not user.password_set
        or user.role not in set(UserRole)
        or session.user_version != user.token_version
    ):
        raise invalid
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        browser_request(request)
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", "").encode(), csrf_token(raw).encode()
        ):
            raise HTTPException(403, "csrf_invalid")
    # Conditional update cannot revive an expired/revoked session, even under concurrency.
    touched = db.execute(
        update(LoginSession)
        .where(
            LoginSession.id == session.id,
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > now,
            LoginSession.last_seen_at > cutoff,
        )
        .values(last_seen_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()
    if not touched:
        raise invalid
    item = mfa.credential(db, user.id)
    if item and item.secret and not session.mfa_verified:
        raise invalid
    allowed = {
        "/api/v1/auth/csrf",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/mfa/status",
        "/api/v1/auth/mfa/setup",
        "/api/v1/auth/mfa/confirm",
    }
    if mfa.enrollment_required(item) and request.url.path not in allowed:
        raise HTTPException(403, "mfa_enrollment_required")
    return session


def require_user(
    session: LoginSession = Depends(require_session), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, session.user_id)
    if (
        user is None
        or not user.is_active
        or not user.password_set
        or user.token_version != session.user_version
    ):
        raise HTTPException(401, "Sessão expirada. Entre novamente.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def require_recent_admin(
    user: User = Depends(require_admin), session: LoginSession = Depends(require_session)
) -> User:
    from app.services.authentication import aware

    if aware(session.reauthenticated_at) < utcnow() - timedelta(minutes=5):
        raise HTTPException(403, "reauthentication_required")
    return user


def require_operator(user: User = Depends(require_user)) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status_code=403, detail="Operator access required")
    return user
