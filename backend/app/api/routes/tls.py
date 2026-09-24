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
    certificate_chain: str = Field(default="", max_length=131_072)
    private_key: SecretStr | None = None


def _values(payload: TlsPayload) -> tuple[str, str]:
    return (
        payload.certificate_chain,
        payload.private_key.get_secret_value() if payload.private_key else "",
    )


def _call(function, payload: TlsPayload) -> dict:
    chain, private_key = _values(payload)
    try:
        return function(payload.mode, payload.domain, chain, private_key)
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
