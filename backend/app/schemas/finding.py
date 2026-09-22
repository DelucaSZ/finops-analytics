from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: int
    rule_key: str
    service: str
    region: str
    resource_id: str
    resource_name: str | None
    title: str
    description: str
    evidence: dict
    current_monthly_cost: Decimal
    estimated_monthly_savings: Decimal
    confidence: str
    severity: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


class FindingStatusUpdate(BaseModel):
    status: str
