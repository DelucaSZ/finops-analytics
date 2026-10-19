from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr

from app.core.security import require_admin, require_recent_admin
from app.models.user import User
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


@router.get("")
def get_tls_status() -> dict:
    return manager.status()


@router.post("/validate")
def validate_tls(payload: TlsPayload) -> dict:
    return _call(manager.validate, payload)


@router.post("/apply")
def apply_tls(
    payload: TlsPayload,
    _actor: User = Depends(require_recent_admin),
) -> dict:
    return _call(manager.apply, payload)
