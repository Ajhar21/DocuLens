from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ExtractedInvoiceRead, ValidationResultRead
from app.schemas.user import UserSummary


class DocumentCorrectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    document_id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None
    field_name: str
    original_value: Optional[str] = None
    corrected_value: Optional[str] = None
    corrected_by: uuid.UUID
    correction_reason: Optional[str] = None
    created_at: datetime


class CorrectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    corrected_value: Optional[Any] = None
    reason: Optional[str] = None


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    original_filename: str
    content_type: str
    file_ext: str
    size_bytes: int
    status: str
    review_status: str
    uploaded_by: uuid.UUID
    uploader: UserSummary
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    error_count: int = 0
    warning_count: int = 0


class ReviewQueuePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReviewQueueItem]
    total: int
    limit: int
    offset: int


class ReviewDetailRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    original_filename: str
    status: str
    review_status: str
    uploaded_by: uuid.UUID
    uploader: UserSummary
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    extracted_invoice: Optional[ExtractedInvoiceRead] = None
    original_llm_output: Optional[dict[str, Any]] = None
    validation_results: list[ValidationResultRead] = Field(default_factory=list)
    corrections: list[DocumentCorrectionRead] = Field(default_factory=list)


class RejectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, description="Reason for rejection")


class ApprovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: Optional[str] = None

