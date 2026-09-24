import hashlib
import json


def _normalize(
    value: str | int | None,
    *,
    field: str,
    lowercase: bool = False,
    allow_empty: bool = False,
) -> str:
    normalized = "" if value is None else str(value).strip()
    if lowercase:
        normalized = normalized.lower()
    if not normalized and not allow_empty:
        raise ValueError(f"{field} must not be empty")
    return normalized


def build_opportunity_fingerprint_v1(
    *,
    provider: str,
    account_id: str | int,
    region: str | None,
    resource_id: str,
    rule_id: str,
    scope: str | None = None,
) -> str:
    """Build the stable v1 identity for one logical optimization opportunity."""
    payload = [
        "opportunity-fingerprint:v1",
        _normalize(provider, field="provider", lowercase=True),
        _normalize(account_id, field="account_id"),
        _normalize(region, field="region", lowercase=True, allow_empty=True),
        _normalize(scope, field="scope", lowercase=True, allow_empty=True),
        _normalize(resource_id, field="resource_id"),
        _normalize(rule_id, field="rule_id", lowercase=True),
    ]
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_opportunity_fingerprint(
    *,
    provider: str,
    account_id: str | int,
    region: str | None,
    resource_id: str,
    rule_id: str,
    scope: str | None = None,
) -> str:
    return build_opportunity_fingerprint_v1(
        provider=provider,
        account_id=account_id,
        region=region,
        resource_id=resource_id,
        rule_id=rule_id,
        scope=scope,
    )
