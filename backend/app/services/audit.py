from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, SecretBytes, SecretStr
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent

if TYPE_CHECKING:
    from app.models.user import User

AUDIT_SOURCES = frozenset({"UI", "API", "SYSTEM"})
MAX_BEFORE_AFTER_BYTES = 16_384
MAX_CHANGES_BYTES = 16_384
MAX_METADATA_BYTES = 8_192
MAX_STRING_VALUE_CHARS = 2_048

_SECRET_KEYS = {
    "password",
    "token",
    "passwordhash",
    "secret",
    "secretkey",
    "privatekey",
    "accesskey",
    "accesskeyid",
    "secretaccesskey",
    "sessiontoken",
    "refreshtoken",
    "bearertoken",
    "jwt",
    "mfasecret",
    "recoverycodes",
    "recoverycode",
    "invitationtoken",
    "passwordresettoken",
    "credentials",
    "credential",
    "passphrase",
    "smtppassword",
    "ociprivatekey",
    "awssecretkey",
    "certificateprivatekey",
}
_SECRET_SUFFIXES = (
    "password",
    "passwordhash",
    "privatekey",
    "secret",
    "secretkey",
    "accesskey",
    "secretaccesskey",
    "token",
    "sessiontoken",
    "refreshtoken",
    "bearertoken",
    "resettoken",
    "invitationtoken",
    "mfasecret",
    "passphrase",
    "credentials",
)

_OMIT = object()


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _sensitive_key(value: Any) -> bool:
    key = _normalized_key(value)
    return key in _SECRET_KEYS or any(key.endswith(suffix) for suffix in _SECRET_SUFFIXES)


def _large_string_summary(value: str) -> dict[str, Any]:
    raw = value.encode("utf-8", errors="replace")
    kind = "certificate_pem" if "-----BEGIN CERTIFICATE-----" in value else "large_text"
    return {
        "_omitted": kind,
        "_length": len(value),
        "_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (SecretStr, SecretBytes)):
        return _OMIT
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        upper = value.upper()
        if (
            re.search(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", upper)
            or upper.startswith("BEARER ")
            or (value.startswith("eyJ") and value.count(".") == 2 and len(value) > 40)
        ):
            return _OMIT
        if len(value) > MAX_STRING_VALUE_CHARS or "-----BEGIN CERTIFICATE-----" in value:
            return _large_string_summary(value)
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value, key=lambda item: str(item)):
            if _sensitive_key(key):
                continue
            safe = _json_safe(value[key])
            if safe is not _OMIT:
                result[str(key)] = safe
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            safe = _json_safe(item)
            if safe is not _OMIT:
                result.append(safe)
        return result
    if isinstance(value, (set, frozenset)):
        items = []
        for item in value:
            safe = _json_safe(item)
            if safe is not _OMIT:
                items.append(safe)
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))

    # Unknown objects are intentionally represented only by their type. Calling
    # repr()/str() here could accidentally serialize credentials.
    return {"_type": type(value).__name__}


def _limit_payload(value: Any, max_bytes: int) -> Any:
    if value is None:
        return None
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) <= max_bytes:
        return value
    return {
        "_truncated": True,
        "_original_bytes": len(raw),
        "_sha256": hashlib.sha256(raw).hexdigest(),
    }


def sanitize_audit_payload(payload: Any, *, max_bytes: int = MAX_BEFORE_AFTER_BYTES) -> Any:
    """Return a deterministic, JSON-safe and secret-free audit representation."""

    safe = _json_safe(payload)
    if safe is _OMIT:
        return None
    return _limit_payload(safe, max_bytes)


def audit_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build an explicit audit snapshot without introspecting ORM internals."""

    safe = sanitize_audit_payload(dict(payload), max_bytes=MAX_BEFORE_AFTER_BYTES)
    if not isinstance(safe, dict):
        return {}
    return safe


def build_audit_changes(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Calculate a deterministic first-level diff."""

    old = dict(before or {})
    new = dict(after or {})
    changes: dict[str, Any] = {}
    for key in sorted(set(old) | set(new)):
        previous = old.get(key)
        current = new.get(key)
        if previous != current:
            changes[key] = {"from": previous, "to": current}
    limited = _limit_payload(changes, MAX_CHANGES_BYTES)
    return limited if isinstance(limited, dict) else {}


def _text(value: Any, *, max_length: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError("Required audit field is missing")
        return None
    text = str(value).strip()
    if required and not text:
        raise ValueError("Required audit field is blank")
    if not text:
        return None
    return text[:max_length]


class AuditService:
    @staticmethod
    def record(
        db: Session,
        *,
        actor: User | None,
        action: str,
        module: str,
        entity_type: str,
        entity_id: Any = None,
        entity_label: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        source: str = "API",
        metadata: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditEvent:
        """Add an AuditEvent to the caller transaction without committing it."""

        source = source.upper().strip()
        if source not in AUDIT_SOURCES:
            raise ValueError(f"Unsupported audit source: {source}")

        clean_before = sanitize_audit_payload(before, max_bytes=MAX_BEFORE_AFTER_BYTES)
        clean_after = sanitize_audit_payload(after, max_bytes=MAX_BEFORE_AFTER_BYTES)
        before_mapping = clean_before if isinstance(clean_before, dict) else {}
        after_mapping = clean_after if isinstance(clean_after, dict) else {}
        clean_changes = build_audit_changes(before_mapping, after_mapping)
        clean_metadata = sanitize_audit_payload(metadata, max_bytes=MAX_METADATA_BYTES)

        actor_id = getattr(actor, "id", None) if actor is not None else None
        actor_name = getattr(actor, "name", None) if actor is not None else None
        actor_email = getattr(actor, "email", None) if actor is not None else None
        if actor is None and source == "SYSTEM":
            actor_name = "SYSTEM"

        item = AuditEvent(
            actor_id=_text(actor_id, max_length=36),
            actor_name_snapshot=_text(actor_name, max_length=120),
            actor_email_snapshot=_text(actor_email, max_length=254),
            action=_text(action, max_length=120, required=True),
            module=_text(module, max_length=80, required=True),
            entity_type=_text(entity_type, max_length=120, required=True),
            entity_id=_text(entity_id, max_length=255),
            entity_label=_text(entity_label, max_length=500),
            source=source,
            before_data=clean_before if isinstance(clean_before, dict) else None,
            after_data=clean_after if isinstance(clean_after, dict) else None,
            changes=clean_changes,
            metadata_json=clean_metadata if isinstance(clean_metadata, dict) else None,
            correlation_id=_text(correlation_id, max_length=36),
        )
        db.add(item)
        return item


audit_service = AuditService()
