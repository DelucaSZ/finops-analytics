"""TOTP secrets and one-time proofs. Mutations require lock_user_changes()."""

import base64
import io
import secrets
from datetime import timedelta

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.mfa import MfaChallenge, MfaCredential, RecoveryCode, SecurityEvent
from app.models.user import User
from app.services.authentication import digest, revoke_sessions


def cipher() -> Fernet:
    explicit = settings.mfa_encryption_key.get_secret_value()
    if explicit:
        return Fernet(explicit.encode())
    if len(settings.secret_key) < 32 or settings.secret_key.startswith(
        ("development-only", "replace-with")
    ):
        raise HTTPException(503, "Configure uma chave segura no servidor antes de usar MFA.")
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"deepops:totp:v1").derive(
        settings.secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def decrypt(value: str) -> str:
    try:
        return cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise HTTPException(503, "Chave MFA indisponível. Contate o administrador.") from None


def credential(db: Session, user_id: str) -> MfaCredential | None:
    return db.get(MfaCredential, user_id, populate_existing=True)


def enrollment_required(item: MfaCredential | None) -> bool:
    return not (item and item.secret) and bool(
        settings.mfa_required or (item and item.reset_required)
    )


def event(db: Session, user_id: str, action: str, actor_id: str | None, reason: str = "") -> None:
    db.add(SecurityEvent(user_id=user_id, action=action, actor_id=actor_id, reason=reason))


def matched_step(secret: str, code: str, last_step: int = -1) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    step = int(utcnow().timestamp()) // 30
    totp = pyotp.TOTP(secret, digits=6, interval=30)
    for candidate in (step, step - 1, step + 1):
        if candidate > last_step and secrets.compare_digest(totp.at(candidate * 30), code):
            return candidate
    return None


def verify_factor(db: Session, item: MfaCredential, code: str, *, recovery: bool = True) -> bool:
    if not item.secret:
        return False
    step = matched_step(decrypt(item.secret), code, item.last_step)
    if step is not None:
        item.last_step = step
        return True
    if recovery:
        normalized = code.replace("-", "").strip().upper()
        if len(normalized) != 32:
            return False
        row = db.scalar(
            select(RecoveryCode).where(
                RecoveryCode.user_id == item.user_id,
                RecoveryCode.code_hash == digest(item.user_id + ":" + normalized),
                RecoveryCode.used_at.is_(None),
            )
        )
        if row:
            row.used_at = utcnow()
            event(db, item.user_id, "mfa.recovery_used", item.user_id)
            return True
    return False


def require_factor(db: Session, user: User, code: str) -> None:
    item = credential(db, user.id)
    if item and item.secret and not verify_factor(db, item, code):
        raise HTTPException(400, "Código inválido ou já utilizado. Aguarde o próximo código.")
    db.flush()


def recovery_codes(db: Session, user_id: str) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    codes = [secrets.token_hex(16).upper() for _ in range(10)]
    for code in codes:
        db.add(RecoveryCode(user_id=user_id, code_hash=digest(user_id + ":" + code)))
    return ["-".join(code[i : i + 4] for i in range(0, 32, 4)) for code in codes]


def challenge(db: Session, user: User) -> str:
    now = utcnow()
    db.execute(delete(MfaChallenge).where(MfaChallenge.expires_at < now))
    # Only the latest password verification may be completed.
    db.execute(delete(MfaChallenge).where(MfaChallenge.user_id == user.id))
    raw = secrets.token_urlsafe(32)
    db.add(
        MfaChallenge(
            token_hash=digest(raw),
            user_id=user.id,
            user_version=user.token_version,
            expires_at=now + timedelta(minutes=5),
        )
    )
    return raw


def provisioning(secret: str, email: str) -> dict:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="DeepOps")
    image = qrcode.make(uri)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return {
        "secret": secret,
        "qr_code": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
    }


def reset_mfa(db: Session, user: User, actor_id: str | None, reason: str) -> None:
    item = credential(db, user.id)
    if item is None:
        item = MfaCredential(user_id=user.id)
        db.add(item)
    item.secret = None
    item.enabled_at = None
    item.pending_secret = None
    item.pending_session_id = None
    item.pending_expires_at = None
    item.last_step = -1
    item.reset_required = True
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.execute(delete(MfaChallenge).where(MfaChallenge.user_id == user.id))
    user.token_version += 1
    revoke_sessions(db, user.id)
    event(db, user.id, "mfa.reset", actor_id, reason)
