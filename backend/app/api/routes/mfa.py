from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import _locked_user
from app.core.passwords import verify_password
from app.core.security import require_admin, require_session, require_user
from app.db.base import utcnow
from app.db.session import get_db
from app.models.auth import LoginSession
from app.models.mfa import MfaChallenge, MfaCredential, RecoveryCode, SecurityEvent
from app.models.user import User
from app.schemas.auth import MfaCode, MfaLogin, MfaReset, PasswordProof
from app.schemas.user import UserRead
from app.services import mfa
from app.services.authentication import (
    aware,
    browser_request,
    csrf_token,
    digest,
    new_session,
    rate_limit,
    revoke_sessions,
    set_session_cookie,
)
from app.services.users import lock_user_changes

router = APIRouter(prefix="/auth/mfa", tags=["MFA"])


def proof(
    db: Session, request: Request, user: User, session: LoginSession, payload: PasswordProof
) -> None:
    rate_limit(db, request, "mfa-proof", user.id, limit=5)
    _locked_user(db, user, session)
    if not verify_password(payload.password.get_secret_value(), user.password_hash):
        raise HTTPException(400, "Senha incorreta")
    mfa.require_factor(db, user, payload.code.get_secret_value())


@router.post("/verify", dependencies=[Depends(browser_request)])
def verify_login(
    payload: MfaLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    raw_challenge = payload.challenge.get_secret_value()
    rate_limit(db, request, "mfa-login", digest(raw_challenge), limit=5)
    lock_user_changes(db)
    item = db.get(MfaChallenge, digest(raw_challenge), populate_existing=True)
    user = db.get(User, item.user_id, populate_existing=True) if item else None
    invalid = HTTPException(400, "Desafio inválido ou expirado. Entre novamente.")
    if (
        not item
        or item.used_at
        or aware(item.expires_at) <= utcnow()
        or item.attempts >= 5
        or not user
        or not user.is_active
        or not user.password_set
        or user.token_version != item.user_version
    ):
        raise invalid
    credential = mfa.credential(db, user.id)
    item.attempts += 1
    if not credential or not mfa.verify_factor(db, credential, payload.code.get_secret_value()):
        mfa.event(db, user.id, "mfa.login_failed", user.id)
        db.commit()
        raise HTTPException(400, "Código inválido ou já utilizado. Aguarde o próximo código.")
    item.used_at = utcnow()
    session, raw = new_session(db, user, request.headers.get("user-agent", ""))
    session.mfa_verified = True
    mfa.event(db, user.id, "mfa.login_verified", user.id)
    db.commit()
    set_session_cookie(response, raw)
    return {"user": UserRead.model_validate(user), "csrf_token": csrf_token(raw)}


@router.get("/status")
def status(user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    item = mfa.credential(db, user.id)
    return {
        "enabled": bool(item and item.secret),
        "enrollment_required": mfa.enrollment_required(item),
        "enabled_at": item.enabled_at if item else None,
        "recovery_codes_remaining": db.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
        ),
    }


@router.post("/setup")
def setup(
    payload: PasswordProof,
    request: Request,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict:
    proof(db, request, user, session, payload)
    item = mfa.credential(db, user.id)
    if item is None:
        item = MfaCredential(user_id=user.id)
        db.add(item)
    secret = pyotp.random_base32()
    item.pending_secret = mfa.cipher().encrypt(secret.encode()).decode()
    item.pending_expires_at = utcnow() + timedelta(minutes=10)
    item.pending_session_id = session.id
    result = mfa.provisioning(secret, user.email)
    mfa.event(db, user.id, "mfa.setup_started", user.id)
    db.commit()
    return {**result, "expires_in": 600}


@router.post("/confirm")
def confirm(
    payload: MfaCode,
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict:
    rate_limit(db, request, "mfa-confirm", user.id, limit=5)
    _locked_user(db, user, session)
    item = mfa.credential(db, user.id)
    if (
        not item
        or not item.pending_secret
        or item.pending_session_id != session.id
        or not item.pending_expires_at
        or aware(item.pending_expires_at) <= utcnow()
    ):
        raise HTTPException(400, "Configuração expirada. Inicie novamente.")
    step = mfa.matched_step(mfa.decrypt(item.pending_secret), payload.code.get_secret_value())
    if step is None:
        raise HTTPException(400, "Código inválido. Confira o relógio do autenticador.")
    item.secret = item.pending_secret
    item.pending_secret = None
    item.pending_expires_at = None
    item.pending_session_id = None
    item.enabled_at = utcnow()
    item.last_step = step
    item.reset_required = False
    codes = mfa.recovery_codes(db, user.id)
    # Cancel all sessions, links and outstanding challenges, then rotate this browser.
    user.token_version += 1
    revoke_sessions(db, user.id)
    fresh, raw = new_session(db, user, request.headers.get("user-agent", ""))
    fresh.mfa_verified = True
    mfa.event(db, user.id, "mfa.enabled", user.id)
    db.commit()
    set_session_cookie(response, raw)
    return {"recovery_codes": codes}


@router.post("/recovery-codes")
def regenerate(
    payload: PasswordProof,
    request: Request,
    user: User = Depends(require_user),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict:
    proof(db, request, user, session, payload)
    item = mfa.credential(db, user.id)
    if not item or not item.secret:
        raise HTTPException(409, "Ative o MFA primeiro.")
    codes = mfa.recovery_codes(db, user.id)
    mfa.event(db, user.id, "mfa.recovery_regenerated", user.id)
    db.commit()
    return {"recovery_codes": codes}


@router.post("/reset/{user_id}", status_code=204)
def admin_reset(
    user_id: str,
    payload: MfaReset,
    request: Request,
    actor: User = Depends(require_admin),
    session: LoginSession = Depends(require_session),
    db: Session = Depends(get_db),
) -> None:
    proof(db, request, actor, session, payload)
    # A password-only admin must not be able to defeat another user's MFA.
    actor_mfa = mfa.credential(db, actor.id)
    if not actor_mfa or not actor_mfa.secret or not session.mfa_verified:
        raise HTTPException(403, "Ative o MFA na sua conta antes de recuperar outra conta.")
    if actor.id == user_id:
        raise HTTPException(
            400, "Para sua conta, use Trocar autenticador ou a recuperação pelo host."
        )
    user = db.get(User, user_id, populate_existing=True)
    if not user or not user.is_active or not user.password_set:
        raise HTTPException(404, "Conta ativa não encontrada.")
    mfa.reset_mfa(db, user, actor.id, payload.reason.strip())
    db.commit()


@router.get("/events")
def events(user: User = Depends(require_user), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"action": item.action, "created_at": item.created_at, "actor_id": item.actor_id}
        for item in db.scalars(
            select(SecurityEvent)
            .where(SecurityEvent.user_id == user.id)
            .order_by(SecurityEvent.created_at.desc())
            .limit(50)
        )
    ]
