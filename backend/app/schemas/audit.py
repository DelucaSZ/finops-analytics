from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditActorRead(BaseModel):
    id: str | None = None
    name: str | None = None
    email: str | None = None


class AuditEntityRead(BaseModel):
    type: str
    id: str | None = None
    label: str | None = None


class AuditEventRead(BaseModel):
    id: str
    event_kind: str
    created_at: datetime
    actor: AuditActorRead
    module: str
    action: str
    entity: AuditEntityRead
    source: str
    reason: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None

    # Compatibility fields retained for clients of the pre-24.2 SecurityEvent
    # response. New clients should prefer the nested actor/entity contract.
    actor_id: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    user_email: str | None = None


class AuditPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int
