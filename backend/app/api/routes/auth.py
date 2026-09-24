from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.security import authenticate_user, require_session, require_user
from app.db.base import utcnow
from app.db.session import get_db
from app.models.auth import AccessToken, LoginSession
from app.models.user import User
from app.schemas.auth import (
    CompleteAccess,
    LoginRequest,
    PasswordChange,
    PasswordProof,
    ResetRequest,
)
from app.schemas.user import UserRead
from app.services.authentication import (
    COOKIE,
    aware,
    browser_request,
    clear_session_cookie,
    csrf_token,
    digest,
    live_sessions,
    new_session,
    rate_limit,
    revoke_sessions,
    set_session_cookie,
)
from app.services.mailer import request_password_reset
from app.services.users import lock_user_changes

router = APIRouter(prefix="/auth", tags=["auth"])


def _locked_user(db: Session, user: User, session: LoginSession) -> None:
    version = session.user_version
    lock_user_changes(db)
    db.refresh(user)
    db.refresh(session)
    now = utcnow()
    if (
        not user.is_active
        or not user.password_set
        or user.token_version != version
        or session.revoked_at
        or aware(session.expires_at) <= now
        or aware(session.last_seen_at) <= now - timedelta(minutes=settings.session_idle_minutes)
    ):
        raise HTTPException(401, "Sessão expirada. Entre novamente.")


@router.post("/login", dependencies=[Depends(browser_request)])
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    rate_limit(db, request, "login", payload.email.strip().lower())
    user = authenticate_user(db, payload.email, payload.password.get_secret_value())
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    version = user.token_version
    lock_user_changes(db)
    db.refresh(user)
    if not user.is_active or not user.password_set or user.token_version != version:
        raise HTTPException(401, "Invalid email or password")
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(
            update(LoginSession)
            .where(LoginSession.token_hash == digest(old))
            .values(revoked_at=utcnow())
        )
    _, raw = new_session(db, user, request.headers.get("user-agent", ""))
    db.commit()
    set_session_cookie(response, raw)
    return {"user": UserRead.model_validate(user), "csrf_token": csrf_token(raw)}


@router.get("/me", response_model=UserRead)
def current_user(user: User = Depends(require_user)) -> User:
    return user


@router.get("/csrf")
def csrf(request: Request, _: LoginSession = Depends(require_session)) -> dict:
    return {"csrf_token": csrf_token(request.cookies[COOKIE])}


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    db.execute(
        update(LoginSession).where(LoginSession.id == session.id).values(revoked_at=utcnow())
    )
    db.commit()
    clear_session_cookie(response)


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    _locked_user(db, user, session)
    revoke_sessions(db, user.id)
    db.commit()
    clear_session_cookie(response)


@router.get("/sessions")
def sessions(
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": item.id,
            "created_at": item.created_at,
            "last_seen_at": item.last_seen_at,
            "expires_at": item.expires_at,
            "user_agent": item.user_agent,
            "current": item.id == session.id,
        }
        for item in live_sessions(db, user)
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: str,
    response: Response,
    user: User = Depends(require_user),
    current: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    changed = db.execute(
        update(LoginSession)
        .where(LoginSession.id == session_id, LoginSession.user_id == user.id)
        .values(revoked_at=utcnow())
    ).rowcount
    if not changed:
        raise HTTPException(404, "Sessão não encontrada")
    db.commit()
    if session_id == current.id:
        clear_session_cookie(response)


@router.post("/reauthenticate", status_code=204)
def reauthenticate(
    payload: PasswordProof,
    request: Request,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    rate_limit(db, request, "reauthenticate", user.id, limit=5)
    _locked_user(db, user, session)
    if not verify_password(payload.password.get_secret_value(), user.password_hash):
        raise HTTPException(400, "Senha incorreta")
    session.reauthenticated_at = utcnow()
    db.commit()


@router.post("/change-password", status_code=204)
def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    rate_limit(db, request, "change-password", user.id, limit=5)
    _locked_user(db, user, session)
    if not verify_password(payload.current_password.get_secret_value(), user.password_hash):
        raise HTTPException(400, "Senha atual incorreta")
    user.password_hash = hash_password(payload.new_password.get_secret_value())
    user.token_version += 1
    revoke_sessions(db, user.id)
    db.commit()
    clear_session_cookie(response)


@router.post("/forgot-password", dependencies=[Depends(browser_request)], status_code=202)
def forgot_password(
    payload: ResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    email = payload.email.strip().lower()
    if rate_limit(db, request, "forgot-password", email, limit=3, silent=True):
        background.add_task(request_password_reset, email, db.get_bind())
    return {
        "message": (
            "Se a conta estiver ativa e o envio de e-mail estiver configurado, "
            "você receberá um link. Caso contrário, contate o administrador."
        )
    }


def _complete_access(
    payload: CompleteAccess, request: Request, response: Response, db: Session, purpose: str
) -> dict:
    rate_limit(db, request, "complete-access", limit=10)
    lock_user_changes(db)
    token = db.scalar(
        select(AccessToken).where(
            AccessToken.token_hash == digest(payload.token.get_secret_value()),
            AccessToken.purpose == purpose,
        )
    )
    user = db.get(User, token.user_id, populate_existing=True) if token else None
    if (
        token is None
        or token.used_at
        or aware(token.expires_at) <= utcnow()
        or user is None
        or not user.is_active
        or user.token_version != token.user_version
        or (purpose == "invite" and user.password_set)
        or (purpose == "reset" and not user.password_set)
    ):
        raise HTTPException(400, "Link inválido, expirado ou já utilizado. Solicite um novo link.")
    user.password_hash = hash_password(payload.password.get_secret_value())
    user.password_set = True
    user.token_version += 1
    token.used_at = utcnow()
    revoke_sessions(db, user.id)
    db.commit()
    clear_session_cookie(response)
    return {"message": "Senha definida. Entre com seu e-mail e a nova senha."}


@router.post("/accept-invitation", dependencies=[Depends(browser_request)])
def accept_invitation(
    payload: CompleteAccess, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    return _complete_access(payload, request, response, db, "invite")


@router.post("/reset-password", dependencies=[Depends(browser_request)])
def reset_password(
    payload: CompleteAccess, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    return _complete_access(payload, request, response, db, "reset")
