from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScanCreate(BaseModel):
    account_id: int


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: int
    status: str
    trigger: str
    started_at: datetime | None
    completed_at: datetime | None
    findings_count: int
    error: str | None
    created_at: datetime
