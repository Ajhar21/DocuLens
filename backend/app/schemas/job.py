from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    document_id: uuid.UUID
    job_type: str
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
