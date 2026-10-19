"""Safe HTTPS configuration and diagnostics through Caddy's internal admin API."""

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
from cryptography.x509.oid import ExtendedKeyUsageOID, ObjectIdentifier


class TlsValidationError(ValueError):
    """User-supplied TLS material is invalid."""


class TlsOperationError(RuntimeError):
    """The local proxy could not safely apply or verify TLS."""


class TlsManager:
    SERVER_CERTIFICATE_MAX = 65_536
    INTERMEDIATE_CHAIN_MAX = 131_072
    PRIVATE_KEY_MAX = 65_536
    ANY_EXTENDED_KEY_USAGE = ObjectIdentifier("2.5.29.37.0")

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
        self._system_roots_cache: tuple[x509.Certificate, ...] | None = None

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
        domain = domain.lower().rstrip(".")
        if pattern == domain:
            return True
        if not pattern.startswith("*."):
            return False
        suffix = pattern[2:]
        return (
            domain.endswith("." + suffix) and len(domain.split(".")) == len(suffix.split(".")) + 1
        )

    @staticmethod
    def _fingerprint(certificate: x509.Certificate) -> str:
        return certificate.fingerprint(hashes.SHA256()).hex().upper()

    @staticmethod
    def _sans(certificate: x509.Certificate) -> list[str]:
        try:
            values = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            return []
        return list(values)

    def _certificate_metadata(
        self, certificate: x509.Certificate, *, chain_length: int | None = None
    ) -> dict:
        metadata = {
            "fingerprint_sha256": self._fingerprint(certificate),
            "issuer": certificate.issuer.rfc4514_string(),
            "valid_from": certificate.not_valid_before_utc.isoformat(),
            "valid_until": certificate.not_valid_after_utc.isoformat(),
            "san": self._sans(certificate),
        }
        if chain_length is not None:
            metadata["chain_length"] = chain_length
        return metadata

    @staticmethod
    def _load_certificates(value: str, *, label: str, allow_empty: bool) -> list[x509.Certificate]:
        if not value.strip():
            if allow_empty:
                return []
            raise TlsValidationError(f"{label} não foi informado.")
        try:
            certificates = x509.load_pem_x509_certificates(value.encode())
        except ValueError as exc:
            raise TlsValidationError(f"{label} inválido.") from exc
        if not certificates and not allow_empty:
            raise TlsValidationError(f"{label} inválido.")
        return certificates

    @staticmethod
    def _check_validity(certificate: x509.Certificate, *, label: str) -> None:
        now = datetime.now(UTC)
        if certificate.not_valid_before_utc > now:
            raise TlsValidationError(
                f"{label} ainda não é válido; início da validade: "
                f"{certificate.not_valid_before_utc.isoformat()}."
            )
        if certificate.not_valid_after_utc <= now:
            raise TlsValidationError(
                f"{label} expirou em {certificate.not_valid_after_utc.isoformat()}."
            )

    @staticmethod
    def _verify_directly_issued(child: x509.Certificate, issuer: x509.Certificate) -> bool:
        if child.issuer != issuer.subject:
            return False
        try:
            child.verify_directly_issued_by(issuer)
        except (TypeError, ValueError):
            return False
        return True

    @classmethod
    def _is_self_signed(cls, certificate: x509.Certificate) -> bool:
        return certificate.subject == certificate.issuer and cls._verify_directly_issued(
            certificate, certificate
        )

    @staticmethod
    def _is_ca(certificate: x509.Certificate) -> bool:
        try:
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
        except x509.ExtensionNotFound:
            return False
        return constraints.ca

    def _system_roots(self) -> tuple[x509.Certificate, ...]:
        if self._system_roots_cache is not None:
            return self._system_roots_cache
        roots: list[x509.Certificate] = []
        try:
            der_roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        except ssl.SSLError:
            der_roots = []
        for der in der_roots:
            try:
                roots.append(x509.load_der_x509_certificate(der))
            except ValueError:
                continue
        self._system_roots_cache = tuple(roots)
        return self._system_roots_cache

    def _system_trust_anchor(self, certificate: x509.Certificate) -> x509.Certificate | None:
        for root in self._system_roots():
            if self._verify_directly_issued(certificate, root):
                return root
            if self._fingerprint(certificate) == self._fingerprint(root):
                return root
        return None

    def _validate_leaf(self, domain: str, leaf: x509.Certificate, private_key_pem: str) -> None:
        self._check_validity(leaf, label="O certificado do servidor")
        sans = self._sans(leaf)
        if not any(self._dns_matches(name, domain) for name in sans):
            raise TlsValidationError(
                f"O certificado não contém {domain} no Subject Alternative Name."
            )
        try:
            eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        except x509.ExtensionNotFound:
            eku = None
        if eku is not None and not any(
            oid in eku for oid in (ExtendedKeyUsageOID.SERVER_AUTH, self.ANY_EXTENDED_KEY_USAGE)
        ):
            raise TlsValidationError(
                "O certificado não possui finalidade Extended Key Usage adequada para TLS servidor."
            )
        if not private_key_pem.strip() or len(private_key_pem.encode()) > self.PRIVATE_KEY_MAX:
            raise TlsValidationError("Informe a chave privada PEM (máximo 64 KiB).")
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
            raise TlsValidationError("A chave privada não corresponde ao certificado informado.")

    def _prepare_custom(
        self,
        domain: str,
        server_certificate_pem: str,
        intermediate_chain_pem: str,
        private_key_pem: str,
    ) -> dict:
        domain = self.normalize_domain(domain)
        if len(server_certificate_pem.encode()) > self.SERVER_CERTIFICATE_MAX:
            raise TlsValidationError("Certificado do servidor excede o limite de 64 KiB.")
        if len(intermediate_chain_pem.encode()) > self.INTERMEDIATE_CHAIN_MAX:
            raise TlsValidationError("Cadeia intermediária excede o limite de 128 KiB.")

        server_certificates = self._load_certificates(
            server_certificate_pem,
            label="Certificado do servidor",
            allow_empty=False,
        )
        if len(server_certificates) != 1:
            raise TlsValidationError(
                "O campo Certificado do servidor deve conter exatamente um certificado PEM."
            )
        leaf = server_certificates[0]
        self._validate_leaf(domain, leaf, private_key_pem)

        intermediates = self._load_certificates(
            intermediate_chain_pem,
            label="Cadeia intermediária / CA Bundle",
            allow_empty=True,
        )
        leaf_fingerprint = self._fingerprint(leaf)
        seen = {leaf_fingerprint}
        roots: list[x509.Certificate] = []
        non_roots: list[x509.Certificate] = []
        for position, certificate in enumerate(intermediates, start=1):
            label = f"Certificado intermediário #{position}"
            self._check_validity(certificate, label=label)
            if not self._is_ca(certificate):
                raise TlsValidationError(f"{label} não possui BasicConstraints CA=true.")
            fingerprint = self._fingerprint(certificate)
            if fingerprint in seen:
                raise TlsValidationError("A cadeia contém certificados duplicados.")
            seen.add(fingerprint)
            if self._is_self_signed(certificate):
                roots.append(certificate)
            else:
                non_roots.append(certificate)

        ordered: list[x509.Certificate] = []
        remaining = list(non_roots)
        current = leaf
        while remaining:
            matches = [item for item in remaining if self._verify_directly_issued(current, item)]
            if not matches:
                break
            if len(matches) > 1:
                raise TlsValidationError(
                    "A cadeia intermediária é ambígua; mais de um emissor válido foi encontrado."
                )
            parent = matches[0]
            ordered.append(parent)
            remaining.remove(parent)
            current = parent

        if remaining:
            raise TlsValidationError(
                "A cadeia intermediária está quebrada: issuer/subject ou assinatura não "
                "correspondem."
            )

        matching_roots = [root for root in roots if self._verify_directly_issued(current, root)]
        if roots and len(matching_roots) != 1:
            raise TlsValidationError(
                "O Root CA informado não fecha uma cadeia única e válida para o certificado."
            )
        if len(roots) > 1:
            raise TlsValidationError(
                "O CA Bundle contém Root CAs adicionais sem relação com a cadeia."
            )

        omitted_root = matching_roots[0] if matching_roots else None
        trust_anchor = self._system_trust_anchor(current)
        if omitted_root is not None:
            omitted_fingerprint = self._fingerprint(omitted_root)
            root_is_public = any(
                omitted_fingerprint == self._fingerprint(root) for root in self._system_roots()
            )
            if root_is_public:
                trust_status = "PUBLIC_TRUSTED"
                trust_message = "A cadeia termina em uma raiz presente na trust store do sistema."
            else:
                trust_status = "PRIVATE_OR_UNTRUSTED"
                trust_message = (
                    "O Root CA informado foi identificado como privado/não confiável pela "
                    "trust store deste sistema; clientes precisam confiar explicitamente nessa CA."
                )
        elif trust_anchor is not None:
            trust_status = "PUBLIC_TRUSTED"
            trust_message = "A cadeia pode ser ancorada na trust store padrão deste sistema."
        else:
            trust_status = "UNANCHORED"
            trust_message = (
                "A cadeia é criptograficamente consistente, mas não pôde ser ancorada na trust "
                "store deste sistema. Isso pode indicar CA privada ou intermediária ausente."
            )

        fullchain_pem = leaf.public_bytes(serialization.Encoding.PEM).decode() + "".join(
            certificate.public_bytes(serialization.Encoding.PEM).decode() for certificate in ordered
        )
        chain_length = 1 + len(ordered)
        certificate_metadata = self._certificate_metadata(leaf, chain_length=chain_length)
        chain = {
            "status": "VALID" if trust_status != "UNANCHORED" else "UNANCHORED",
            "provided_intermediates": len(intermediates),
            "served_intermediates": len(ordered),
            "served_chain_length": chain_length,
            "root_omitted": omitted_root is not None,
            "root_subject": omitted_root.subject.rfc4514_string() if omitted_root else None,
            "message": (
                "Root CA identificado e omitido do fullchain servido."
                if omitted_root
                else "Cadeia intermediária validada e ordenada."
            ),
        }
        return {
            "certificate": certificate_metadata,
            "chain": chain,
            "trust": {"status": trust_status, "message": trust_message},
            "fullchain_pem": fullchain_pem,
        }

    def validate_custom(
        self,
        domain: str,
        server_certificate_pem: str,
        intermediate_chain_pem: str,
        private_key_pem: str,
    ) -> dict:
        prepared = self._prepare_custom(
            domain,
            server_certificate_pem,
            intermediate_chain_pem,
            private_key_pem,
        )
        return {key: value for key, value in prepared.items() if key != "fullchain_pem"}

    @staticmethod
    def split_legacy_chain(chain_pem: str) -> tuple[str, str]:
        """Split the old leaf+intermediates payload without preserving ambiguous semantics."""
        if not chain_pem.strip():
            return "", ""
        try:
            certificates = x509.load_pem_x509_certificates(chain_pem.encode())
        except ValueError as exc:
            raise TlsValidationError("Certificado ou cadeia PEM inválidos.") from exc
        if not certificates:
            raise TlsValidationError("Nenhum certificado PEM foi encontrado.")
        server = certificates[0].public_bytes(serialization.Encoding.PEM).decode()
        intermediates = "".join(
            item.public_bytes(serialization.Encoding.PEM).decode() for item in certificates[1:]
        )
        return server, intermediates

    @staticmethod
    def _routes(*, https: bool = False) -> str:
        content_security = (
            "\t\tContent-Security-Policy "
            "\"frame-ancestors 'none'; base-uri 'self'; object-src 'none'\""
        )
        headers = [
            "\t\t-Server",
            '\t\tX-Content-Type-Options "nosniff"',
            '\t\tX-Frame-Options "DENY"',
            '\t\tReferrer-Policy "no-referrer"',
            '\t\tPermissions-Policy "camera=(), microphone=(), geolocation=()"',
            content_security,
        ]
        if https:
            headers.append('\t\tStrict-Transport-Security "max-age=31536000"')
        header_block = "\n".join(headers)
        return f"""\theader {{
{header_block}
\t}}

\tencode zstd gzip

\thandle /api/* {{
\t\treverse_proxy api:8000
\t}}

\thandle /health {{
\t\treverse_proxy api:8000
\t}}

\thandle {{
\t\treverse_proxy web:3000
\t}}"""

    def baseline_caddyfile(self) -> str:
        return f"""{{
\tauto_https off
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
        return f"""{{
\tpersist_config off
\tadmin 0.0.0.0:2019 {{
\t\torigins http://api:8000
\t\tenforce_origin
\t}}
}}

http://proxy {{
{self._routes()}
}}

http://{domain} {{
\tredir https://{domain}{{uri}} 308
}}

https://{domain} {{{tls_line}
{self._routes(https=True)}
}}
"""

    def validate(
        self,
        mode: str,
        domain: str,
        server_certificate_pem: str = "",
        intermediate_chain_pem: str = "",
        private_key_pem: str = "",
    ) -> dict:
        domain = self.normalize_domain(domain)
        if mode == "automatic":
            self.managed_caddyfile(domain)
            return {
                "valid": True,
                "mode": mode,
                "domain": domain,
                "certificate": None,
                "chain": None,
                "trust": None,
            }
        if mode != "custom":
            raise TlsValidationError("Modo HTTPS inválido.")
        result = self.validate_custom(
            domain,
            server_certificate_pem,
            intermediate_chain_pem,
            private_key_pem,
        )
        return {"valid": True, "mode": mode, "domain": domain, **result}

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
        os.chmod(path.parent, 0o700)
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

    @staticmethod
    def _verification_error(exc: BaseException) -> str:
        if isinstance(exc, ssl.SSLCertVerificationError):
            message = getattr(exc, "verify_message", None)
            return message or "Falha na confiança da cadeia TLS."
        return "A cadeia não pôde ser validada pela trust store deste sistema."

    def _connect_leaf(
        self,
        host: str,
        domain: str,
        *,
        timeout: float,
        verify: bool,
    ) -> x509.Certificate:
        if verify:
            context = ssl.create_default_context()
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        with (
            socket.create_connection((host, 443), timeout=timeout) as plain,
            context.wrap_socket(plain, server_hostname=domain) as secure,
        ):
            der = secure.getpeercert(binary_form=True)
        if not der:
            raise TlsOperationError("O endpoint não apresentou certificado TLS.")
        return x509.load_der_x509_certificate(der)

    def _probe(
        self,
        domain: str,
        timeout: float = 5,
        *,
        host: str | None = None,
        expected_fingerprint: str | None = None,
        require_trust: bool = False,
    ) -> dict:
        target = host or self.probe_host
        try:
            leaf = self._connect_leaf(target, domain, timeout=timeout, verify=False)
        except (OSError, ssl.SSLError, TimeoutError, TlsOperationError) as exc:
            raise TlsOperationError("O endpoint TLS não pôde ser alcançado ou negociado.") from exc

        sans = self._sans(leaf)
        if not any(self._dns_matches(name, domain) for name in sans):
            raise TlsOperationError("O endpoint apresentou certificado para outro hostname.")
        fingerprint = self._fingerprint(leaf)
        if expected_fingerprint and not secrets.compare_digest(fingerprint, expected_fingerprint):
            raise TlsOperationError("O endpoint apresentou um certificado diferente do esperado.")

        trusted = True
        trust_error = None
        try:
            self._connect_leaf(target, domain, timeout=timeout, verify=True)
        except (OSError, ssl.SSLError, TimeoutError, TlsOperationError) as exc:
            trusted = False
            trust_error = self._verification_error(exc)
        if require_trust and not trusted:
            raise TlsOperationError("O endpoint não apresentou uma cadeia confiável pelo sistema.")

        return {
            "healthy": True,
            "trusted": trusted,
            "trust_error": trust_error,
            "certificate": self._certificate_metadata(leaf),
            "message": (
                "O Caddy local apresentou o certificado esperado e a cadeia é confiável "
                "pelo sistema."
                if trusted
                else "O Caddy local apresentou o certificado esperado, mas a cadeia não é "
                "confiável pela trust store deste sistema."
            ),
        }

    def _wait_probe(
        self,
        domain: str,
        *,
        expected_fingerprint: str | None = None,
        require_trust: bool = False,
    ) -> dict:
        deadline = time.monotonic() + self.verify_timeout
        last_error: TlsOperationError | None = None
        while time.monotonic() < deadline:
            try:
                return self._probe(
                    domain,
                    expected_fingerprint=expected_fingerprint,
                    require_trust=require_trust,
                )
            except TlsOperationError as exc:
                last_error = exc
                time.sleep(2)
        raise last_error or TlsOperationError("Não foi possível validar o TLS local.")

    @staticmethod
    def _empty_dns() -> dict[str, list[str]]:
        return {"a": [], "aaaa": []}

    def _resolve_dns(self, domain: str) -> dict[str, list[str]]:
        addresses = self._empty_dns()
        try:
            records = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror):
            return addresses
        for family, _socktype, _proto, _canonname, sockaddr in records:
            address = sockaddr[0]
            if family == socket.AF_INET and address not in addresses["a"]:
                addresses["a"].append(address)
            elif family == socket.AF_INET6 and address not in addresses["aaaa"]:
                addresses["aaaa"].append(address)
        addresses["a"].sort()
        addresses["aaaa"].sort()
        return addresses

    def _probe_published_endpoint(
        self,
        domain: str,
        address: str,
        *,
        expected_fingerprint: str | None,
        timeout: float = 3,
    ) -> dict:
        family = "AAAA" if ":" in address else "A"
        endpoint = {
            "record_type": family,
            "address": address,
            "status": "UNREACHABLE",
            "fingerprint_sha256": None,
            "fingerprint_matches": None,
            "hostname_valid": False,
            "trusted": None,
            "trust_error": None,
            "issuer": None,
            "valid_until": None,
            "message": "O endpoint não pôde ser testado a partir deste host.",
        }
        try:
            leaf = self._connect_leaf(address, domain, timeout=timeout, verify=False)
        except (OSError, ssl.SSLError, TimeoutError, TlsOperationError):
            return endpoint

        metadata = self._certificate_metadata(leaf)
        fingerprint = metadata["fingerprint_sha256"]
        hostname_valid = any(self._dns_matches(name, domain) for name in metadata["san"])
        fingerprint_matches = (
            secrets.compare_digest(fingerprint, expected_fingerprint)
            if expected_fingerprint
            else None
        )
        trusted = True
        trust_error = None
        try:
            self._connect_leaf(address, domain, timeout=timeout, verify=True)
        except (OSError, ssl.SSLError, TimeoutError, TlsOperationError) as exc:
            trusted = False
            trust_error = self._verification_error(exc)

        endpoint.update(
            {
                "fingerprint_sha256": fingerprint,
                "fingerprint_matches": fingerprint_matches,
                "hostname_valid": hostname_valid,
                "trusted": trusted,
                "trust_error": trust_error,
                "issuer": metadata["issuer"],
                "valid_until": metadata["valid_until"],
            }
        )
        if not hostname_valid or fingerprint_matches is False:
            endpoint["status"] = "MISMATCH"
            endpoint["message"] = "O endpoint apresentou um certificado diferente do esperado."
        elif expected_fingerprint is None:
            endpoint["status"] = "PARTIAL"
            endpoint["message"] = "Endpoint acessível, mas sem fingerprint local para comparação."
        else:
            endpoint["status"] = "VERIFIED"
            endpoint["message"] = "O endpoint apresentou o mesmo certificado aplicado localmente."
        return endpoint

    def _public_diagnostics(
        self, domain: str, *, expected_fingerprint: str | None
    ) -> tuple[dict, dict]:
        dns = self._resolve_dns(domain)
        addresses = [("A", address) for address in dns["a"]] + [
            ("AAAA", address) for address in dns["aaaa"]
        ]
        if not addresses:
            return dns, {
                "status": "DNS_NOT_FOUND",
                "endpoints": [],
                "message": "O domínio não possui registros A/AAAA resolvidos deste host.",
            }

        endpoints = [
            self._probe_published_endpoint(
                domain,
                address,
                expected_fingerprint=expected_fingerprint,
            )
            for _record_type, address in addresses
        ]
        statuses = [item["status"] for item in endpoints]
        if "MISMATCH" in statuses:
            status = "MISMATCH"
            message = "Ao menos um endpoint DNS acessível apresenta certificado divergente."
        elif all(item == "VERIFIED" for item in statuses):
            status = "VERIFIED"
            message = "Todos os endpoints DNS testados apresentaram o certificado esperado."
        elif any(item == "VERIFIED" for item in statuses):
            status = "PARTIAL"
            message = "Parte dos endpoints foi validada; outros não puderam ser confirmados."
        elif all(item == "UNREACHABLE" for item in statuses):
            status = "UNREACHABLE"
            message = "Os endpoints DNS não puderam ser alcançados a partir deste host."
        else:
            status = "PARTIAL"
            message = "A validação dos endpoints DNS foi apenas parcial."
        return dns, {"status": status, "endpoints": endpoints, "message": message}

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

    @staticmethod
    def _trust_summary(state: dict, local_tls: dict) -> dict:
        if local_tls.get("trusted") is True:
            return {
                "status": "PUBLIC_TRUSTED",
                "message": "A cadeia apresentada é confiável pela trust store deste sistema.",
            }
        saved = state.get("trust") or {}
        if saved.get("status") == "PRIVATE_OR_UNTRUSTED":
            return saved
        return {
            "status": "UNTRUSTED_OR_INCOMPLETE",
            "message": (
                "A cadeia apresentada não é confiável pela trust store deste sistema. "
                "Confirme se a CA é privada ou se existe intermediária ausente."
            ),
        }

    def _status_from_state(self, state: dict, *, local_tls: dict | None = None) -> dict:
        domain = state["domain"]
        saved_fingerprint = (state.get("certificate") or {}).get("fingerprint_sha256")
        probe_fingerprint = saved_fingerprint if state["mode"] == "custom" else None
        if local_tls is None:
            try:
                local_tls = self._probe(domain, timeout=4, expected_fingerprint=probe_fingerprint)
            except TlsOperationError as exc:
                local_tls = {
                    "healthy": False,
                    "trusted": None,
                    "trust_error": None,
                    "certificate": None,
                    "message": f"TLS local requer atenção: {exc}",
                }
        current_fingerprint = (local_tls.get("certificate") or {}).get("fingerprint_sha256")
        expected = current_fingerprint or saved_fingerprint

        dns, endpoint_validation = self._public_diagnostics(domain, expected_fingerprint=expected)
        certificate = local_tls.get("certificate") or state.get("certificate")
        if certificate and state.get("certificate", {}).get("chain_length"):
            certificate = {
                **certificate,
                "chain_length": state["certificate"]["chain_length"],
            }
        last_validated_at = datetime.now(UTC).isoformat()
        trust = self._trust_summary(state, local_tls)
        message = (
            "TLS local válido. Consulte separadamente DNS, endpoint publicado e confiança da CA."
            if local_tls["healthy"]
            else "Configuração salva, mas o TLS local não pôde ser validado agora."
        )
        return {
            "configured": True,
            "mode": state["mode"],
            "domain": domain,
            "healthy": local_tls["healthy"],
            "local_tls": local_tls,
            "dns": dns,
            "endpoint_validation": endpoint_validation,
            "certificate": certificate,
            "chain": state.get("chain"),
            "trust": trust,
            "applied_at": state.get("applied_at"),
            "last_validated_at": last_validated_at,
            "message": message,
        }

    def status(self) -> dict:
        state = self._read_state()
        if not state:
            return {
                "configured": False,
                "mode": "http",
                "domain": None,
                "healthy": False,
                "local_tls": {
                    "healthy": False,
                    "trusted": None,
                    "trust_error": None,
                    "certificate": None,
                    "message": "TLS local ainda não foi configurado pelo DeepOps.",
                },
                "dns": self._empty_dns(),
                "endpoint_validation": {
                    "status": "DNS_NOT_FOUND",
                    "endpoints": [],
                    "message": "Sem domínio HTTPS configurado para diagnóstico.",
                },
                "certificate": None,
                "chain": None,
                "trust": None,
                "applied_at": None,
                "last_validated_at": None,
                "message": "HTTPS ainda não foi configurado pelo DeepOps.",
            }
        return self._status_from_state(state)

    def _write_custom_files(
        self, metadata: dict, fullchain_pem: str, private_key_pem: str
    ) -> tuple[Path, str, str]:
        reference = metadata["fingerprint_sha256"].lower()[:16] + "-" + secrets.token_hex(6)
        directory = self.certs_path / reference
        directory.mkdir(parents=True, mode=0o700)
        os.chmod(directory, 0o700)
        self._atomic_write(directory / "fullchain.pem", fullchain_pem.encode())
        self._atomic_write(directory / "private-key.pem", private_key_pem.encode())
        return (
            directory,
            f"/config/deepops/certs/{reference}/fullchain.pem",
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
            return

    def apply(
        self,
        mode: str,
        domain: str,
        server_certificate_pem: str = "",
        intermediate_chain_pem: str = "",
        private_key_pem: str = "",
    ) -> dict:
        domain = self.normalize_domain(domain)
        custom_directory: Path | None = None
        certificate_path = key_path = None
        if mode == "custom":
            prepared = self._prepare_custom(
                domain,
                server_certificate_pem,
                intermediate_chain_pem,
                private_key_pem,
            )
            metadata = prepared["certificate"]
            require_trust = prepared["trust"]["status"] == "PUBLIC_TRUSTED"
        elif mode == "automatic":
            prepared = None
            metadata = None
            require_trust = True
        else:
            raise TlsValidationError("Modo HTTPS inválido.")

        with self._locked():
            previous_file = self.config_path.read_bytes() if self.config_path.exists() else None
            previous_runtime = (
                previous_file.decode() if previous_file is not None else self.baseline_caddyfile()
            )
            if prepared is not None:
                try:
                    custom_directory, certificate_path, key_path = self._write_custom_files(
                        metadata,
                        prepared["fullchain_pem"],
                        private_key_pem,
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
                local_tls = self._wait_probe(
                    domain,
                    expected_fingerprint=(metadata or {}).get("fingerprint_sha256"),
                    require_trust=require_trust,
                )
            except TlsOperationError as exc:
                try:
                    self._load(previous_runtime)
                except TlsOperationError as rollback_error:
                    raise TlsOperationError(
                        "A verificação TLS local falhou e a restauração automática também falhou."
                    ) from rollback_error
                if custom_directory:
                    shutil.rmtree(custom_directory, ignore_errors=True)
                raise exc

            certificate = local_tls.get("certificate") or metadata
            if metadata and certificate:
                certificate = {**certificate, "chain_length": metadata["chain_length"]}
            state = {
                "version": 2,
                "mode": mode,
                "domain": domain,
                "certificate": certificate,
                "chain": prepared["chain"] if prepared else None,
                "trust": prepared["trust"] if prepared else None,
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
            return self._status_from_state(state, local_tls=local_tls)


manager = TlsManager()
