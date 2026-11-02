from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus
from app.schemas.job import JobRead


class FileUploadItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    status: Literal["accepted", "rejected"]
    document_id: Optional[uuid.UUID] = None
    job_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None


class BatchUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[FileUploadItemResult]
    accepted_count: int
    rejected_count: int


class ParseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_count: int
    table_count: int
    ocr_used: bool
    metadata: dict[str, Any]
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    original_filename: str
    content_type: str
    file_ext: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    error: Optional[str] = None
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DocumentDetailRead(DocumentRead):
    latest_job: Optional[JobRead] = None
    parse_summary: Optional[ParseSummary] = None
