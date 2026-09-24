from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.auth import LoginSession
from app.models.mfa import SecurityEvent
from app.services.authentication import digest
from app.tests.test_security import PASSWORD, headers
from app.tests.test_security import auth_env as auth_env


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_admin_settings_reads_and_mutations_are_restricted(auth_env, role):
    http, _, tokens, ids = auth_env
    for path in ["/users", "/audit", f"/users/{ids['admin']}/sessions"]:
        assert http.get("/api/v1" + path, headers=headers(tokens, role)).status_code == 403
    assert (
        http.delete(
            f"/api/v1/users/{ids['admin']}/sessions/unknown", headers=headers(tokens, role)
        ).status_code
        == 403
    )
    assert http.get("/api/v1/auth/sessions", headers=headers(tokens, role)).status_code == 200


def test_user_filters_pagination_and_safe_admin_metadata(auth_env):
    http, _, tokens, _ = auth_env
    invite = http.post(
        "/api/v1/users/invitations",
        headers=headers(tokens),
        json={"name": "Pending", "email": "pending@example.com"},
    )
    assert invite.status_code == 201
    active = http.get("/api/v1/users?state=active", headers=headers(tokens)).json()
    assert len(active) == 3
    pending = http.get("/api/v1/users?state=pending", headers=headers(tokens)).json()
    assert len(pending) == 1 and pending[0]["email"] == "pending@example.com"
    assert pending[0]["mfa_enabled"] is False
    assert not {"secret", "password_hash", "token_version"} & pending[0].keys()
    assert len(http.get("/api/v1/users?q=VIEWER", headers=headers(tokens)).json()) == 1
    assert http.get("/api/v1/users?q=%25", headers=headers(tokens)).json() == []
    first = http.get("/api/v1/users?limit=2", headers=headers(tokens)).json()
    second = http.get("/api/v1/users?limit=2&offset=2", headers=headers(tokens)).json()
    assert len({u["id"] for u in first + second}) == 4


def test_administration_is_audited_without_link_or_password(auth_env):
    http, _, tokens, _ = auth_env
    response = http.post(
        "/api/v1/users",
        headers=headers(tokens),
        json={"name": "Guest", "email": "guest@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    assert (
        http.patch(
            f"/api/v1/users/{user_id}",
            headers=headers(tokens),
            json={"name": "New name", "role": "operator"},
        ).status_code
        == 200
    )
    link = http.post(f"/api/v1/users/{user_id}/password-reset", headers=headers(tokens)).json()[
        "url"
    ]
    response = http.get(f"/api/v1/audit?category=user&user_id={user_id}", headers=headers(tokens))
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["total"] == 3
    assert {row["action"] for row in data["items"]} == {
        "user.created",
        "user.updated",
        "user.password_reset_issued",
    }
    assert all(row["actor_email"] == "admin@example.com" for row in data["items"])
    assert PASSWORD not in response.text and link not in response.text
    assert not any("token" in row["reason"] for row in data["items"])
    page = http.get(
        f"/api/v1/audit?user_id={user_id}&limit=1&offset=1", headers=headers(tokens)
    ).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert page["items"][0]["id"] == data["items"][1]["id"]


def test_failed_changes_do_not_create_success_audit(auth_env):
    http, engine, tokens, ids = auth_env
    assert (
        http.patch(
            f"/api/v1/users/{ids['admin']}", headers=headers(tokens), json={"is_active": False}
        ).status_code
        == 409
    )
    assert (
        http.patch(
            f"/api/v1/users/{ids['viewer']}",
            headers=headers(tokens),
            json={"email": "admin@example.com"},
        ).status_code
        == 409
    )
    with Session(engine) as db:
        assert (
            db.scalar(select(SecurityEvent).where(SecurityEvent.action == "user.updated")) is None
        )


def test_individual_admin_revocation_is_scoped_and_requires_reauthentication(auth_env):
    http, engine, tokens, ids = auth_env
    sessions = http.get(f"/api/v1/users/{ids['viewer']}/sessions", headers=headers(tokens)).json()
    assert len(sessions) == 1 and "token_hash" not in sessions[0]
    sid = sessions[0]["id"]
    assert (
        http.delete(
            f"/api/v1/users/{ids['operator']}/sessions/{sid}", headers=headers(tokens)
        ).status_code
        == 404
    )
    with Session(engine) as db:
        db.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(tokens["admin"]))
        ).reauthenticated_at = utcnow() - timedelta(minutes=6)
        db.commit()
    path = f"/api/v1/users/{ids['viewer']}/sessions/{sid}"
    assert http.delete(path, headers=headers(tokens)).status_code == 403
    assert (
        http.post(
            "/api/v1/auth/reauthenticate", json={"password": PASSWORD}, headers=headers(tokens)
        ).status_code
        == 204
    )
    assert http.delete(path, headers=headers(tokens)).status_code == 204
    assert http.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).status_code == 401
    audit = http.get("/api/v1/audit?category=user", headers=headers(tokens)).json()
    assert audit["items"][0]["action"] == "user.session_revoked"


def test_login_and_logout_audit_uses_known_subject_without_claiming_failed_actor(auth_env):
    http, engine, tokens, ids = auth_env
    assert (
        http.post(
            "/api/v1/auth/login", json={"email": "viewer@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    response = http.post(
        "/api/v1/auth/login", json={"email": "viewer@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert http.post("/api/v1/auth/logout", headers=headers(tokens, "viewer")).status_code == 204
    with Session(engine) as db:
        rows = list(db.scalars(select(SecurityEvent).where(SecurityEvent.user_id == ids["viewer"])))
        assert {row.action for row in rows} == {"auth.login_failed", "auth.login", "auth.logout"}
        assert next(row for row in rows if row.action == "auth.login_failed").actor_id is None
