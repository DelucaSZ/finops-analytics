from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

CycleMode = Literal["CALENDAR_MONTH", "FIXED_DAYS"]


class OpportunityPolicyFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_mode: CycleMode = "CALENDAR_MONTH"
    cycle_length_days: int = Field(30, ge=7, le=365)
    cycle_timezone: str = Field("UTC", min_length=1, max_length=64)
    cycle_anchor_date: date | None = None
    automatic_cycle_close_enabled: bool = False
    treated_archive_enabled: bool = True
    treated_archive_days: int = Field(30, ge=1, le=3650)
    rejected_archive_enabled: bool = True
    rejected_archive_days: int = Field(30, ge=1, le=3650)
    resolved_external_archive_enabled: bool = True
    resolved_external_archive_days: int = Field(30, ge=1, le=3650)
    open_archive_enabled: bool = False
    open_archive_days: int = Field(30, ge=1, le=3650)
    observation_retention_days: int = Field(400, ge=30, le=3650)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_cycle(self) -> "OpportunityPolicyFields":
        try:
            ZoneInfo(self.cycle_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("cycle_timezone must be a valid IANA timezone") from exc

        if self.cycle_mode == "FIXED_DAYS" and self.cycle_anchor_date is None:
            raise ValueError("cycle_anchor_date is required for FIXED_DAYS")

        minimum_retention = 31 if self.cycle_mode == "CALENDAR_MONTH" else self.cycle_length_days
        if self.observation_retention_days < minimum_retention:
            raise ValueError(
                "observation_retention_days cannot be shorter than the configured cycle"
            )
        return self


class OpportunityPolicyUpdate(OpportunityPolicyFields):
    expected_version: int = Field(ge=1)


class OpportunityPolicyPreviewRequest(OpportunityPolicyFields):
    pass


class OpportunityCycleSummary(BaseModel):
    id: str
    label: str
    period_start: datetime
    period_end: datetime
    status: str
    timezone: str
    policy_version: int | None = None


class OpportunityMaintenanceStatus(BaseModel):
    last_retention_run_at: datetime | None = None
    last_cycle_close_check_at: datetime | None = None
    last_observation_cleanup_at: datetime | None = None


class OpportunityPolicyRead(OpportunityPolicyFields):
    id: str
    version: int
    updated_at: datetime
    updated_by: str | None = None
    current_cycle: OpportunityCycleSummary | None = None
    next_cycle_start: datetime | None = None
    maintenance: OpportunityMaintenanceStatus = Field(default_factory=OpportunityMaintenanceStatus)


class OpportunityPolicyPreview(BaseModel):
    treated_eligible: int
    rejected_eligible: int
    resolved_externally_eligible: int
    open_eligible: int
    observations_eligible_for_purge: int
    overdue_cycles_awaiting_close: int
    current_cycle: OpportunityCycleSummary | None = None
    warnings: list[str] = Field(default_factory=list)
