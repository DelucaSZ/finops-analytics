import ssl
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import tls
from app.models.auth import LoginSession
from app.services.authentication import digest
from app.services.tls_manager import TlsManager, TlsOperationError, TlsValidationError
from app.tests.test_security import PASSWORD, headers
from app.tests.test_security import auth_env as auth_env


def private_key_pem(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def certificate(
    name: str,
    *,
    key=None,
    issuer_certificate: x509.Certificate | None = None,
    issuer_key=None,
    ca: bool = False,
    san: str | None = None,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    server_auth: bool = True,
):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    issuer_certificate = issuer_certificate or None
    issuer = issuer_certificate.subject if issuer_certificate else subject
    signer = issuer_key or key
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(days=1))
        .not_valid_after(not_after or now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if not ca:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san or name)]),
            critical=False,
        )
        if server_auth:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
    cert = builder.sign(signer, hashes.SHA256())
    return cert, key


def pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def private_hierarchy(domain: str = "deepops.example.com"):
    root, root_key = certificate("Test Root CA", ca=True)
    intermediate, intermediate_key = certificate(
        "Test Intermediate CA",
        ca=True,
        issuer_certificate=root,
        issuer_key=root_key,
    )
    leaf, leaf_key = certificate(
        domain,
        issuer_certificate=intermediate,
        issuer_key=intermediate_key,
    )
    return root, root_key, intermediate, intermediate_key, leaf, leaf_key


def local_tls(fingerprint: str = "LOCAL", *, trusted: bool = True) -> dict:
    return {
        "healthy": True,
        "trusted": trusted,
        "trust_error": None if trusted else "private CA",
        "certificate": {
            "fingerprint_sha256": fingerprint,
            "issuer": "CN=Test CA",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_until": "2027-01-01T00:00:00+00:00",
            "san": ["deepops.example.com"],
        },
        "message": "ok",
    }


def no_public_endpoints(_domain: str, *, expected_fingerprint: str | None):
    del expected_fingerprint
    return (
        {"a": [], "aaaa": []},
        {"status": "DNS_NOT_FOUND", "endpoints": [], "message": "none"},
    )


def test_custom_certificate_validates_domain_key_and_never_returns_key():
    manager = TlsManager(storage="/tmp/not-used")
    leaf, leaf_key = certificate("deepops.example.com")
    result = manager.validate(
        "custom",
        "DEEPops.example.com.",
        pem(leaf),
        "",
        private_key_pem(leaf_key),
    )
    assert result["domain"] == "deepops.example.com"
    assert result["certificate"]["fingerprint_sha256"]
    assert result["certificate"]["san"] == ["deepops.example.com"]
    assert private_key_pem(leaf_key) not in str(result)

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(TlsValidationError, match="não corresponde"):
        manager.validate_custom("deepops.example.com", pem(leaf), "", private_key_pem(other_key))
    with pytest.raises(TlsValidationError, match="Subject Alternative Name"):
        manager.validate_custom("other.example.com", pem(leaf), "", private_key_pem(leaf_key))


def test_leaf_requires_exactly_one_certificate_and_server_auth_eku():
    manager = TlsManager(storage="/tmp/not-used")
    leaf, leaf_key = certificate("deepops.example.com")
    with pytest.raises(TlsValidationError, match="exatamente um"):
        manager.validate_custom(
            "deepops.example.com", pem(leaf) + pem(leaf), "", private_key_pem(leaf_key)
        )

    wrong_eku, wrong_key = certificate("deepops.example.com", server_auth=False)
    wrong_eku = (
        x509.CertificateBuilder()
        .subject_name(wrong_eku.subject)
        .issuer_name(wrong_eku.issuer)
        .public_key(wrong_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("deepops.example.com")]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(wrong_key, hashes.SHA256())
    )
    with pytest.raises(TlsValidationError, match="Extended Key Usage"):
        manager.validate_custom(
            "deepops.example.com", pem(wrong_eku), "", private_key_pem(wrong_key)
        )


@pytest.mark.parametrize(
    ("not_before", "not_after", "message"),
    [
        (
            datetime.now(UTC) - timedelta(days=30),
            datetime.now(UTC) - timedelta(days=1),
            "expirou",
        ),
        (
            datetime.now(UTC) + timedelta(days=1),
            datetime.now(UTC) + timedelta(days=30),
            "ainda não é válido",
        ),
    ],
)
def test_leaf_validity_errors_are_specific(not_before, not_after, message):
    manager = TlsManager(storage="/tmp/not-used")
    leaf, leaf_key = certificate("deepops.example.com", not_before=not_before, not_after=not_after)
    with pytest.raises(TlsValidationError, match=message):
        manager.validate_custom("deepops.example.com", pem(leaf), "", private_key_pem(leaf_key))


def test_chain_is_cryptographically_validated_reordered_and_root_is_omitted():
    manager = TlsManager(storage="/tmp/not-used")
    root, _, intermediate, _, leaf, leaf_key = private_hierarchy()
    result = manager._prepare_custom(
        "deepops.example.com",
        pem(leaf),
        pem(root) + pem(intermediate),
        private_key_pem(leaf_key),
    )
    served = x509.load_pem_x509_certificates(result["fullchain_pem"].encode())
    assert [item.subject for item in served] == [leaf.subject, intermediate.subject]
    assert result["chain"]["root_omitted"] is True
    assert result["chain"]["served_chain_length"] == 2
    assert result["trust"]["status"] == "PRIVATE_OR_UNTRUSTED"


def test_two_intermediates_are_sorted_from_leaf_to_root():
    manager = TlsManager(storage="/tmp/not-used")
    root, root_key = certificate("Root", ca=True)
    intermediate_one, intermediate_one_key = certificate(
        "Intermediate 1", ca=True, issuer_certificate=root, issuer_key=root_key
    )
    intermediate_two, intermediate_two_key = certificate(
        "Intermediate 2",
        ca=True,
        issuer_certificate=intermediate_one,
        issuer_key=intermediate_one_key,
    )
    leaf, leaf_key = certificate(
        "deepops.example.com",
        issuer_certificate=intermediate_two,
        issuer_key=intermediate_two_key,
    )
    result = manager._prepare_custom(
        "deepops.example.com",
        pem(leaf),
        pem(intermediate_one) + pem(intermediate_two) + pem(root),
        private_key_pem(leaf_key),
    )
    served = x509.load_pem_x509_certificates(result["fullchain_pem"].encode())
    assert [item.subject for item in served] == [
        leaf.subject,
        intermediate_two.subject,
        intermediate_one.subject,
    ]


def test_missing_intermediate_is_diagnosed_as_unanchored():
    manager = TlsManager(storage="/tmp/not-used")
    _, _, _, _, leaf, leaf_key = private_hierarchy()
    result = manager.validate_custom(
        "deepops.example.com", pem(leaf), "", private_key_pem(leaf_key)
    )
    assert result["chain"]["status"] == "UNANCHORED"
    assert "intermediária ausente" in result["trust"]["message"]


def test_invalid_intermediate_ca_validity_and_signature_are_rejected():
    manager = TlsManager(storage="/tmp/not-used")
    root, root_key, intermediate, intermediate_key, leaf, leaf_key = private_hierarchy()

    non_ca, non_ca_key = certificate(
        "Test Intermediate CA",
        ca=False,
        issuer_certificate=root,
        issuer_key=root_key,
    )
    leaf_non_ca, leaf_non_ca_key = certificate(
        "deepops.example.com",
        issuer_certificate=non_ca,
        issuer_key=non_ca_key,
    )
    with pytest.raises(TlsValidationError, match="CA=true"):
        manager.validate_custom(
            "deepops.example.com",
            pem(leaf_non_ca),
            pem(non_ca),
            private_key_pem(leaf_non_ca_key),
        )

    expired_intermediate, expired_key = certificate(
        "Expired Intermediate",
        ca=True,
        issuer_certificate=root,
        issuer_key=root_key,
        not_before=datetime.now(UTC) - timedelta(days=30),
        not_after=datetime.now(UTC) - timedelta(days=1),
    )
    expired_leaf, expired_leaf_key = certificate(
        "deepops.example.com",
        issuer_certificate=expired_intermediate,
        issuer_key=expired_key,
    )
    with pytest.raises(TlsValidationError, match="expirou"):
        manager.validate_custom(
            "deepops.example.com",
            pem(expired_leaf),
            pem(expired_intermediate),
            private_key_pem(expired_leaf_key),
        )

    imposter, _ = certificate("Test Intermediate CA", ca=True)
    with pytest.raises(TlsValidationError, match="quebrada"):
        manager.validate_custom(
            "deepops.example.com",
            pem(leaf),
            pem(imposter),
            private_key_pem(leaf_key),
        )

    with pytest.raises(TlsValidationError, match="duplicados"):
        manager.validate_custom(
            "deepops.example.com",
            pem(leaf),
            pem(intermediate) + pem(intermediate),
            private_key_pem(leaf_key),
        )
    assert intermediate_key is not None


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


def test_fullchain_files_are_protected_and_caddy_uses_explicit_redirect(tmp_path):
    manager = TlsManager(storage=tmp_path)
    root, _, intermediate, _, leaf, leaf_key = private_hierarchy()
    prepared = manager._prepare_custom(
        "deepops.example.com",
        pem(leaf),
        pem(intermediate) + pem(root),
        private_key_pem(leaf_key),
    )
    directory, certificate_path, key_path = manager._write_custom_files(
        prepared["certificate"], prepared["fullchain_pem"], private_key_pem(leaf_key)
    )
    assert (directory / "fullchain.pem").stat().st_mode & 0o777 == 0o600
    assert (directory / "private-key.pem").stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    stored = x509.load_pem_x509_certificates((directory / "fullchain.pem").read_bytes())
    assert len(stored) == 2
    assert root.subject not in [item.subject for item in stored]

    caddyfile = manager.managed_caddyfile("deepops.example.com", certificate_path, key_path)
    assert "http://deepops.example.com" in caddyfile
    assert "redir https://deepops.example.com{uri} 308" in caddyfile
    assert f"tls {certificate_path} {key_path}" in caddyfile
    assert "http://proxy" in caddyfile


def test_failed_local_probe_restores_previous_runtime_and_discards_private_key(
    tmp_path, monkeypatch
):
    manager = TlsManager(storage=tmp_path, verify_timeout=0)
    previous = manager.baseline_caddyfile()
    loaded = []
    monkeypatch.setattr(manager, "_load", loaded.append)

    def fail(*_args, **_kwargs):
        raise TlsOperationError("probe failed")

    monkeypatch.setattr(manager, "_wait_probe", fail)
    _, _, intermediate, _, leaf, leaf_key = private_hierarchy()

    with pytest.raises(TlsOperationError, match="probe failed"):
        manager.apply(
            "custom",
            "deepops.example.com",
            pem(leaf),
            pem(intermediate),
            private_key_pem(leaf_key),
        )

    assert loaded[0] != previous
    assert loaded[-1] == previous
    assert not manager.config_path.exists()
    assert not manager.state_path.exists()
    assert not manager.certs_path.exists() or not list(manager.certs_path.iterdir())


def test_public_endpoint_unreachable_does_not_rollback_valid_local_tls(tmp_path, monkeypatch):
    manager = TlsManager(storage=tmp_path)
    loaded = []
    monkeypatch.setattr(manager, "_load", loaded.append)
    monkeypatch.setattr(manager, "_wait_probe", lambda *_args, **_kwargs: local_tls("LOCAL"))
    monkeypatch.setattr(
        manager,
        "_public_diagnostics",
        lambda _domain, *, expected_fingerprint: (
            {"a": ["203.0.113.10"], "aaaa": []},
            {
                "status": "UNREACHABLE",
                "endpoints": [],
                "message": f"unreachable {expected_fingerprint}",
            },
        ),
    )

    result = manager.apply("automatic", "deepops.example.com")
    assert result["local_tls"]["healthy"] is True
    assert result["endpoint_validation"]["status"] == "UNREACHABLE"
    assert manager.config_path.exists()
    assert len(loaded) == 1


def test_dns_and_endpoint_statuses_cover_not_found_verified_partial_and_mismatch(monkeypatch):
    manager = TlsManager(storage="/tmp/not-used")
    monkeypatch.setattr(manager, "_resolve_dns", lambda _domain: {"a": [], "aaaa": []})
    _, result = manager._public_diagnostics("deepops.example.com", expected_fingerprint="X")
    assert result["status"] == "DNS_NOT_FOUND"

    monkeypatch.setattr(
        manager,
        "_resolve_dns",
        lambda _domain: {"a": ["192.0.2.1", "192.0.2.2"], "aaaa": ["2001:db8::1"]},
    )
    responses = {
        "192.0.2.1": "VERIFIED",
        "192.0.2.2": "VERIFIED",
        "2001:db8::1": "VERIFIED",
    }

    def endpoint(_domain, address, *, expected_fingerprint, timeout=3):
        del expected_fingerprint, timeout
        return {"address": address, "status": responses[address]}

    monkeypatch.setattr(manager, "_probe_published_endpoint", endpoint)
    dns, result = manager._public_diagnostics("deepops.example.com", expected_fingerprint="X")
    assert dns == {"a": ["192.0.2.1", "192.0.2.2"], "aaaa": ["2001:db8::1"]}
    assert result["status"] == "VERIFIED"

    responses["192.0.2.2"] = "UNREACHABLE"
    _, result = manager._public_diagnostics("deepops.example.com", expected_fingerprint="X")
    assert result["status"] == "PARTIAL"

    responses["192.0.2.2"] = "MISMATCH"
    _, result = manager._public_diagnostics("deepops.example.com", expected_fingerprint="X")
    assert result["status"] == "MISMATCH"


def test_endpoint_probe_compares_fingerprint_hostname_and_trust(monkeypatch):
    manager = TlsManager(storage="/tmp/not-used")
    leaf, _ = certificate("deepops.example.com")
    calls = []

    def connect(_host, _domain, *, timeout, verify):
        calls.append((timeout, verify))
        if verify:
            raise ssl.SSLCertVerificationError(1, "private CA")
        return leaf

    monkeypatch.setattr(manager, "_connect_leaf", connect)
    fingerprint = manager._fingerprint(leaf)
    result = manager._probe_published_endpoint(
        "deepops.example.com", "192.0.2.10", expected_fingerprint=fingerprint
    )
    assert result["status"] == "VERIFIED"
    assert result["trusted"] is False
    assert result["fingerprint_matches"] is True
    assert [verify for _timeout, verify in calls] == [False, True]

    mismatch = manager._probe_published_endpoint(
        "deepops.example.com", "192.0.2.10", expected_fingerprint="OTHER"
    )
    assert mismatch["status"] == "MISMATCH"


def test_https_config_adds_security_headers_and_hsts_only_to_public_tls():
    manager = TlsManager(storage="/tmp/not-used")
    baseline = manager.baseline_caddyfile()
    managed = manager.managed_caddyfile("deepops.example.com")

    assert 'Strict-Transport-Security "max-age=31536000"' not in baseline
    assert managed.count('Strict-Transport-Security "max-age=31536000"') == 1
    assert managed.count('X-Content-Type-Options "nosniff"') == 2
    assert managed.count('X-Frame-Options "DENY"') == 2
    assert "frame-ancestors 'none'" in managed
    assert "-Server" in managed


def test_automatic_mode_persists_after_local_probe_and_status_observes_renewal(
    tmp_path, monkeypatch
):
    manager = TlsManager(storage=tmp_path)
    loaded = []
    monkeypatch.setattr(manager, "_load", loaded.append)
    monkeypatch.setattr(manager, "_wait_probe", lambda *_args, **_kwargs: local_tls("OLD"))
    monkeypatch.setattr(manager, "_public_diagnostics", no_public_endpoints)

    result = manager.apply("automatic", "deepops.example.com")
    assert result["healthy"] is True
    assert manager.config_path.exists() and manager.state_path.exists()
    caddyfile = manager.config_path.read_text()
    assert "deepops.example.com" in caddyfile
    assert "http://proxy" in caddyfile
    assert "auto_https off" not in caddyfile

    monkeypatch.setattr(
        manager,
        "_probe",
        lambda *_args, **_kwargs: local_tls("NEW"),
    )
    status = manager.status()
    assert status["certificate"]["fingerprint_sha256"] == "NEW"
    assert status["mode"] == "automatic"


def test_legacy_state_remains_readable(tmp_path, monkeypatch):
    manager = TlsManager(storage=tmp_path)
    manager._ensure_storage()
    manager.state_path.write_text(
        '{"mode":"custom","domain":"deepops.example.com","applied_at":"legacy"}'
    )
    monkeypatch.setattr(manager, "_probe", lambda *_args, **_kwargs: local_tls("LEGACY"))
    monkeypatch.setattr(manager, "_public_diagnostics", no_public_endpoints)
    status = manager.status()
    assert status["configured"] is True
    assert status["certificate"]["fingerprint_sha256"] == "LEGACY"


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


def test_api_new_contract_legacy_compatibility_and_private_key_redaction(auth_env, caplog):
    client, _, tokens, _ = auth_env
    leaf, leaf_key = certificate("deepops.example.com")
    key = private_key_pem(leaf_key)
    new_response = client.post(
        "/api/v1/tls/validate",
        headers=headers(tokens),
        json={
            "mode": "custom",
            "domain": "deepops.example.com",
            "server_certificate": pem(leaf),
            "intermediate_chain": "",
            "private_key": key,
        },
    )
    assert new_response.status_code == 200
    assert key not in new_response.text
    assert key not in caplog.text

    legacy_response = client.post(
        "/api/v1/tls/validate",
        headers=headers(tokens),
        json={
            "mode": "custom",
            "domain": "deepops.example.com",
            "certificate_chain": pem(leaf),
            "private_key": key,
        },
    )
    assert legacy_response.status_code == 200
    assert key not in legacy_response.text


def test_apply_requires_recent_admin(auth_env, monkeypatch):
    client, engine, tokens, _ = auth_env
    fake = SimpleNamespace(
        apply=lambda mode, domain, server, intermediates, key: {
            "configured": True,
            "mode": mode,
            "domain": domain,
            "healthy": True,
            "local_tls": local_tls(),
            "dns": {"a": [], "aaaa": []},
            "endpoint_validation": {
                "status": "DNS_NOT_FOUND",
                "endpoints": [],
                "message": "none",
            },
            "certificate": None,
            "chain": None,
            "trust": None,
            "applied_at": "2026-09-24T18:00:00+00:00",
            "last_validated_at": "2026-09-24T18:00:00+00:00",
            "message": f"ok {len(server)} {len(intermediates)} {len(key)}",
        },
        split_legacy_chain=TlsManager.split_legacy_chain,
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
