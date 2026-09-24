#!/usr/bin/env python3
"""Validate that a DeepOps host is ready for controlled public HTTPS exposure."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


class ReadinessError(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_environment(values: dict[str, str]) -> str:
    if values.get("NUVEMIQ_ENVIRONMENT", "").strip().lower() != "production":
        raise ReadinessError("NUVEMIQ_ENVIRONMENT precisa ser production.")

    public_url = values.get("NUVEMIQ_PUBLIC_URL", "").strip().rstrip("/")
    parsed = urlsplit(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ReadinessError("NUVEMIQ_PUBLIC_URL precisa ser uma origem HTTPS sem caminho.")

    if values.get("NUVEMIQ_COOKIE_SECURE", "").strip().lower() in {"0", "false", "no", "off"}:
        raise ReadinessError("NUVEMIQ_COOKIE_SECURE não pode estar desabilitado em produção.")

    if not is_true(values.get("NUVEMIQ_MFA_REQUIRED")):
        raise ReadinessError("NUVEMIQ_MFA_REQUIRED precisa estar true antes da exposição externa.")

    if is_true(values.get("NUVEMIQ_DEMO_MODE")):
        raise ReadinessError("NUVEMIQ_DEMO_MODE precisa estar false em produção.")

    cors = [
        item.strip().rstrip("/")
        for item in values.get("NUVEMIQ_CORS_ORIGINS", "").split(",")
        if item.strip()
    ]
    if cors != [public_url]:
        raise ReadinessError(
            "NUVEMIQ_CORS_ORIGINS deve conter somente a mesma origem de NUVEMIQ_PUBLIC_URL."
        )
    return parsed.hostname


def compose_config(repo: Path, env_file: Path) -> dict:
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-directory",
                str(repo),
                "--env-file",
                str(env_file),
                "-f",
                str(repo / "compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReadinessError("Não foi possível renderizar o Docker Compose.") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReadinessError("Docker Compose retornou configuração inválida.") from exc


def validate_ports(config: dict) -> None:
    services = config.get("services", {})
    allowed = {("proxy", 80, 80), ("proxy", 443, 443)}
    observed: set[tuple[str, int, int]] = set()
    for name, service in services.items():
        for port in service.get("ports", []) or []:
            try:
                published = int(port["published"])
                target = int(port["target"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ReadinessError(f"Mapeamento de porta inesperado em {name}.") from exc
            observed.add((name, published, target))
    if observed != allowed:
        raise ReadinessError(
            "Somente proxy:80->80 e proxy:443->443 podem ser publicados; "
            f"mapeamentos encontrados: {sorted(observed)}"
        )


def validate_persisted_tls(repo: Path) -> None:
    try:
        subprocess.run(
            [
                "docker",
                "compose",
                "--project-directory",
                str(repo),
                "-f",
                str(repo / "compose.yaml"),
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                (
                    "from pathlib import Path; "
                    "base=Path('/var/lib/deepops/caddy/deepops'); "
                    "assert (base/'Caddyfile').stat().st_size > 0; "
                    "assert (base/'state.json').stat().st_size > 0"
                ),
            ],
            cwd=repo,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReadinessError(
            "A configuração HTTPS persistida não pôde ser confirmada dentro da API."
        ) from exc


def local_https_probe(domain: str) -> None:
    context = ssl.create_default_context()
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=8) as plain:
            with context.wrap_socket(plain, server_hostname=domain) as secure:
                request = (
                    f"GET /health HTTP/1.1\r\nHost: {domain}\r\n"
                    "Connection: close\r\nAccept: application/json\r\n\r\n"
                )
                secure.sendall(request.encode("ascii"))
                chunks = []
                while True:
                    chunk = secure.recv(8192)
                    if not chunk:
                        break
                    chunks.append(chunk)
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        raise ReadinessError("Falha no handshake HTTPS local com certificado confiável.") from exc

    raw = b"".join(chunks)
    head, separator, body = raw.partition(b"\r\n\r\n")
    if not separator:
        raise ReadinessError("Resposta HTTPS inválida.")
    lines = head.decode("iso-8859-1").split("\r\n")
    if not lines or " 200 " not in lines[0]:
        raise ReadinessError(f"/health não retornou HTTP 200: {lines[0] if lines else 'sem status'}")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    if "max-age=" not in headers.get("strict-transport-security", "").lower():
        raise ReadinessError("Strict-Transport-Security ausente no HTTPS público.")
    if headers.get("x-content-type-options", "").lower() != "nosniff":
        raise ReadinessError("X-Content-Type-Options ausente ou inválido.")
    if b'"status":"ok"' not in body.replace(b" ", b""):
        raise ReadinessError("/health não retornou status ok.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Diretório do checkout DeepOps.")
    parser.add_argument("--env-file", default=".env", help="Arquivo de ambiente relativo ao repo.")
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Valida somente publicação de portas do Compose; usado em CI.",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    env_file = (repo / args.env_file).resolve()

    try:
        config = compose_config(repo, env_file)
        validate_ports(config)
        if not args.static_only:
            values = load_env(env_file)
            domain = validate_environment(values)
            validate_persisted_tls(repo)
            local_https_probe(domain)
    except (ReadinessError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.static_only:
        print("OK: Compose publica somente 80/443 no proxy.")
    else:
        print("OK: DeepOps pronto localmente para exposição HTTPS controlada.")
        print("A validação final ainda deve ser executada de fora da VPC/EC2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
