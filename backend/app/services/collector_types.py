from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class CollectedFinding:
    """Provider-neutral result emitted by a provider-specific collector/analyzer."""

    rule_key: str
    service: str
    region: str | None
    resource_id: str
    title: str
    description: str
    resource_name: str | None = None
    resource_type: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    current_monthly_cost: Decimal = Decimal("0")
    estimated_monthly_savings: Decimal = Decimal("0")
    currency: str = "USD"
    confidence: str = "medium"
    severity: str = "medium"
