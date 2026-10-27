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


class InventoryCoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


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


@dataclass(frozen=True, slots=True)
class InventoryCoverage:
    """Evidence about one deterministically comparable discovery scope."""

    provider: str
    cloud_account_id: int
    resource_type: str
    status: InventoryCoverageStatus | str
    region: str | None = None
    scope: tuple[tuple[str, str], ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        provider = normalize_provider(self.provider)
        resource_type = str(self.resource_type or "").strip()
        if self.cloud_account_id is None or int(self.cloud_account_id) <= 0:
            raise ValueError("cloud_account_id must identify a persisted CloudAccount")
        if not resource_type:
            raise ValueError("coverage resource_type is required")
        try:
            status = InventoryCoverageStatus(str(self.status))
        except ValueError as exc:
            raise ValueError(f"Unsupported Inventory coverage status: {self.status!r}") from exc

        canonical_scope: list[tuple[str, str]] = []
        seen_scope_keys: set[str] = set()
        for raw_key, raw_value in self.scope:
            key = str(raw_key or "").strip()
            value = str(raw_value or "").strip()
            if not key or not value:
                raise ValueError("coverage scope entries require non-empty key/value")
            if key in seen_scope_keys:
                raise ValueError(f"Duplicate coverage scope key: {key}")
            seen_scope_keys.add(key)
            canonical_scope.append((key, value))

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "cloud_account_id", int(self.cloud_account_id))
        object.__setattr__(self, "resource_type", resource_type)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "region", str(self.region).strip() if self.region else None)
        object.__setattr__(self, "scope", tuple(sorted(canonical_scope)))
        object.__setattr__(
            self,
            "error_code",
            str(self.error_code).strip()[:120] if self.error_code else None,
        )
        object.__setattr__(
            self,
            "error_message",
            str(self.error_message).strip()[:500] if self.error_message else None,
        )

    @property
    def reconciliation_key(self) -> tuple[str, str | None, tuple[tuple[str, str], ...]]:
        return (self.resource_type, self.region, self.scope)


@dataclass(frozen=True, slots=True)
class InventoryDiscoveryIssue:
    """Sanitized discovery issue safe for logs and collection diagnostics."""

    provider: str
    resource_type: str | None
    region: str | None
    category: str
    code: str | None = None
    message: str = "Inventory discovery scope could not be completed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", normalize_provider(self.provider))
        object.__setattr__(self, "category", str(self.category or "provider_error")[:120])
        object.__setattr__(self, "code", str(self.code)[:120] if self.code else None)
        object.__setattr__(self, "message", str(self.message or "Inventory discovery failed")[:500])


@dataclass(frozen=True, slots=True)
class InventoryDiscoveryResult:
    """Provider-neutral output consumed by persistence and collection orchestration."""

    resources: tuple[DiscoveredInventoryResource, ...] = ()
    coverage: tuple[InventoryCoverage, ...] = ()
    warnings: tuple[InventoryDiscoveryIssue, ...] = ()
    errors: tuple[InventoryDiscoveryIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "coverage", tuple(self.coverage))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def resources_analyzed(self) -> int:
        """Count unique resources actually observed, independent of coverage failures."""

        return len(
            {
                (resource.provider, resource.resource_type, resource.resource_id)
                for resource in self.resources
            }
        )
