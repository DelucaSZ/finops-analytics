from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import tls
from app.models.auth import LoginSession
from app.services.authentication import digest
from app.services.tls_manager import TlsManager, TlsOperationError, TlsValidationError
from app.tests.test_security import PASSWORD, headers
from app.tests.test_security import auth_env as auth_env


def certificate_material(domain: str, *, key=None, san: str | None = None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san or domain)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    chain = certificate.public_bytes(serialization.Encoding.PEM).decode()
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return chain, private_key


def test_custom_certificate_validates_domain_key_and_never_returns_key():
    manager = TlsManager(storage="/tmp/not-used")
    chain, private_key = certificate_material("deepops.example.com")
    result = manager.validate("custom", "DEEPops.example.com.", chain, private_key)
    assert result["domain"] == "deepops.example.com"
    assert result["certificate"]["fingerprint_sha256"]
    assert private_key not in str(result)

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _, wrong_key = certificate_material("deepops.example.com", key=other_key)
    with pytest.raises(TlsValidationError, match="não corresponde"):
        manager.validate_custom("deepops.example.com", chain, wrong_key)
    with pytest.raises(TlsValidationError, match="SAN"):
        manager.validate_custom("other.example.com", chain, private_key)


@pytest.mark.parametrize(
    "domain",
    [
        "https://example.com",
        "example.com:443",
        "*.example.com",
        "127.0.0.1",
        "localhost",
        "bad_domain.example.com",
    ],
)
def test_domain_validation_rejects_non_dns_origins(domain):
    with pytest.raises(TlsValidationError):
        TlsManager.normalize_domain(domain)


def test_failed_handshake_restores_previous_runtime_and_discards_private_key(tmp_path, monkeypatch):
    manager = TlsManager(storage=tmp_path, verify_timeout=0)
    previous = manager.baseline_caddyfile()
    loaded = []
    monkeypatch.setattr(manager, "_load", loaded.append)

    def fail(_domain):
        raise TlsOperationError("probe failed")

    monkeypatch.setattr(manager, "_wait_probe", fail)
    chain, private_key = certificate_material("deepops.example.com")

    with pytest.raises(TlsOperationError, match="probe failed"):
        manager.apply("custom", "deepops.example.com", chain, private_key)

    assert loaded[0] != previous
    assert loaded[-1] == previous
    assert not manager.config_path.exists()
    assert not manager.state_path.exists()
    assert not manager.certs_path.exists() or not list(manager.certs_path.iterdir())


def test_success_persists_only_after_tls_probe_and_status_observes_renewal(tmp_path, monkeypatch):
    manager = TlsManager(storage=tmp_path)
    loaded = []
    old_certificate = {
        "fingerprint_sha256": "OLD",
        "issuer": "CN=Test CA",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "2026-10-01T00:00:00+00:00",
    }
    new_certificate = {**old_certificate, "fingerprint_sha256": "NEW"}
    monkeypatch.setattr(manager, "_load", loaded.append)
    monkeypatch.setattr(manager, "_wait_probe", lambda _domain: old_certificate)

    result = manager.apply("automatic", "deepops.example.com")
    assert result["healthy"] is True
    assert manager.config_path.exists() and manager.state_path.exists()
    caddyfile = manager.config_path.read_text()
    assert "deepops.example.com" in caddyfile
    assert "http://proxy" in caddyfile
    assert "auto_https off" not in caddyfile

    monkeypatch.setattr(manager, "_probe", lambda _domain, timeout=4: new_certificate)
    status = manager.status()
    assert status["certificate"]["fingerprint_sha256"] == "NEW"
    assert status["mode"] == "automatic"


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_tls_settings_are_admin_only(auth_env, role):
    client, _, tokens, _ = auth_env
    assert client.get("/api/v1/tls", headers=headers(tokens, role)).status_code == 403
    assert (
        client.post(
            "/api/v1/tls/validate",
            headers=headers(tokens, role),
            json={"mode": "automatic", "domain": "deepops.example.com"},
        ).status_code
        == 403
    )


def test_apply_requires_recent_admin_and_validation_does_not_echo_private_key(
    auth_env, monkeypatch
):
    client, engine, tokens, _ = auth_env
    chain, private_key = certificate_material("deepops.example.com")
    response = client.post(
        "/api/v1/tls/validate",
        headers=headers(tokens),
        json={
            "mode": "custom",
            "domain": "deepops.example.com",
            "certificate_chain": chain,
            "private_key": private_key,
        },
    )
    assert response.status_code == 200
    assert private_key not in response.text

    fake = SimpleNamespace(
        apply=lambda mode, domain, chain, key: {
            "configured": True,
            "mode": mode,
            "domain": domain,
            "healthy": True,
            "certificate": None,
            "applied_at": "2026-09-24T18:00:00+00:00",
            "message": "ok",
        }
    )
    monkeypatch.setattr(tls, "manager", fake)
    payload = {"mode": "automatic", "domain": "deepops.example.com"}
    with Session(engine) as db:
        session = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(tokens["admin"]))
        )
        session.reauthenticated_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
    assert (
        client.post("/api/v1/tls/apply", headers=headers(tokens), json=payload).status_code == 403
    )
    assert (
        client.post(
            "/api/v1/auth/reauthenticate",
            headers=headers(tokens),
            json={"password": PASSWORD, "code": ""},
        ).status_code
        == 204
    )
    response = client.post("/api/v1/tls/apply", headers=headers(tokens), json=payload)
    assert response.status_code == 200
    assert response.json()["healthy"] is True
