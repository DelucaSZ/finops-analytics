"""Safe HTTPS configuration through Caddy's internal admin API."""

from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization


class TlsValidationError(ValueError):
    """User-supplied TLS material is invalid."""


class TlsOperationError(RuntimeError):
    """The local proxy could not safely apply or verify TLS."""


class TlsManager:
    def __init__(
        self,
        storage: Path | str = "/var/lib/deepops/caddy/deepops",
        admin_url: str = "http://proxy:2019",
        probe_host: str = "proxy",
        verify_timeout: float = 45,
    ):
        self.storage = Path(storage)
        self.admin_url = admin_url.rstrip("/")
        self.probe_host = probe_host
        self.verify_timeout = verify_timeout
        self.config_path = self.storage / "Caddyfile"
        self.state_path = self.storage / "state.json"
        self.lock_path = self.storage / ".lock"
        self.certs_path = self.storage / "certs"

    @staticmethod
    def normalize_domain(value: str) -> str:
        raw = value.strip().rstrip(".").lower()
        if not raw or any(token in raw for token in ("://", "/", "\\", ":", "*", " ")):
            raise TlsValidationError(
                "Informe somente um domínio DNS, sem protocolo, porta ou caminho."
            )
        try:
            domain = raw.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise TlsValidationError("Domínio inválido.") from exc
        if len(domain) > 253 or len(domain.split(".")) < 2:
            raise TlsValidationError("Informe um domínio DNS completo.")
        try:
            ipaddress.ip_address(domain)
        except ValueError:
            pass
        else:
            raise TlsValidationError("Informe um domínio DNS, não um endereço IP.")
        pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        if any(not pattern.fullmatch(label) for label in domain.split(".")):
            raise TlsValidationError("Domínio DNS inválido.")
        return domain

    @staticmethod
    def _dns_matches(pattern: str, domain: str) -> bool:
        pattern = pattern.lower().rstrip(".")
        if pattern == domain:
            return True
        if not pattern.startswith("*."):
            return False
        suffix = pattern[2:]
        return (
            domain.endswith("." + suffix) and len(domain.split(".")) == len(suffix.split(".")) + 1
        )

    @staticmethod
    def _certificate_metadata(certificate: x509.Certificate) -> dict[str, str]:
        return {
            "fingerprint_sha256": certificate.fingerprint(hashes.SHA256()).hex().upper(),
            "issuer": certificate.issuer.rfc4514_string(),
            "valid_from": certificate.not_valid_before_utc.isoformat(),
            "valid_until": certificate.not_valid_after_utc.isoformat(),
        }

    def validate_custom(self, domain: str, chain_pem: str, private_key_pem: str) -> dict[str, str]:
        domain = self.normalize_domain(domain)
        if not chain_pem.strip() or len(chain_pem.encode()) > 131_072:
            raise TlsValidationError("Informe o certificado e a cadeia PEM (máximo 128 KiB).")
        if not private_key_pem.strip() or len(private_key_pem.encode()) > 65_536:
            raise TlsValidationError("Informe a chave privada PEM (máximo 64 KiB).")
        try:
            certificates = x509.load_pem_x509_certificates(chain_pem.encode())
        except ValueError as exc:
            raise TlsValidationError("Certificado ou cadeia PEM inválidos.") from exc
        if not certificates:
            raise TlsValidationError("Nenhum certificado PEM foi encontrado.")
        leaf = certificates[0]
        now = datetime.now(UTC)
        if leaf.not_valid_before_utc > now:
            raise TlsValidationError("O certificado ainda não é válido.")
        if leaf.not_valid_after_utc <= now:
            raise TlsValidationError("O certificado está expirado.")
        try:
            sans = leaf.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            sans = []
        if not any(self._dns_matches(name, domain) for name in sans):
            raise TlsValidationError("O certificado não contém o domínio informado no SAN.")
        try:
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )
        except (TypeError, ValueError) as exc:
            raise TlsValidationError("Chave privada PEM inválida ou protegida por senha.") from exc
        cert_public = leaf.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_public = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if not secrets.compare_digest(cert_public, key_public):
            raise TlsValidationError("A chave privada não corresponde ao certificado.")
        return self._certificate_metadata(leaf)

    @staticmethod
    def _routes() -> str:
        return """\tencode zstd gzip

\thandle /api/* {
\t\treverse_proxy api:8000
\t}

\thandle /health {
\t\treverse_proxy api:8000
\t}

\thandle {
\t\treverse_proxy web:3000
\t}"""

    def baseline_caddyfile(self) -> str:
        return f"""{{\n\tauto_https off
\tpersist_config off
\tadmin 0.0.0.0:2019 {{
\t\torigins http://api:8000
\t\tenforce_origin
\t}}
}}

:80 {{
{self._routes()}
}}
"""

    def managed_caddyfile(
        self,
        domain: str,
        certificate_path: str | None = None,
        key_path: str | None = None,
    ) -> str:
        tls_line = f"\n\ttls {certificate_path} {key_path}" if certificate_path and key_path else ""
        return f"""{{\n\tpersist_config off
\tadmin 0.0.0.0:2019 {{
\t\torigins http://api:8000
\t\tenforce_origin
\t}}
}}

http://proxy {{
{self._routes()}
}}

{domain} {{{tls_line}
{self._routes()}
}}
"""

    def validate(
        self,
        mode: str,
        domain: str,
        chain_pem: str = "",
        private_key_pem: str = "",
    ) -> dict:
        domain = self.normalize_domain(domain)
        if mode == "automatic":
            self.managed_caddyfile(domain)
            return {"valid": True, "mode": mode, "domain": domain, "certificate": None}
        if mode != "custom":
            raise TlsValidationError("Modo HTTPS inválido.")
        certificate = self.validate_custom(domain, chain_pem, private_key_pem)
        return {"valid": True, "mode": mode, "domain": domain, "certificate": certificate}

    def _ensure_storage(self) -> None:
        try:
            self.storage.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.storage, 0o700)
        except OSError as exc:
            raise TlsOperationError("Armazenamento seguro de certificados indisponível.") from exc

    @contextmanager
    def _locked(self):
        self._ensure_storage()
        with self.lock_path.open("a") as lock:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _atomic_write(self, path: Path, data: bytes, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            temporary.replace(path)
            self._fsync_directory(path.parent)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _load(self, caddyfile: str) -> None:
        request = Request(
            self.admin_url + "/load",
            data=caddyfile.encode(),
            method="POST",
            headers={
                "Content-Type": "text/caddyfile",
                "Origin": "http://api:8000",
                "Cache-Control": "must-revalidate",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status < 200 or response.status >= 300:
                    raise TlsOperationError("O Caddy recusou a configuração HTTPS.")
        except HTTPError as exc:
            raise TlsOperationError("O Caddy recusou a configuração HTTPS.") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise TlsOperationError("A API interna do Caddy está indisponível.") from exc

    def _probe(self, domain: str, timeout: float = 5) -> dict[str, str]:
        context = ssl.create_default_context()
        try:
            with (
                socket.create_connection((self.probe_host, 443), timeout=timeout) as plain,
                context.wrap_socket(plain, server_hostname=domain) as secure,
            ):
                der = secure.getpeercert(binary_form=True)
        except (OSError, ssl.SSLError, TimeoutError) as exc:
            raise TlsOperationError(
                "O proxy ainda não apresentou um certificado confiável para o domínio."
            ) from exc
        if not der:
            raise TlsOperationError("O proxy não apresentou certificado.")
        return self._certificate_metadata(x509.load_der_x509_certificate(der))

    def _wait_probe(self, domain: str) -> dict[str, str]:
        deadline = time.monotonic() + self.verify_timeout
        last_error: TlsOperationError | None = None
        while time.monotonic() < deadline:
            try:
                return self._probe(domain)
            except TlsOperationError as exc:
                last_error = exc
                time.sleep(2)
        raise last_error or TlsOperationError("Não foi possível validar o HTTPS.")

    def _read_state(self) -> dict | None:
        if not self.state_path.exists():
            return None
        try:
            value = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if value.get("mode") not in {"automatic", "custom"} or not value.get("domain"):
            return None
        return value

    def status(self) -> dict:
        state = self._read_state()
        if not state:
            return {
                "configured": False,
                "mode": "http",
                "domain": None,
                "healthy": False,
                "certificate": None,
                "applied_at": None,
                "message": "HTTPS ainda não foi configurado pelo DeepOps.",
            }
        domain = state["domain"]
        try:
            certificate = self._probe(domain, timeout=4)
            healthy = True
            message = "HTTPS válido e certificado apresentado pelo proxy."
        except TlsOperationError:
            certificate = None
            healthy = False
            message = "Configuração salva, mas o certificado não pôde ser validado agora."
        return {
            "configured": True,
            "mode": state["mode"],
            "domain": domain,
            "healthy": healthy,
            "certificate": certificate,
            "applied_at": state.get("applied_at"),
            "message": message,
        }

    def _write_custom_files(
        self, metadata: dict[str, str], chain_pem: str, private_key_pem: str
    ) -> tuple[Path, str, str]:
        reference = metadata["fingerprint_sha256"].lower()[:16] + "-" + secrets.token_hex(6)
        directory = self.certs_path / reference
        directory.mkdir(parents=True, mode=0o700)
        os.chmod(directory, 0o700)
        self._atomic_write(directory / "certificate.pem", chain_pem.encode())
        self._atomic_write(directory / "private-key.pem", private_key_pem.encode())
        return (
            directory,
            f"/config/deepops/certs/{reference}/certificate.pem",
            f"/config/deepops/certs/{reference}/private-key.pem",
        )

    def _restore_persisted(self, previous: bytes | None) -> None:
        if previous is None:
            self.config_path.unlink(missing_ok=True)
            self._fsync_directory(self.storage)
        else:
            self._atomic_write(self.config_path, previous)

    def _cleanup_certificates(self, keep: Path | None) -> None:
        try:
            if not self.certs_path.exists():
                return
            for item in self.certs_path.iterdir():
                if keep is not None and item == keep:
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink(missing_ok=True)
        except OSError:
            # Cleanup is hygiene after a committed configuration, not part of availability.
            return

    def apply(
        self,
        mode: str,
        domain: str,
        chain_pem: str = "",
        private_key_pem: str = "",
    ) -> dict:
        domain = self.normalize_domain(domain)
        custom_directory: Path | None = None
        certificate_path = key_path = None
        if mode == "custom":
            metadata = self.validate_custom(domain, chain_pem, private_key_pem)
        elif mode == "automatic":
            metadata = None
        else:
            raise TlsValidationError("Modo HTTPS inválido.")

        with self._locked():
            previous_file = self.config_path.read_bytes() if self.config_path.exists() else None
            previous_runtime = (
                previous_file.decode() if previous_file is not None else self.baseline_caddyfile()
            )
            if metadata:
                try:
                    custom_directory, certificate_path, key_path = self._write_custom_files(
                        metadata, chain_pem, private_key_pem
                    )
                except OSError as exc:
                    raise TlsOperationError(
                        "Não foi possível armazenar o certificado com segurança."
                    ) from exc
            candidate = self.managed_caddyfile(domain, certificate_path, key_path)
            try:
                self._load(candidate)
            except TlsOperationError:
                if custom_directory:
                    shutil.rmtree(custom_directory, ignore_errors=True)
                raise

            try:
                certificate = self._wait_probe(domain)
            except TlsOperationError as exc:
                try:
                    self._load(previous_runtime)
                except TlsOperationError as rollback_error:
                    raise TlsOperationError(
                        "A verificação HTTPS falhou e a restauração automática também falhou."
                    ) from rollback_error
                if custom_directory:
                    shutil.rmtree(custom_directory, ignore_errors=True)
                raise exc

            state = {
                "mode": mode,
                "domain": domain,
                "applied_at": datetime.now(UTC).isoformat(),
            }
            try:
                self._atomic_write(self.config_path, candidate.encode())
                self._atomic_write(
                    self.state_path,
                    (json.dumps(state, indent=2, sort_keys=True) + "\n").encode(),
                )
            except (OSError, TlsOperationError) as exc:
                self._restore_persisted(previous_file)
                try:
                    self._load(previous_runtime)
                except TlsOperationError as rollback_error:
                    raise TlsOperationError(
                        "A persistência falhou e a restauração automática também falhou."
                    ) from rollback_error
                if custom_directory:
                    shutil.rmtree(custom_directory, ignore_errors=True)
                raise TlsOperationError(
                    "Não foi possível persistir a configuração; a anterior foi restaurada."
                ) from exc

            self._cleanup_certificates(custom_directory)
            return {
                "configured": True,
                "mode": mode,
                "domain": domain,
                "healthy": True,
                "certificate": certificate,
                "applied_at": state["applied_at"],
                "message": "HTTPS aplicado e validado com sucesso.",
            }


manager = TlsManager()
