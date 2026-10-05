from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.collection_errors import sanitize_collection_error


class ScanCreate(BaseModel):
    account_id: int


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: int | None
    status: str
    trigger: str
    started_at: datetime | None
    completed_at: datetime | None
    findings_count: int
    error: str | None
    created_at: datetime

    @field_validator("error", mode="before")
    @classmethod
    def safe_error(cls, value):
        return sanitize_collection_error(value)
