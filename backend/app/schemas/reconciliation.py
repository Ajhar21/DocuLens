from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict


class ReconcilePdfPdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id_a: uuid.UUID
    document_id_b: uuid.UUID
    notes: Optional[str] = None


class ReconcilePdfExcelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id_a: uuid.UUID
    document_id_b: uuid.UUID
    excel_sheet_name: Optional[str] = None
    column_mapping: Optional[dict[str, str]] = None
    notes: Optional[str] = None


class ReconciliationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    entity_type: str
    field_name: str
    source_a_value: Optional[str] = None
    source_b_value: Optional[str] = None
    match_status: str
    absolute_difference: Optional[Decimal] = None
    percentage_difference: Optional[Decimal] = None
    created_at: datetime


class ReconciliationJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    initiated_by: uuid.UUID
    document_id_a: uuid.UUID
    document_id_b: uuid.UUID
    reconciliation_type: str
    overall_status: str
    discrepancy_count: int
    initiated_at: datetime
    completed_at: datetime
    notes: Optional[str] = None


class ReconciliationJobDetail(ReconciliationJobSummary):
    results: list[ReconciliationResultRead]


class ReconciliationJobPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    page_size: int
    total: int
    total_pages: int


class ReconciliationJobPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReconciliationJobSummary]
    pagination: ReconciliationJobPagination


class ExcelSheetsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    sheet_names: list[str]

