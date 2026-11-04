from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus, ReviewStatus
from app.schemas.job import JobRead
from app.schemas.user import UserSummary


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


class UploadPolicy(BaseModel):
    """Server-side upload limits, exposed so clients never hard-code them."""

    model_config = ConfigDict(extra="forbid")

    max_upload_mb: int
    max_upload_bytes: int
    allowed_extensions: list[str]
    accepted_content_types: list[str]


class ParseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_count: int
    table_count: int
    ocr_used: bool
    metadata: dict[str, Any]
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    created_at: datetime


class InvoiceLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    line_no: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None


class ExtractedInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    document_id: uuid.UUID
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)
    line_items: list[InvoiceLineItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ValidationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    document_id: uuid.UUID
    validation_code: str
    field_name: Optional[str] = None
    severity: str
    message: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    status: str
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
    review_status: Optional[ReviewStatus] = None
    error: Optional[str] = None
    uploaded_by: uuid.UUID
    uploader: UserSummary
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class DocumentDetailRead(DocumentRead):
    latest_job: Optional[JobRead] = None
    processing_jobs: list[JobRead] = Field(default_factory=list)
    parse_summary: Optional[ParseSummary] = None
    extracted_invoice: Optional[ExtractedInvoiceRead] = None
    validation_results: list[ValidationResultRead] = Field(default_factory=list)
