from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str | None
    provider: str
    account_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    resources_analyzed: int
    opportunities_found: int
    analyzer_version: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
