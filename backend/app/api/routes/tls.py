from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_recent_admin
from app.db.session import get_db
from app.models.user import User
from app.services.audit import AuditService, audit_snapshot
from app.services.tls_manager import TlsOperationError, TlsValidationError, manager

router = APIRouter(prefix="/tls", tags=["tls"], dependencies=[Depends(require_admin)])


class TlsPayload(BaseModel):
    mode: Literal["automatic", "custom"]
    domain: str = Field(min_length=1, max_length=253)
    server_certificate: str = Field(default="", max_length=65_536)
    intermediate_chain: str = Field(default="", max_length=131_072)
    private_key: SecretStr | None = None
    # Transitional compatibility for API clients using the pre-24.1 contract.
    certificate_chain: str | None = Field(default=None, max_length=196_608)


def _values(payload: TlsPayload) -> tuple[str, str, str]:
    server_certificate = payload.server_certificate
    intermediate_chain = payload.intermediate_chain
    legacy_chain = payload.certificate_chain or ""
    if legacy_chain.strip():
        if server_certificate.strip() or intermediate_chain.strip():
            raise TlsValidationError(
                "Use o novo contrato server_certificate/intermediate_chain ou o campo legado, "
                "não ambos."
            )
        server_certificate, intermediate_chain = manager.split_legacy_chain(legacy_chain)
    return (
        server_certificate,
        intermediate_chain,
        payload.private_key.get_secret_value() if payload.private_key else "",
    )


def _call(function: Callable[..., dict], payload: TlsPayload) -> dict:
    try:
        server_certificate, intermediate_chain, private_key = _values(payload)
        return function(
            payload.mode,
            payload.domain,
            server_certificate,
            intermediate_chain,
            private_key,
        )
    except TlsValidationError as exc:
        raise HTTPException(422, str(exc)) from None
    except TlsOperationError as exc:
        raise HTTPException(503, str(exc)) from None


def _tls_audit_snapshot(status: dict) -> dict:
    certificate = status.get("certificate") or {}
    local_tls = status.get("local_tls") or {}
    local_certificate = local_tls.get("certificate") or {}
    effective_certificate = certificate or local_certificate
    trust = status.get("trust") or {}
    return audit_snapshot(
        {
            "configured": status.get("configured"),
            "mode": status.get("mode"),
            "domain": status.get("domain"),
            "healthy": status.get("healthy"),
            "certificate": {
                "fingerprint_sha256": effective_certificate.get("fingerprint_sha256"),
                "issuer": effective_certificate.get("issuer"),
                "valid_from": effective_certificate.get("valid_from"),
                "valid_until": effective_certificate.get("valid_until"),
                "chain_length": effective_certificate.get("chain_length"),
            },
            "local_tls": {
                "healthy": local_tls.get("healthy"),
                "trusted": local_tls.get("trusted"),
            },
            "trust": {"status": trust.get("status")},
        }
    )


@router.get("")
def get_tls_status() -> dict:
    return manager.status()


@router.post("/validate")
def validate_tls(payload: TlsPayload) -> dict:
    return _call(manager.validate, payload)


@router.post("/apply")
def apply_tls(
    payload: TlsPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(require_recent_admin),
) -> dict:
    result = _call(manager.apply, payload)
    after = _tls_audit_snapshot(result)
    AuditService.record(
        db,
        actor=actor,
        module="tls",
        action="tls.apply",
        entity_type="tls_configuration",
        entity_id=None,
        entity_label=after.get("domain") or payload.domain,
        before=None,
        after=after,
        source="API",
        metadata={
            "domain": after.get("domain") or payload.domain,
            "mode": after.get("mode") or payload.mode,
            "certificate": after.get("certificate"),
            "local_tls": after.get("local_tls"),
        },
    )
    db.commit()
    return result
