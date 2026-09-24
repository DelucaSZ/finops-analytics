from datetime import timedelta

import pyotp
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.auth import LoginSession
from app.models.mfa import MfaChallenge, MfaCredential, RecoveryCode, SecurityEvent
from app.models.user import User
from app.services import mfa
from app.services.authentication import COOKIE, csrf_token, digest, issue_token
from app.tests.test_security import PASSWORD, headers
from app.tests.test_security import auth_env as auth_env


@pytest.fixture(autouse=True)
def mfa_config(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "Test-MFA-secret-key-that-is-at-least-32-bytes")
    monkeypatch.setattr(settings, "mfa_required", False)
    monkeypatch.setattr(settings, "mfa_encryption_key", SecretStr(""))


@pytest.fixture
def clock(monkeypatch):
    now = [utcnow()]
    monkeypatch.setattr(mfa, "utcnow", lambda: now[0])

    def code(secret, *, advance=True):
        if advance:
            now[0] += timedelta(seconds=30)
        return pyotp.TOTP(secret).at(now[0])

    return code


def session_headers(http):
    raw = http.cookies.get(COOKIE)
    return {"Cookie": f"{COOKIE}={raw}", "X-CSRF-Token": csrf_token(raw)}


def enable(env, clock, role="admin"):
    http, _, tokens, _ = env
    response = http.post(
        "/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=headers(tokens, role)
    )
    assert response.status_code == 200, response.text
    secret = response.json()["secret"]
    assert response.json()["qr_code"].startswith("data:image/png;base64,")
    confirm = http.post(
        "/api/v1/auth/mfa/confirm", json={"code": clock(secret)}, headers=headers(tokens, role)
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"], session_headers(http)


def login(http, role="admin", password=PASSWORD):
    response = http.post(
        "/api/v1/auth/login", json={"email": f"{role}@example.com", "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def finish(http, challenge, code):
    return http.post("/api/v1/auth/mfa/verify", json={"challenge": challenge, "code": code})


def test_activation_encrypted_confirmed_and_revokes_old_sessions(auth_env, clock):
    http, engine, tokens, ids = auth_env
    secret, codes, fresh = enable(auth_env, clock)
    assert len(codes) == len(set(codes)) == 10
    assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 401
    assert http.get("/api/v1/auth/me", headers=fresh).status_code == 200
    status = http.get("/api/v1/auth/mfa/status", headers=fresh).json()
    assert status["enabled"] and status["recovery_codes_remaining"] == 10
    assert secret not in str(status) and codes[0] not in str(status)
    with Session(engine) as db:
        item = db.get(MfaCredential, ids["admin"])
        assert item.secret != secret and mfa.decrypt(item.secret) == secret
        assert item.pending_secret is None
        assert len(list(db.scalars(select(RecoveryCode)))) == 10
        assert all(row.code_hash != codes[0] for row in db.scalars(select(RecoveryCode)))
        assert db.scalar(select(SecurityEvent).where(SecurityEvent.action == "mfa.enabled"))


def test_password_only_login_cannot_access_business_or_create_session(auth_env, clock):
    http, engine, _, _ = auth_env
    secret, _, _ = enable(auth_env, clock)
    with Session(engine) as db:
        count = db.scalar(select(func.count()).select_from(LoginSession))
    pending = login(http)
    assert pending["mfa_required"] and len(pending["challenge"]) == 43
    assert not http.cookies.get(COOKIE)
    assert http.get("/api/v1/accounts").status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginSession)) == count
        assert db.scalar(select(MfaChallenge)).token_hash == digest(pending["challenge"])
    result = finish(http, pending["challenge"], clock(secret))
    assert result.status_code == 200 and "HttpOnly" in result.headers["set-cookie"]
    assert result.headers["cache-control"] == "no-store"
    assert http.get("/api/v1/accounts").status_code == 200
    assert finish(http, pending["challenge"], clock(secret)).status_code == 400


def test_totp_cannot_be_replayed_even_in_another_challenge(auth_env, clock):
    http, _, _, _ = auth_env
    secret, _, _ = enable(auth_env, clock)
    pending = login(http)["challenge"]
    assert finish(http, pending, clock(secret, advance=False)).status_code == 400
    code = clock(secret)
    assert finish(http, pending, code).status_code == 200
    pending = login(http)["challenge"]
    assert finish(http, pending, code).status_code == 400
    assert finish(http, pending, clock(secret)).status_code == 200


@pytest.mark.parametrize("failure", ["expired", "attempts", "disabled", "version", "replaced"])
def test_challenges_fail_closed(auth_env, clock, failure):
    http, engine, _, ids = auth_env
    secret, _, _ = enable(auth_env, clock)
    pending = login(http)["challenge"]
    with Session(engine) as db:
        row = db.get(MfaChallenge, digest(pending))
        user = db.get(User, ids["admin"])
        if failure == "expired":
            row.expires_at = utcnow() - timedelta(seconds=1)
        elif failure == "attempts":
            row.attempts = 5
        elif failure == "disabled":
            user.is_active = False
        elif failure == "version":
            user.token_version += 1
        db.commit()
    if failure == "replaced":
        login(http)
    assert finish(http, pending, clock(secret)).status_code == 400
    assert http.get("/api/v1/accounts").status_code == 401


def test_failed_codes_are_limited_and_audited(auth_env, clock):
    http, engine, _, _ = auth_env
    enable(auth_env, clock)
    pending = login(http)["challenge"]
    for _ in range(5):
        assert finish(http, pending, "xxxxxx").status_code == 400
    assert finish(http, pending, "xxxxxx").status_code == 429
    with Session(engine) as db:
        assert db.get(MfaChallenge, digest(pending)).attempts == 5
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.action == "mfa.login_failed")
            )
            == 5
        )


def test_recovery_codes_are_single_use_and_rotation_invalidates_old_codes(auth_env, clock):
    http, engine, _, _ = auth_env
    secret, codes, _ = enable(auth_env, clock)
    assert finish(http, login(http)["challenge"], codes[0].lower()).status_code == 200
    current = session_headers(http)
    assert http.get("/api/v1/auth/mfa/status").json()["recovery_codes_remaining"] == 9
    result = http.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"password": PASSWORD, "code": clock(secret)},
        headers=current,
    )
    assert result.status_code == 200
    pending = login(http)["challenge"]
    assert finish(http, pending, codes[0]).status_code == 400
    assert finish(http, pending, codes[1]).status_code == 400
    assert finish(http, pending, result.json()["recovery_codes"][0]).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(SecurityEvent).where(SecurityEvent.action == "mfa.recovery_used"))


def test_password_reset_does_not_disable_mfa(auth_env, clock):
    http, engine, _, ids = auth_env
    secret, _, _ = enable(auth_env, clock)
    with Session(engine) as db:
        raw, _ = issue_token(db, db.get(User, ids["admin"]), "reset")
        db.commit()
    password = "A-new-password-for-MFA-789"
    assert (
        http.post(
            "/api/v1/auth/reset-password", json={"token": raw, "password": password}
        ).status_code
        == 200
    )
    pending = login(http, password=password)
    assert pending["mfa_required"]
    assert finish(http, pending["challenge"], clock(secret)).status_code == 200


def test_required_enrollment_restricts_all_business_routes(auth_env, monkeypatch, clock):
    http, _, tokens, _ = auth_env
    monkeypatch.setattr(settings, "mfa_required", True)
    for path in ["/accounts", "/findings", "/auth/me", "/users", "/auth/sessions"]:
        response = http.get("/api/v1" + path, headers=headers(tokens))
        assert (
            response.status_code == 403 and response.json()["detail"] == "mfa_enrollment_required"
        )
    assert login(http)["enrollment_required"]
    _, _, fresh = enable(auth_env, clock)
    assert http.get("/api/v1/accounts", headers=fresh).status_code == 200


def test_setup_is_bound_to_session_and_expires(auth_env, clock):
    http, engine, tokens, ids = auth_env
    response = http.post(
        "/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=headers(tokens)
    )
    secret = response.json()["secret"]
    login(http)
    other = session_headers(http)
    assert (
        http.post(
            "/api/v1/auth/mfa/confirm", json={"code": clock(secret)}, headers=other
        ).status_code
        == 400
    )
    with Session(engine) as db:
        db.get(MfaCredential, ids["admin"]).pending_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert (
        http.post(
            "/api/v1/auth/mfa/confirm", json={"code": clock(secret)}, headers=headers(tokens)
        ).status_code
        == 400
    )
    assert not http.get("/api/v1/auth/mfa/status", headers=other).json()["enabled"]


def test_replacement_keeps_old_factor_until_confirmation(auth_env, clock):
    http, _, _, _ = auth_env
    secret, _, fresh = enable(auth_env, clock)
    assert (
        http.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=fresh).status_code
        == 400
    )
    result = http.post(
        "/api/v1/auth/mfa/setup", json={"password": PASSWORD, "code": clock(secret)}, headers=fresh
    )
    assert result.status_code == 200
    replacement = result.json()["secret"]
    assert finish(http, login(http)["challenge"], clock(secret)).status_code == 200
    assert finish(http, login(http)["challenge"], clock(replacement)).status_code == 400


@pytest.mark.parametrize(
    "path,payload",
    [
        ("reauthenticate", {"password": PASSWORD}),
        ("change-password", {"current_password": PASSWORD, "new_password": "Another-password-42!"}),
    ],
)
def test_sensitive_operations_require_second_factor(auth_env, clock, path, payload):
    http, _, _, _ = auth_env
    secret, _, fresh = enable(auth_env, clock)
    assert http.post("/api/v1/auth/" + path, json=payload, headers=fresh).status_code == 400
    assert (
        http.post(
            "/api/v1/auth/" + path, json={**payload, "code": clock(secret)}, headers=fresh
        ).status_code
        == 204
    )


def test_admin_recovery_requires_mfa_and_forces_reenrollment(auth_env, clock):
    http, engine, tokens, ids = auth_env
    path = f"/api/v1/auth/mfa/reset/{ids['viewer']}"
    body = {"password": PASSWORD, "reason": "Identity verified through internal support"}
    assert http.post(path, json=body, headers=headers(tokens, "operator")).status_code == 403
    assert http.post(path, json=body, headers=headers(tokens)).status_code == 403
    secret, _, fresh = enable(auth_env, clock)
    assert http.post(path, json={**body, "code": clock(secret)}, headers=fresh).status_code == 204
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 401
    assert login(http, "viewer")["enrollment_required"]
    assert http.get("/api/v1/accounts").status_code == 403
    with Session(engine) as db:
        item = db.scalar(select(SecurityEvent).where(SecurityEvent.action == "mfa.reset"))
        assert item.actor_id == ids["admin"] and item.reason == body["reason"]
        assert db.get(MfaCredential, ids["viewer"]).reset_required


def test_encryption_key_failure_does_not_fall_back_to_password(auth_env, clock, monkeypatch):
    http, _, _, _ = auth_env
    secret, _, _ = enable(auth_env, clock)
    pending = login(http)["challenge"]
    monkeypatch.setattr(settings, "secret_key", "A-different-key-for-testing-decryption-failure")
    assert finish(http, pending, clock(secret)).status_code == 503
    assert http.get("/api/v1/accounts").status_code == 401


def test_setup_rejects_default_key_and_missing_csrf(auth_env, monkeypatch):
    http, _, tokens, _ = auth_env
    assert (
        http.post(
            "/api/v1/auth/mfa/setup",
            json={"password": PASSWORD},
            headers={"Cookie": f"{COOKIE}={tokens['admin']}"},
        ).status_code
        == 403
    )
    monkeypatch.setattr(settings, "secret_key", "development-only-change-me-at-least-32-bytes")
    assert (
        http.post(
            "/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=headers(tokens)
        ).status_code
        == 503
    )


def test_totp_standard_vector_and_clock_window(monkeypatch):
    import base64
    from datetime import UTC, datetime

    # RFC 6238 SHA-1 vector at t=59; truncate to the configured six digits.
    secret = base64.b32encode(b"12345678901234567890").decode()
    monkeypatch.setattr(mfa, "utcnow", lambda: datetime.fromtimestamp(59, UTC))
    assert mfa.matched_step(secret, "287082") == 1
    assert mfa.matched_step(secret, "287082", last_step=1) is None
    assert mfa.matched_step(secret, pyotp.TOTP(secret).at(90)) is None
    assert mfa.matched_step(secret, "２８７０８２") is None


def test_completed_replacement_invalidates_old_factor_and_recovery(auth_env, clock):
    http, _, _, _ = auth_env
    old, old_codes, fresh = enable(auth_env, clock)
    response = http.post(
        "/api/v1/auth/mfa/setup", json={"password": PASSWORD, "code": clock(old)}, headers=fresh
    )
    new = response.json()["secret"]
    confirmed = http.post("/api/v1/auth/mfa/confirm", json={"code": clock(new)}, headers=fresh)
    assert confirmed.status_code == 200
    assert http.get("/api/v1/auth/me", headers=fresh).status_code == 401
    pending = login(http)["challenge"]
    assert finish(http, pending, clock(old)).status_code == 400
    assert finish(http, pending, old_codes[0]).status_code == 400
    assert finish(http, pending, clock(new)).status_code == 200


def test_host_reset_audits_and_requires_new_enrollment(auth_env, clock):
    from app.services.users import lock_user_changes

    http, engine, _, ids = auth_env
    _, codes, fresh = enable(auth_env, clock)
    pending = login(http)["challenge"]
    with Session(engine) as db:
        lock_user_changes(db)
        mfa.reset_mfa(db, db.get(User, ids["admin"]), None, "Host operator verified account owner")
        db.commit()
    assert finish(http, pending, codes[0]).status_code == 400
    assert http.get("/api/v1/auth/me", headers=fresh).status_code == 401
    assert login(http)["enrollment_required"]
    assert http.get("/api/v1/accounts").status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 0
        assert (
            db.scalar(select(SecurityEvent).where(SecurityEvent.action == "mfa.reset")).actor_id
            is None
        )


def test_mfa_proof_consumption_survives_setup_refresh(auth_env, clock):
    http, _, _, _ = auth_env
    secret, _, fresh = enable(auth_env, clock)
    code = clock(secret)
    assert (
        http.post(
            "/api/v1/auth/mfa/setup", json={"password": PASSWORD, "code": code}, headers=fresh
        ).status_code
        == 200
    )
    assert (
        http.post(
            "/api/v1/auth/reauthenticate", json={"password": PASSWORD, "code": code}, headers=fresh
        ).status_code
        == 400
    )
