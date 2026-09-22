from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class CollectedFinding:
    rule_key: str
    service: str
    region: str
    resource_id: str
    title: str
    description: str
    resource_name: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    current_monthly_cost: Decimal = Decimal("0")
    estimated_monthly_savings: Decimal = Decimal("0")
    confidence: str = "medium"
    severity: str = "medium"
