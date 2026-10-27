"""Provider-neutral Inventory domain contracts and metadata guardrails."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.cloud import normalize_provider

MAX_INVENTORY_JSON_BYTES = 256 * 1024
MAX_INVENTORY_JSON_DEPTH = 12
MAX_INVENTORY_STRING_LENGTH = 64 * 1024

_SENSITIVE_METADATA_KEYS = {
    "access_key",
    "access_key_id",
    "aws_access_key_id",
    "secret_access_key",
    "aws_secret_access_key",
    "secret_key",
    "session_token",
    "aws_session_token",
    "private_key",
    "private_key_pem",
    "private_key_ciphertext",
    "private_key_password",
    "private_key_password_ciphertext",
    "password",
    "authorization",
    "authorization_header",
    "credentials",
    "credential_payload",
    "bearer_token",
    "auth_token",
}


class InventoryPresenceStatus(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"


def _normalized_metadata_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _validate_metadata_node(value: Any, *, depth: int, path: str) -> None:
    if depth > MAX_INVENTORY_JSON_DEPTH:
        raise ValueError(f"Inventory metadata exceeds maximum depth at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_metadata_key(key)
            if normalized in _SENSITIVE_METADATA_KEYS:
                raise ValueError(f"Sensitive metadata key is not allowed at {path}.{key}")
            _validate_metadata_node(child, depth=depth + 1, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_metadata_node(child, depth=depth + 1, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and len(value) > MAX_INVENTORY_STRING_LENGTH:
        raise ValueError(f"Inventory metadata string is too large at {path}")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"Inventory metadata is not JSON-compatible at {path}")


def prepare_inventory_metadata(value: dict[str, Any], *, field_name: str) -> dict[str, Any]:
    """Validate untrusted provider metadata and return an independent snapshot."""

    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    _validate_metadata_node(value, depth=0, path=field_name)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain JSON-compatible data") from exc
    if len(encoded) > MAX_INVENTORY_JSON_BYTES:
        raise ValueError(
            f"{field_name} exceeds the {MAX_INVENTORY_JSON_BYTES}-byte Inventory limit"
        )
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class DiscoveredInventoryResource:
    """Provider-neutral boundary between discovery adapters and persistence."""

    provider: str
    resource_id: str
    resource_type: str
    native_resource_type: str | None = None
    service: str | None = None
    name: str | None = None
    region: str | None = None
    availability_zone: str | None = None
    lifecycle_status: str = "unknown"
    native_status: str | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = normalize_provider(self.provider)
        resource_id = str(self.resource_id or "").strip()
        resource_type = str(self.resource_type or "").strip()
        lifecycle_status = str(self.lifecycle_status or "unknown").strip() or "unknown"
        if not resource_id:
            raise ValueError("resource_id is required")
        if not resource_type:
            raise ValueError("resource_type is required")
        tags = prepare_inventory_metadata(self.tags, field_name="tags")
        attributes = prepare_inventory_metadata(self.attributes, field_name="attributes")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "resource_type", resource_type)
        object.__setattr__(self, "lifecycle_status", lifecycle_status)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "attributes", attributes)
