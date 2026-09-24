from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.db.base import utcnow
from app.models.auth import AccessToken, AuthRateLimit, LoginSession
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, digest, new_session
from app.tests.test_security import PASSWORD, headers
from app.tests.test_security import auth_env as auth_env

NEW_PASSWORD = "A-new-strong-password-987!"


def link_token(response):
    assert response.status_code in (200, 201), response.text
    return parse_qs(urlsplit(response.json()["url"]).fragment)["token"][0]


def reset_link(env, role="viewer"):
    http, _, tokens, ids = env
    return link_token(
        http.post(f"/api/v1/users/{ids[role]}/password-reset", headers=headers(tokens))
    )


def complete(http, token, purpose="reset-password"):
    return http.post(f"/api/v1/auth/{purpose}", json={"token": token, "password": NEW_PASSWORD})


def test_cookie_and_storage_contract(auth_env, monkeypatch):
    http, engine, _, _ = auth_env
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = http.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Domain=" not in cookie and "Path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    raw = http.cookies.get(COOKIE)
    assert raw not in response.text
    with Session(engine) as db:
        row = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(raw)))
        assert row and row.token_hash != raw


@pytest.mark.parametrize("mutation", ["missing", "wrong", "other-session", "origin"])
def test_csrf_and_origin_are_enforced(auth_env, mutation):
    http, _, tokens, _ = auth_env
    request_headers = headers(tokens)
    if mutation == "missing":
        del request_headers["X-CSRF-Token"]
    elif mutation == "wrong":
        request_headers["X-CSRF-Token"] = "invalid"
    elif mutation == "other-session":
        request_headers["X-CSRF-Token"] = csrf_token(tokens["viewer"])
    else:
        request_headers["Origin"] = "https://attacker.example"
    assert http.post("/api/v1/auth/logout", headers=request_headers).status_code == 403
    assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 200


def test_login_requires_browser_protection(auth_env):
    http, _, _, _ = auth_env
    del http.headers["X-DeepOps-Request"]
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
        ).status_code
        == 403
    )
    assert (
        http.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": PASSWORD},
            headers={"X-DeepOps-Request": "1", "Origin": "null"},
        ).status_code
        == 403
    )


def test_logout_revokes_captured_cookie_and_survives_new_request(auth_env):
    http, _, tokens, _ = auth_env
    response = http.post("/api/v1/auth/logout", headers=headers(tokens))
    assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
    assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 401
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 200


@pytest.mark.parametrize("field", ["expires_at", "last_seen_at"])
def test_expired_session_cannot_be_revived(auth_env, field):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        item = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(tokens["admin"]))
        )
        setattr(item, field, utcnow() - timedelta(days=2))
        db.commit()
    for _ in range(2):
        assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 401


def test_relogin_rotates_and_invalidates_previous_cookie(auth_env):
    http, _, tokens, _ = auth_env
    result = http.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": PASSWORD},
        headers=headers(tokens),
    )
    assert result.status_code == 200
    assert http.cookies.get(COOKIE) != tokens["admin"]
    assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 401
    assert http.get("/api/v1/auth/me").status_code == 200


def test_sessions_are_scoped_and_logout_all_revokes_every_device(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        _, second = new_session(db, db.get(User, ids["admin"]), "Second device")
        db.commit()
    own = http.get("/api/v1/auth/sessions", headers=headers(tokens)).json()
    assert len(own) == 2 and sum(item["current"] for item in own) == 1
    assert all("token_hash" not in item for item in own)
    other = http.get("/api/v1/auth/sessions", headers=headers(tokens, "viewer")).json()[0]
    assert (
        http.delete(f"/api/v1/auth/sessions/{other['id']}", headers=headers(tokens)).status_code
        == 404
    )
    assert http.post("/api/v1/auth/logout-all", headers=headers(tokens)).status_code == 204
    for raw in [tokens["admin"], second]:
        assert http.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE}={raw}"}).status_code == 401
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 200


def test_admin_can_revoke_user_sessions_but_viewer_cannot(auth_env):
    http, _, tokens, ids = auth_env
    path = f"/api/v1/users/{ids['operator']}/sessions"
    assert http.delete(path, headers=headers(tokens, "viewer")).status_code == 403
    assert http.delete(path, headers=headers(tokens)).status_code == 204
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "operator")).status_code == 401


def test_password_change_invalidates_sessions_and_reset_links(auth_env):
    http, _, tokens, _ = auth_env
    raw = reset_link(auth_env)
    assert (
        http.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": NEW_PASSWORD},
            headers=headers(tokens, "viewer"),
        ).status_code
        == 400
    )
    assert (
        http.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers(tokens, "viewer"),
        ).status_code
        == 204
    )
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 401
    assert complete(http, raw).status_code == 400
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "viewer@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "viewer@example.com", "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_invite_activation_and_single_use(auth_env):
    http, engine, tokens, _ = auth_env
    response = http.post(
        "/api/v1/users/invitations",
        json={"name": "Guest", "email": "guest@example.com"},
        headers=headers(tokens),
    )
    raw = link_token(response)
    user_id = response.json()["user"]["id"]
    assert response.json()["user"]["password_set"] is False
    assert response.headers["cache-control"] == "no-store"
    with Session(engine) as db:
        user = db.get(User, user_id)
        # Even a known valid hash does not activate a pending invitation.
        user.password_hash = db.scalar(
            select(User).where(User.email == "admin@example.com")
        ).password_hash
        item = db.scalar(select(AccessToken).where(AccessToken.user_id == user_id))
        assert item.token_hash == digest(raw) and item.token_hash != raw
        db.commit()
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "guest@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert complete(http, raw, "accept-invitation").status_code == 200
    assert complete(http, raw, "accept-invitation").status_code == 400
    assert (
        http.get("/api/v1/auth/me").status_code == 401
    )  # Activation does not automatically sign in.
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "guest@example.com", "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_pending_admin_does_not_allow_last_real_admin_to_be_removed(auth_env):
    http, _, tokens, ids = auth_env
    assert (
        http.post(
            "/api/v1/users/invitations",
            json={"name": "Pending", "email": "pending@example.com", "role": "admin"},
            headers=headers(tokens),
        ).status_code
        == 201
    )
    assert (
        http.patch(
            f"/api/v1/users/{ids['admin']}", json={"is_active": False}, headers=headers(tokens)
        ).status_code
        == 409
    )


def test_invitation_reissue_invalidates_first_link(auth_env):
    http, _, tokens, _ = auth_env
    response = http.post(
        "/api/v1/users/invitations",
        json={"name": "Guest", "email": "guest@example.com"},
        headers=headers(tokens),
    )
    first = link_token(response)
    second = link_token(
        http.post(
            f"/api/v1/users/{response.json()['user']['id']}/invitation", headers=headers(tokens)
        )
    )
    assert complete(http, first, "accept-invitation").status_code == 400
    assert complete(http, second, "accept-invitation").status_code == 200


def test_reset_single_use_and_no_automatic_login(auth_env):
    http, _, tokens, _ = auth_env
    raw = reset_link(auth_env)
    assert complete(http, raw, "accept-invitation").status_code == 400
    assert complete(http, raw).status_code == 200
    assert complete(http, raw).status_code == 400
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 401
    assert http.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("change", ["expired", "disabled", "email", "role"])
def test_changed_account_or_expired_link_cannot_reset_password(auth_env, change):
    http, engine, tokens, ids = auth_env
    raw = reset_link(auth_env)
    if change == "expired":
        with Session(engine) as db:
            item = db.scalar(select(AccessToken).where(AccessToken.token_hash == digest(raw)))
            item.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
    else:
        fields = {
            "disabled": {"is_active": False},
            "email": {"email": "changed@example.com"},
            "role": {"role": "operator"},
        }
        assert (
            http.patch(
                f"/api/v1/users/{ids['viewer']}", json=fields[change], headers=headers(tokens)
            ).status_code
            == 200
        )
    assert complete(http, raw).status_code == 400


def test_public_recovery_does_not_reveal_accounts_or_tokens(auth_env, monkeypatch):
    http, engine, _, _ = auth_env
    from app.services import mailer

    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "public_url", "https://deepops.example.com")
    monkeypatch.setattr(mailer, "send_link", lambda *args: sent.append(args))
    responses = [
        http.post("/api/v1/auth/forgot-password", json={"email": address})
        for address in ["viewer@example.com", "unknown@example.com"]
    ]
    assert responses[0].status_code == responses[1].status_code == 202
    assert responses[0].json() == responses[1].json()
    assert "token" not in responses[0].text and "url" not in responses[0].json()
    assert len(sent) == 1 and sent[0][0] == "viewer@example.com"
    assert sent[0][1].startswith("https://deepops.example.com/reset-password#token=")
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AccessToken)) == 1


def test_public_recovery_without_mail_or_on_mail_failure_is_generic(auth_env, monkeypatch):
    http, _, _, _ = auth_env
    from app.services import mailer

    def fail(*args):
        raise RuntimeError("Do not leak SMTP information")

    monkeypatch.setattr(settings, "smtp_host", "")
    first = http.post("/api/v1/auth/forgot-password", json={"email": "viewer@example.com"})
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(mailer, "send_link", fail)
    second = http.post("/api/v1/auth/forgot-password", json={"email": "viewer@example.com"})
    assert first.status_code == second.status_code == 202 and first.json() == second.json()
    assert "SMTP" not in second.text


def test_rate_limits_persist_in_database(auth_env):
    http, engine, _, _ = auth_env
    for _ in range(10):
        assert (
            http.post(
                "/api/v1/auth/login", json={"email": "absent@example.com", "password": "wrong"}
            ).status_code
            == 401
        )
    response = http.post(
        "/api/v1/auth/login", json={"email": "absent@example.com", "password": "wrong"}
    )
    assert response.status_code == 429 and "Retry-After" in response.headers
    with Session(engine) as db:
        assert db.scalar(select(func.max(AuthRateLimit.attempts))) == 11


def test_recovery_rate_limit_is_generic_and_does_not_flood_mail(auth_env, monkeypatch):
    http, _, _, _ = auth_env
    from app.services import mailer

    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(mailer, "send_link", lambda *args: sent.append(args))
    for _ in range(5):
        assert (
            http.post(
                "/api/v1/auth/forgot-password", json={"email": "viewer@example.com"}
            ).status_code
            == 202
        )
    assert len(sent) == 3


def test_sensitive_admin_actions_require_recent_password(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        item = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(tokens["admin"]))
        )
        item.reauthenticated_at = utcnow() - timedelta(minutes=6)
        db.commit()
    path = f"/api/v1/users/{ids['viewer']}/password-reset"
    assert http.post(path, headers=headers(tokens)).status_code == 403
    assert (
        http.post(
            "/api/v1/auth/reauthenticate", json={"password": "wrong"}, headers=headers(tokens)
        ).status_code
        == 400
    )
    assert (
        http.post(
            "/api/v1/auth/reauthenticate", json={"password": PASSWORD}, headers=headers(tokens)
        ).status_code
        == 204
    )
    assert http.post(path, headers=headers(tokens)).status_code == 200


def test_production_config_requires_secure_cookies_and_valid_urls():
    assert Settings(NUVEMIQ_ENVIRONMENT="production").secure_cookies
    with pytest.raises(ValueError):
        Settings(NUVEMIQ_ENVIRONMENT="production", NUVEMIQ_COOKIE_SECURE=False)
    for url in [
        "javascript:alert(1)",
        "https://user:pass@example.com",
        "https://example.com/redirect?evil=1",
    ]:
        with pytest.raises(ValueError):
            Settings(NUVEMIQ_PUBLIC_URL=url)


def test_privileged_recovery_uses_same_expiring_single_use_flow(auth_env):
    http, engine, tokens, ids = auth_env
    from app.manage import recovery_link

    with Session(engine) as db:
        link = recovery_link(db, " ADMIN@EXAMPLE.COM ")
    raw = parse_qs(urlsplit(link).fragment)["token"][0]
    assert complete(http, raw).status_code == 200
    assert http.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 401
    assert complete(http, raw).status_code == 400
    with Session(engine) as db:
        with pytest.raises(ValueError):
            recovery_link(db, "missing@example.com")
        db.rollback()
        user = db.get(User, ids["viewer"])
        user.is_active = False
        db.commit()
        with pytest.raises(ValueError):
            recovery_link(db, "viewer@example.com")


def test_mail_delivery_requires_tls_and_uses_configured_origin(monkeypatch):
    from app.services import mailer

    events = []

    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert host == "smtp.example.com" and port == 587

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            events.append("tls")

        def login(self, username, password):
            assert events == ["tls"]
            events.append("login")

        def send_message(self, message):
            assert events == ["tls", "login"]
            assert message["To"] == "user@example.com"
            assert "https://deepops.example.com/reset-password#token=test" in message.get_content()
            events.append("sent")

    monkeypatch.setattr(mailer.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "mailer")
    monkeypatch.setattr(settings, "smtp_from", "deepops@example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_ssl", False)
    mailer.send_link(
        "user@example.com", "https://deepops.example.com/reset-password#token=test", "reset"
    )
    assert events == ["tls", "login", "sent"]
