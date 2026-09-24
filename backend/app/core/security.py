from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password, password_hasher, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole

ALGORITHM = "HS256"
AUTH_VERSION = 1
bearer = HTTPBearer(auto_error=False)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not verify_password(password, user.password_hash if user else None):
        return None
    if user is None or not user.is_active:
        return None
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "auth_version": AUTH_VERSION,
        "ver": user.token_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise invalid
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "iat", "exp", "auth_version", "ver"]},
        )
    except jwt.PyJWTError as exc:
        raise invalid from exc
    if payload["auth_version"] != AUTH_VERSION or not isinstance(payload["sub"], str):
        raise invalid
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active or payload["ver"] != user.token_version:
        raise invalid
    if user.role not in set(UserRole):
        raise invalid
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def require_operator(user: User = Depends(require_user)) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status_code=403, detail="Operator access required")
    return user
