from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    treated_at: datetime | None = None
    treated_by: str | None = None
    treatment_note: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    rejection_note: str | None = None
    needs_review: bool = False


class OpportunityNote(BaseModel):
    note: str | None = Field(default=None, max_length=4000)


class OpportunityReject(BaseModel):
    reason: Literal["FALSE_POSITIVE", "OPERATIONAL_EXCEPTION", "ACCEPTABLE_COST", "RESOURCE_REQUIRED", "RISK_ACCEPTED", "OTHER"]
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_other_note(self):
        if self.reason == "OTHER" and not (self.note or "").strip():
            raise ValueError("Uma observação é obrigatória para o motivo Outro.")
        return self


class OpportunityBulkAction(BaseModel):
    finding_ids: list[str] = Field(min_length=1)
    action: Literal["treat", "reject", "reopen"]
    reason: Literal["FALSE_POSITIVE", "OPERATIONAL_EXCEPTION", "ACCEPTABLE_COST", "RESOURCE_REQUIRED", "RISK_ACCEPTED", "OTHER"] | None = None
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "reject" and self.reason is None:
            raise ValueError("Motivo é obrigatório para rejeição.")
        if self.action == "reject" and self.reason == "OTHER" and not (self.note or "").strip():
            raise ValueError("Uma observação é obrigatória para o motivo Outro.")
        return self
