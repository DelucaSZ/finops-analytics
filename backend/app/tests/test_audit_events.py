from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes import audit
from app.core.security import require_admin
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.mfa import SecurityEvent
from app.models.user import User, UserRole
from app.services.audit import (
    AuditService,
    audit_snapshot,
    build_audit_changes,
    new_correlation_id,
    sanitize_audit_payload,
)


@pytest.fixture
def audit_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'audit.db'}",
        connect_args={"check_same_thread": False},
    )
    User.__table__.create(engine)
    SecurityEvent.__table__.create(engine)
    AuditEvent.__table__.create(engine)

    with Session(engine) as db:
        actor = User(
            name="Admin Original",
            email="admin@example.com",
            role=UserRole.ADMIN,
            password_hash="not-used",
        )
        subject = User(
            name="Operator Maria",
            email="operator.maria@example.com",
            role=UserRole.OPERATOR,
            password_hash="not-used",
        )
        db.add_all([actor, subject])
        db.commit()
        actor_id = actor.id
        subject_id = subject.id

    yield engine, actor_id, subject_id
    engine.dispose()


def test_sanitizer_is_recursive_json_safe_and_never_persists_secrets():
    now = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)
    payload = {
        "name": "safe",
        "password": "plain-text",
        "nested": {
            "private_key": "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
            "secret_access_key": "aws-secret",
            "value": Decimal("12.3400"),
            "when": now,
        },
        "innocent_secret_type": SecretStr("do-not-store"),
        "role": UserRole.ADMIN,
        "certificate": "-----BEGIN CERTIFICATE-----\n" + ("A" * 4000),
    }

    safe = sanitize_audit_payload(payload)
    serialized = str(safe)

    assert safe["name"] == "safe"
    assert "password" not in safe
    assert "private_key" not in safe["nested"]
    assert "secret_access_key" not in safe["nested"]
    assert "innocent_secret_type" not in safe
    assert safe["nested"]["value"] == "12.3400"
    assert safe["nested"]["when"] == now.isoformat()
    assert safe["role"] == "admin"
    assert safe["certificate"]["_omitted"] == "certificate_pem"
    assert "plain-text" not in serialized
    assert "aws-secret" not in serialized
    assert "do-not-store" not in serialized
    assert "BEGIN PRIVATE KEY" not in serialized


def test_sanitizer_blocks_aws_oci_tls_auth_smtp_and_application_secrets():
    safe = sanitize_audit_payload(
        {
            "aws_access_key": "AKIAEXAMPLE",
            "aws_secret_key": "secret",
            "session_token": "token",
            "oci_private_key": "private",
            "passphrase": "pass",
            "fingerprint": "AA:BB:CC",
            "tenancy_ocid": "ocid1.tenancy.oc1..safe",
            "tls_private_key": "key",
            "server_certificate": "-----BEGIN CERTIFICATE-----\nCERT",
            "password": "password",
            "password_hash": "hash",
            "reset_token": "reset",
            "invitation_token": "invite",
            "mfa_secret": "mfa",
            "recovery_code": "recovery",
            "smtp_password": "smtp",
            "NUVEMIQ_SECRET_KEY": "application-secret",
        }
    )
    serialized = str(safe)
    for forbidden in (
        "AKIAEXAMPLE",
        "secret",
        "token",
        "private",
        "pass",
        "password",
        "hash",
        "reset",
        "invite",
        "mfa",
        "recovery",
        "smtp",
        "application-secret",
    ):
        assert forbidden not in serialized
    assert safe["fingerprint"] == "AA:BB:CC"
    assert safe["tenancy_ocid"] == "ocid1.tenancy.oc1..safe"


def test_diff_is_first_level_deterministic_and_omits_unchanged_fields():
    before = audit_snapshot(
        {
            "enabled": True,
            "scan_interval_hours": 24,
            "name": "Produção",
            "nullable": None,
        }
    )
    after = audit_snapshot(
        {
            "enabled": False,
            "scan_interval_hours": 12,
            "name": "Produção",
            "nullable": None,
        }
    )
    changes = build_audit_changes(before, after)
    assert list(changes) == ["enabled", "scan_interval_hours"]
    assert changes == {
        "enabled": {"from": True, "to": False},
        "scan_interval_hours": {"from": 24, "to": 12},
    }


def test_large_payloads_are_summarized_or_capped():
    safe = sanitize_audit_payload(
        {
            "policy_document": "x" * 10_000,
            "evidence": ["e" * 100 for _ in range(1000)],
        }
    )
    assert safe["_truncated"] is True
    assert safe["_original_bytes"] > 16_384
    assert len(str(safe)) < 500


def test_record_uses_actor_snapshot_and_same_caller_transaction(audit_db):
    engine, actor_id, subject_id = audit_db
    with Session(engine) as db:
        actor = db.get(User, actor_id)
        item = AuditService.record(
            db,
            actor=actor,
            module="users",
            action="user.update",
            entity_type="user",
            entity_id=subject_id,
            entity_label="Operator Maria · operator.maria@example.com",
            before={"role": "viewer"},
            after={"role": "operator"},
            source="API",
        )
        db.flush()
        event_id = item.id
        assert item.actor_name_snapshot == "Admin Original"
        assert item.actor_email_snapshot == "admin@example.com"
        assert item.changes == {"role": {"from": "viewer", "to": "operator"}}
        db.rollback()
    with Session(engine) as db:
        assert db.get(AuditEvent, event_id) is None


def test_commit_persists_snapshot_independent_of_current_user(audit_db):
    engine, actor_id, subject_id = audit_db
    with Session(engine) as db:
        actor = db.get(User, actor_id)
        item = AuditService.record(
            db,
            actor=actor,
            module="users",
            action="user.update",
            entity_type="user",
            entity_id=subject_id,
            entity_label="Operator Maria",
            before={"name": "Operator Maria"},
            after={"name": "Operator Maria Nova"},
            source="API",
        )
        db.commit()
        event_id = item.id
        actor.name = "Admin Renomeado"
        actor.email = "renamed@example.com"
        actor.is_active = False
        db.commit()
    with Session(engine) as db:
        item = db.get(AuditEvent, event_id)
        assert item.actor_name_snapshot == "Admin Original"
        assert item.actor_email_snapshot == "admin@example.com"
        assert item.actor_id == actor_id


def test_system_event_and_correlation_id(audit_db):
    engine, _, _ = audit_db
    correlation_id = new_correlation_id()
    UUID(correlation_id)
    with Session(engine) as db:
        item = AuditService.record(
            db,
            actor=None,
            module="system",
            action="retention.preview",
            entity_type="retention_policy",
            source="SYSTEM",
            correlation_id=correlation_id,
            metadata={"count": 10},
        )
        db.commit()
        assert item.actor_id is None
        assert item.actor_name_snapshot == "SYSTEM"
        assert item.source == "SYSTEM"
        assert item.correlation_id == correlation_id


def _app_for(engine, *, authorized: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(audit.router, prefix="/api/v1")

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    if authorized:
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
            id="test-admin", role=UserRole.ADMIN
        )
    return app


def _seed_unified_events(engine, actor_id: str, subject_id: str) -> tuple[str, str, str]:
    now = datetime.now(UTC)
    correlation_id = new_correlation_id()
    with Session(engine) as db:
        actor = db.get(User, actor_id)
        security = SecurityEvent(
            actor_id=actor_id,
            user_id=subject_id,
            action="auth.login",
            reason="",
            created_at=now - timedelta(minutes=1),
        )
        db.add(security)
        administrative = AuditService.record(
            db,
            actor=actor,
            module="users",
            action="user.update",
            entity_type="user",
            entity_id=subject_id,
            entity_label="Operator Maria · operator.maria@example.com",
            before={"is_active": True},
            after={"is_active": False},
            source="API",
            correlation_id=correlation_id,
        )
        administrative.created_at = now
        db.commit()
        return security.id, administrative.id, correlation_id


def test_unified_endpoint_global_order_total_and_pagination(audit_db):
    engine, actor_id, subject_id = audit_db
    security_id, administrative_id, _ = _seed_unified_events(engine, actor_id, subject_id)
    with TestClient(_app_for(engine, authorized=True)) as client:
        page = client.get(
            "/api/v1/audit",
            params={"event_kind": "all", "limit": 1, "offset": 0},
        ).json()
        assert page["total"] == 2
        assert page["items"][0]["id"] == administrative_id
        assert page["items"][0]["event_kind"] == "administrative"
        second = client.get(
            "/api/v1/audit",
            params={"event_kind": "all", "limit": 1, "offset": 1},
        ).json()
        assert second["total"] == 2
        assert second["items"][0]["id"] == security_id
        assert second["items"][0]["event_kind"] == "security"


def test_actor_filters_support_id_name_email_partial_case_and_historical_snapshot(audit_db):
    engine, actor_id, subject_id = audit_db
    _seed_unified_events(engine, actor_id, subject_id)
    with Session(engine) as db:
        actor = db.get(User, actor_id)
        actor.name = "Admin Atual"
        actor.email = "current@example.com"
        db.commit()

    with TestClient(_app_for(engine, authorized=True)) as client:
        by_id = client.get("/api/v1/audit", params={"actor_id": actor_id}).json()
        assert by_id["total"] == 2

        historical_name = client.get(
            "/api/v1/audit",
            params={"event_kind": "administrative", "actor_search": "admin orig"},
        ).json()
        assert historical_name["total"] == 1

        historical_email = client.get(
            "/api/v1/audit",
            params={
                "event_kind": "administrative",
                "actor_search": "ADMIN@EXAMPLE.COM",
            },
        ).json()
        assert historical_email["total"] == 1

        current_name = client.get(
            "/api/v1/audit",
            params={"event_kind": "administrative", "actor_search": "admin atual"},
        ).json()
        assert current_name["total"] == 1


def test_subject_filters_are_separate_from_actor_and_search_name_email(audit_db):
    engine, actor_id, subject_id = audit_db
    _seed_unified_events(engine, actor_id, subject_id)
    with TestClient(_app_for(engine, authorized=True)) as client:
        by_id = client.get("/api/v1/audit", params={"subject_user_id": subject_id}).json()
        assert by_id["total"] == 2
        by_name = client.get(
            "/api/v1/audit",
            params={"subject_user_search": "maria"},
        ).json()
        assert by_name["total"] == 2
        by_email = client.get(
            "/api/v1/audit",
            params={"subject_user_search": "OPERATOR.MARIA@EXAMPLE.COM"},
        ).json()
        assert by_email["total"] == 2
        actor_is_not_subject = client.get(
            "/api/v1/audit",
            params={"subject_user_id": actor_id},
        ).json()
        assert actor_is_not_subject["total"] == 0


def test_module_action_source_event_kind_period_correlation_and_combinations(audit_db):
    engine, actor_id, subject_id = audit_db
    _, _, correlation_id = _seed_unified_events(engine, actor_id, subject_id)
    now = datetime.now(UTC)
    with TestClient(_app_for(engine, authorized=True)) as client:
        by_module = client.get("/api/v1/audit", params={"module": "users"}).json()
        assert by_module["total"] == 1
        by_action = client.get("/api/v1/audit", params={"action": "user.update"}).json()
        assert by_action["total"] == 1
        by_source = client.get("/api/v1/audit", params={"source": "API"}).json()
        assert by_source["total"] == 2
        system_only = client.get("/api/v1/audit", params={"source": "SYSTEM"}).json()
        assert system_only["total"] == 0
        security = client.get("/api/v1/audit", params={"event_kind": "security"}).json()
        assert security["total"] == 1
        administrative = client.get("/api/v1/audit", params={"event_kind": "administrative"}).json()
        assert administrative["total"] == 1
        by_correlation = client.get(
            "/api/v1/audit", params={"correlation_id": correlation_id}
        ).json()
        assert by_correlation["total"] == 1
        period = client.get(
            "/api/v1/audit",
            params={
                "from": (now - timedelta(hours=1)).isoformat(),
                "to": (now + timedelta(hours=1)).isoformat(),
                "event_kind": "administrative",
                "module": "users",
                "actor_id": actor_id,
                "subject_user_id": subject_id,
            },
        ).json()
        assert period["total"] == 1


def test_period_requires_timezone_and_valid_order(audit_db):
    engine, _, _ = audit_db
    with TestClient(_app_for(engine, authorized=True)) as client:
        naive = client.get("/api/v1/audit", params={"from": "2026-10-20T10:00:00"})
        assert naive.status_code == 422
        reversed_range = client.get(
            "/api/v1/audit",
            params={
                "from": "2026-10-20T12:00:00+00:00",
                "to": "2026-10-20T10:00:00+00:00",
            },
        )
        assert reversed_range.status_code == 422


def test_user_autocomplete_is_partial_case_insensitive_deterministic_and_safe(audit_db):
    engine, _, _ = audit_db
    with TestClient(_app_for(engine, authorized=True)) as client:
        response = client.get("/api/v1/audit/users", params={"q": "MAR", "limit": 20})
        assert response.status_code == 200
        users = response.json()
        assert users == [
            {
                "id": users[0]["id"],
                "name": "Operator Maria",
                "email": "operator.maria@example.com",
            }
        ]
        assert set(users[0]) == {"id", "name", "email"}


def test_audit_options_expose_human_modules_and_canonical_actions(audit_db):
    engine, _, _ = audit_db
    with TestClient(_app_for(engine, authorized=True)) as client:
        response = client.get("/api/v1/audit/options")
        assert response.status_code == 200
        payload = response.json()
        assert {item["value"] for item in payload["modules"]} >= {
            "users",
            "accounts",
            "policies",
        }
        action = next(item for item in payload["actions"] if item["value"] == "account.disable")
        assert action["label"] == "Conta cloud desabilitada"
        assert action["module"] == "accounts"


def test_event_kind_legacy_alias_and_conflict_are_predictable(audit_db):
    engine, actor_id, subject_id = audit_db
    _seed_unified_events(engine, actor_id, subject_id)
    with TestClient(_app_for(engine, authorized=True)) as client:
        legacy = client.get("/api/v1/audit", params={"event_type": "administrative"})
        assert legacy.status_code == 200
        assert legacy.json()["total"] == 1
        conflict = client.get(
            "/api/v1/audit",
            params={"event_kind": "security", "event_type": "administrative"},
        )
        assert conflict.status_code == 422


def test_security_event_still_works_and_audit_endpoints_are_admin_only(audit_db):
    engine, actor_id, subject_id = audit_db
    _seed_unified_events(engine, actor_id, subject_id)
    with Session(engine) as db:
        assert len(list(db.scalars(select(SecurityEvent)))) == 1
        assert len(list(db.scalars(select(AuditEvent)))) == 1
    with TestClient(_app_for(engine, authorized=False)) as client:
        assert client.get("/api/v1/audit").status_code == 401
        assert client.get("/api/v1/audit/users", params={"q": "admin"}).status_code == 401
        assert client.get("/api/v1/audit/options").status_code == 401