from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.main as main
from app.core.config import Settings, settings
from app.core.passwords import verify_password
from app.db.migrations import initialize_database
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.user import User
from app.services.authentication import COOKIE, csrf_token, new_session

PASSWORD = "Test-only-password-482!"


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    initialize_database(
        engine,
        Settings(NUVEMIQ_ADMIN_EMAIL="admin@example.com", NUVEMIQ_ADMIN_PASSWORD=PASSWORD),
    )
    tokens, ids = {}, {}
    with Session(engine) as db:
        admin = db.scalar(select(User))
        for role in ("operator", "viewer"):
            db.add(
                User(
                    name=role,
                    email=f"{role}@example.com",
                    role=role,
                    password_hash=admin.password_hash,
                )
            )
        db.add(
            AwsAccount(
                id=1,
                name="Account",
                aws_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/FinOps",
                external_id="a" * 20,
            )
        )
        db.flush()
        db.add(Scan(id="existing", account_id=1, status="completed"))
        db.flush()
        db.add(
            Finding(
                id="finding",
                fingerprint="f" * 64,
                scan_id="existing",
                account_id=1,
                rule_key="ebs_unattached",
                service="EC2",
                region="sa-east-1",
                resource_id="vol-test",
                title="Test",
                description="Test",
                evidence={},
                severity="high",
                status="open",
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
            )
        )
        db.commit()
        for user in db.scalars(select(User)):
            _, tokens[user.role] = new_session(db, user)
            ids[user.role] = user.id
        db.commit()

    def database():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[get_db] = database
    with TestClient(main.app) as client:
        client.headers["X-DeepOps-Request"] = "1"
        yield client, engine, tokens, ids
    main.app.dependency_overrides.clear()
    engine.dispose()


def headers(tokens, role="admin"):
    return {
        "Cookie": f"{COOKIE}={tokens[role]}",
        "X-CSRF-Token": csrf_token(tokens[role]),
        "X-DeepOps-Request": "1",
    }


def test_login_uses_persisted_user_not_environment(auth_env, monkeypatch):
    client, engine, tokens, ids = auth_env
    monkeypatch.setattr(settings, "admin_password", "a-new-env-password")
    response = client.post(
        "/api/v1/auth/login", json={"email": " ADMIN@EXAMPLE.COM ", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["id"] == ids["admin"]
    assert "access_token" not in response.json()
    me = client.get("/api/v1/auth/me", headers=headers(tokens)).json()
    assert me["role"] == "admin"
    assert not {"password", "password_hash", "token_version"} & me.keys()
    for email, password in [
        ("admin@example.com", "a-new-env-password"),
        ("unknown@example.com", PASSWORD),
    ]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"
    with Session(engine) as db:
        user = db.get(User, ids["admin"])
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(PASSWORD, user.password_hash)


READ_PATHS = [
    "/auth/me",
    "/dashboard/summary",
    "/accounts",
    "/accounts/1",
    "/policies/global",
    "/policies/accounts/1",
    "/scans",
    "/scans/existing",
    "/findings",
]


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_all_roles_can_read(auth_env, role):
    client, _, tokens, _ = auth_env
    for path in READ_PATHS:
        assert client.get("/api/v1" + path, headers=headers(tokens, role)).status_code == 200


ADMIN_ACTIONS = [
    ("get", "/users", None),
    ("post", "/users", {"name": "Other", "email": "other@example.com", "password": PASSWORD}),
    ("patch", "/users/absent", {"role": "admin"}),
    ("get", "/accounts/external-id", None),
    (
        "post",
        "/accounts",
        {
            "name": "New",
            "aws_account_id": "222222222222",
            "role_arn": "arn:aws:iam::222222222222:role/Test",
            "external_id": "a" * 20,
        },
    ),
    ("patch", "/accounts/1", {"enabled": False}),
    ("delete", "/accounts/1", None),
    ("post", "/accounts/1/test-connection", None),
    ("put", "/policies/global/ebs_unattached", {"enabled": False}),
    ("delete", "/policies/global/ebs_unattached", None),
    ("put", "/policies/accounts/1/ebs_unattached", {"enabled": False}),
    ("delete", "/policies/accounts/1/ebs_unattached", None),
]
OPERATOR_ACTIONS = [
    ("post", "/scans", {"account_id": 1}),
    ("patch", "/findings/finding/status", {"status": "accepted"}),
    ("patch", "/findings/bulk/status", {"finding_ids": ["finding"], "status": "dismissed"}),
    ("post", "/findings/finding/explain", None),
]


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_non_admin_cannot_administer_or_escalate(auth_env, role):
    client, _, tokens, ids = auth_env
    for method, path, payload in ADMIN_ACTIONS:
        response = client.request(
            method, "/api/v1" + path, json=payload, headers=headers(tokens, role)
        )
        assert response.status_code == 403, (method, path, response.text)
    assert (
        client.patch(
            f"/api/v1/users/{ids[role]}", json={"role": "admin"}, headers=headers(tokens, role)
        ).status_code
        == 403
    )


def test_viewer_cannot_write_or_invoke_ai(auth_env):
    client, engine, tokens, _ = auth_env
    for method, path, payload in OPERATOR_ACTIONS:
        assert (
            client.request(
                method, "/api/v1" + path, json=payload, headers=headers(tokens, "viewer")
            ).status_code
            == 403
        )
    with Session(engine) as db:
        assert db.get(Finding, "finding").status == "open"
        assert len(list(db.scalars(select(Scan)))) == 1


@pytest.mark.parametrize("role", ["admin", "operator"])
def test_operator_can_scan_and_manage_findings(auth_env, role, monkeypatch):
    client, _, tokens, _ = auth_env
    from app.api.routes import findings

    monkeypatch.setattr(findings, "explain_finding", lambda _: "Test explanation")
    assert (
        client.post(
            "/api/v1/scans", json={"account_id": 1}, headers=headers(tokens, role)
        ).status_code
        == 202
    )
    assert (
        client.patch(
            "/api/v1/findings/finding/status",
            json={"status": "open"},
            headers=headers(tokens, role),
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/findings/bulk/status",
            json={"finding_ids": ["finding"], "status": "accepted"},
            headers=headers(tokens, role),
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/findings/finding/explain", headers=headers(tokens, role)).status_code
        == 200
    )


def test_unauthenticated_business_routes_are_blocked(auth_env):
    client, _, _, _ = auth_env
    for path in READ_PATHS:
        assert client.get("/api/v1" + path).status_code == 401
    for method, path, payload in ADMIN_ACTIONS + OPERATOR_ACTIONS:
        assert client.request(method, "/api/v1" + path, json=payload).status_code == 401


def test_admin_creates_normalized_user_and_duplicate_is_rejected(auth_env):
    client, engine, tokens, _ = auth_env
    data = {
        "name": " New User ",
        "email": "NEW@example.com",
        "password": PASSWORD,
        "role": "operator",
    }
    response = client.post("/api/v1/users", json=data, headers=headers(tokens))
    assert response.status_code == 201
    user = response.json()
    assert user["name"] == "New User" and user["email"] == "new@example.com"
    assert not {"password", "password_hash", "token_version"} & user.keys()
    with Session(engine) as db:
        stored = db.get(User, user["id"])
        assert verify_password(PASSWORD, stored.password_hash)
    assert (
        client.post(
            "/api/v1/users", json={**data, "email": "new@example.com"}, headers=headers(tokens)
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "new@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("payload", [{"role": "viewer"}, {"is_active": False}])
def test_last_admin_cannot_be_removed(auth_env, payload):
    client, _, tokens, ids = auth_env
    assert (
        client.patch(
            f"/api/v1/users/{ids['admin']}", json=payload, headers=headers(tokens)
        ).status_code
        == 409
    )
    assert client.get("/api/v1/auth/me", headers=headers(tokens)).status_code == 200


def test_deactivation_reactivation_and_role_change_revoke_old_tokens(auth_env):
    client, _, tokens, ids = auth_env
    path = f"/api/v1/users/{ids['operator']}"
    assert client.patch(path, json={"is_active": False}, headers=headers(tokens)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers(tokens, "operator")).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "operator@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert client.patch(path, json={"is_active": True}, headers=headers(tokens)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers(tokens, "operator")).status_code == 401
    response = client.post(
        "/api/v1/auth/login", json={"email": "operator@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    fresh = {"Cookie": f"{COOKIE}={client.cookies.get(COOKIE)}"}
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200
    assert client.patch(path, json={"role": "viewer"}, headers=headers(tokens)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 401


def test_second_admin_allows_demotion_and_preserves_remaining_admin(auth_env):
    client, _, tokens, ids = auth_env
    assert (
        client.patch(
            f"/api/v1/users/{ids['operator']}", json={"role": "admin"}, headers=headers(tokens)
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/users/{ids['admin']}", json={"role": "viewer"}, headers=headers(tokens)
        ).status_code
        == 200
    )
    assert client.get("/api/v1/users", headers=headers(tokens)).status_code == 401


@pytest.mark.parametrize(
    "kind", ["legacy", "expired", "missing-exp", "forged", "unknown-user", "wrong-version"]
)
def test_invalid_tokens_are_rejected(auth_env, kind):
    client, _, _, ids = auth_env
    now = datetime.now(UTC)
    claims = {
        "sub": ids["admin"],
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "auth_version": 1,
        "ver": 1,
    }
    if kind == "legacy":
        claims = {"sub": "admin@example.com", "iat": now, "exp": claims["exp"]}
    elif kind == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif kind == "missing-exp":
        del claims["exp"]
    elif kind == "unknown-user":
        claims["sub"] = "absent"
    elif kind == "wrong-version":
        claims["auth_version"] = 0
    token = jwt.encode(
        claims,
        "not-the-real-signing-key-123456789" if kind == "forged" else settings.secret_key,
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "owner"},
        {"is_active": None},
        {"name": "   "},
        {"token_version": 1},
        {"password_hash": "arbitrary"},
    ],
)
def test_invalid_user_edits_are_rejected(auth_env, changes):
    client, _, tokens, ids = auth_env
    assert (
        client.patch(
            f"/api/v1/users/{ids['viewer']}", json=changes, headers=headers(tokens)
        ).status_code
        == 422
    )


def test_email_collision_does_not_partially_change_user(auth_env):
    client, _, tokens, ids = auth_env
    response = client.patch(
        f"/api/v1/users/{ids['viewer']}",
        json={"email": "ADMIN@example.com", "role": "admin"},
        headers=headers(tokens),
    )
    assert response.status_code == 409
    assert (
        client.get("/api/v1/auth/me", headers=headers(tokens, "viewer")).json()["role"] == "viewer"
    )


@pytest.mark.parametrize("password", ["secr3t", "x" * 129])
def test_invalid_password_not_returned_in_validation_errors(auth_env, password):
    client, _, tokens, _ = auth_env
    response = client.post(
        "/api/v1/users",
        json={"name": "New", "email": "new@example.com", "password": password},
        headers=headers(tokens),
    )
    assert response.status_code == 422
    assert password not in response.text
    assert "input" not in response.text


def test_admin_can_change_aws_configuration_and_policies(auth_env, monkeypatch):
    client, _, tokens, _ = auth_env
    from app.api.routes import accounts
    from app.services.aws_auth import CallerIdentity

    monkeypatch.setattr(accounts, "assume_account_session", lambda _: None)
    monkeypatch.setattr(
        accounts,
        "get_caller_identity",
        lambda _: CallerIdentity(
            account_id="123456789012", arn="arn:aws:iam::123456789012:role/FinOps", user_id="test"
        ),
    )
    assert client.get("/api/v1/accounts/external-id", headers=headers(tokens)).status_code == 200
    assert (
        client.patch(
            "/api/v1/accounts/1", json={"name": "Renamed"}, headers=headers(tokens)
        ).status_code
        == 200
    )
    response = client.post("/api/v1/accounts/1/test-connection", headers=headers(tokens))
    assert response.status_code == 200 and response.json()["ok"]
    assert (
        client.put(
            "/api/v1/policies/global/ebs_unattached",
            json={"enabled": False},
            headers=headers(tokens),
        ).status_code
        == 200
    )
    assert (
        client.delete("/api/v1/policies/global/ebs_unattached", headers=headers(tokens)).status_code
        == 204
    )
    assert (
        client.put(
            "/api/v1/policies/accounts/1/ebs_unattached",
            json={"enabled": False},
            headers=headers(tokens),
        ).status_code
        == 200
    )
    assert (
        client.delete(
            "/api/v1/policies/accounts/1/ebs_unattached", headers=headers(tokens)
        ).status_code
        == 204
    )
    response = client.post(
        "/api/v1/accounts",
        json={
            "name": "Another",
            "aws_account_id": "222222222222",
            "role_arn": "arn:aws:iam::222222222222:role/Test",
            "external_id": "a" * 20,
        },
        headers=headers(tokens),
    )
    assert response.status_code == 201
    assert (
        client.delete(
            f"/api/v1/accounts/{response.json()['id']}", headers=headers(tokens)
        ).status_code
        == 204
    )
