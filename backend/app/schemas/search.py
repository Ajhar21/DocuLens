from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict


class SearchDocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    original_filename: str
    status: str
    review_status: str
    created_at: datetime
    uploaded_by: uuid.UUID


class SearchInvoiceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    invoice_date: Optional[date] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: SearchDocumentSummary
    invoice: Optional[SearchInvoiceSummary] = None
    snippet: Optional[str] = None
    score: float
    match_type: Literal["KEYWORD", "SEMANTIC", "BOTH"]


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    mode: str
    total_hits: int
    hits: list[SearchHit]

