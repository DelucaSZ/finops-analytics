import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.auth import AccessToken, AuthRateLimit, LoginSession
from app.models.user import User

COOKIE = "deepops_session"


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(raw_session: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), ("csrf:" + raw_session).encode(), hashlib.sha256
    ).hexdigest()


def browser_request(request: Request) -> None:
    # Custom header forces cross-origin browsers to preflight, including login CSRF.
    if request.headers.get("x-deepops-request") != "1":
        raise HTTPException(403, "Requisição não permitida")
    origin = request.headers.get("origin")
    scheme = "https" if settings.secure_cookies else request.url.scheme
    allowed = {
        *settings.cors_origins,
        settings.public_url,
        f"{scheme}://{request.headers.get('host', '')}",
    }
    if origin and (origin == "null" or origin not in allowed):
        raise HTTPException(403, "Origem não permitida")


def rate_limit(
    db: Session,
    request: Request,
    scope: str,
    identity: str = "",
    *,
    limit: int = 10,
    seconds: int = 900,
    silent: bool = False,
) -> bool:
    now = utcnow()
    bucket = int(now.timestamp()) // seconds
    # Peer IP is deliberately not read from untrusted forwarded headers.
    peer = request.client.host if request.client else "unknown"
    keys = [(f"{scope}:peer:{peer}", limit * 6)]
    if identity:
        keys.append((f"{scope}:identity:{identity}", limit))
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    allowed = True
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at < now))
    for raw_key, maximum in keys:
        key = digest(f"{raw_key}:{bucket}")
        statement = (
            insert(AuthRateLimit)
            .values(
                key=key, attempts=1, expires_at=datetime.fromtimestamp((bucket + 1) * seconds, UTC)
            )
            .on_conflict_do_update(
                index_elements=[AuthRateLimit.key], set_={"attempts": AuthRateLimit.attempts + 1}
            )
            .returning(AuthRateLimit.attempts)
        )
        allowed = db.scalar(statement) <= maximum
        if not allowed:
            break  # A blocked peer cannot create unlimited per-identity buckets.
    db.commit()  # Failed attempts must survive request rollback and process restarts.
    if not allowed and not silent:
        raise HTTPException(
            429,
            "Muitas tentativas. Aguarde e tente novamente.",
            headers={"Retry-After": str(seconds)},
        )
    return allowed


def new_session(db: Session, user: User, user_agent: str = "") -> tuple[LoginSession, str]:
    raw = secrets.token_urlsafe(32)
    now = utcnow()
    session = LoginSession(
        user_id=user.id,
        token_hash=digest(raw),
        user_version=user.token_version,
        created_at=now,
        last_seen_at=now,
        reauthenticated_at=now,
        expires_at=now + timedelta(minutes=settings.access_token_minutes),
        user_agent=user_agent[:255],
    )
    db.add(session)
    db.flush()
    return session, raw


def set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        COOKIE,
        raw,
        max_age=settings.access_token_minutes * 60,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE, path="/", secure=settings.secure_cookies, httponly=True, samesite="lax"
    )


def revoke_sessions(db: Session, user_id: str) -> None:
    db.execute(
        update(LoginSession)
        .where(LoginSession.user_id == user_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def issue_token(db: Session, user: User, purpose: str) -> tuple[str, datetime]:
    now = utcnow()
    db.execute(
        update(AccessToken)
        .where(
            AccessToken.user_id == user.id,
            AccessToken.purpose == purpose,
            AccessToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    expiry = now + (timedelta(hours=24) if purpose == "invite" else timedelta(minutes=30))
    db.add(
        AccessToken(
            user_id=user.id,
            token_hash=digest(raw),
            purpose=purpose,
            user_version=user.token_version,
            expires_at=expiry,
        )
    )
    db.flush()
    return raw, expiry


def token_link(raw: str, purpose: str) -> str:
    path = "/accept-invitation" if purpose == "invite" else "/reset-password"
    # Fragment is not sent to proxies/access logs; never build links using request Host.
    return f"{settings.public_url}{path}#token={raw}"


def live_sessions(db: Session, user: User) -> list[LoginSession]:
    now = utcnow()
    return list(
        db.scalars(
            select(LoginSession)
            .where(
                LoginSession.user_id == user.id,
                LoginSession.user_version == user.token_version,
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > now,
                LoginSession.last_seen_at > now - timedelta(minutes=settings.session_idle_minutes),
            )
            .order_by(LoginSession.created_at.desc())
        )
    )
