from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict


class ActorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str
    role: str


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    event_type: str
    actor: Union[ActorSummary, Literal["system"]]
    details: dict[str, Any]


class DocumentHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    events: list[TimelineEvent]


class AuditLogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    created_at: datetime


class AuditLogPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    page_size: int
    total: int
    total_pages: int


class AuditLogPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditLogItem]
    pagination: AuditLogPagination

