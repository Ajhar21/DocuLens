from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RawLineItemLLM(BaseModel):
    """LLM response schema for a single invoice line item (all numbers as exact strings)."""

    model_config = ConfigDict(extra="ignore")

    description: Optional[str] = Field(
        default=None,
        description="Literal line item description as printed, or null if absent",
    )
    quantity: Optional[str] = Field(
        default=None,
        description="Exact quantity string as printed (e.g. '2', '1.50'), or null if absent",
    )
    unit_price: Optional[str] = Field(
        default=None,
        description="Exact unit price string as printed (e.g. '100.00', '$1,250.50'), or null if absent",
    )
    amount: Optional[str] = Field(
        default=None,
        description="Exact line total amount string as printed, or null if absent",
    )


class RawInvoiceLLM(BaseModel):
    """LLM response schema for extracted invoice fields (monetary/quantity/date values as strings)."""

    model_config = ConfigDict(extra="ignore")

    invoice_number: Optional[str] = Field(
        default=None,
        description="Exact invoice number string as printed, or null if absent",
    )
    invoice_date: Optional[str] = Field(
        default=None,
        description="Exact invoice date string as printed (do not guess ambiguous dates), or null if absent",
    )
    supplier_name: Optional[str] = Field(
        default=None,
        description="Supplier / vendor name literally printed on the invoice, or null if absent",
    )
    customer_name: Optional[str] = Field(
        default=None,
        description="Customer / bill-to name literally printed on the invoice, or null if absent",
    )
    subtotal: Optional[str] = Field(
        default=None,
        description="Exact subtotal string as printed, or null if absent",
    )
    tax: Optional[str] = Field(
        default=None,
        description="Exact tax / VAT amount string as printed, or null if absent",
    )
    total: Optional[str] = Field(
        default=None,
        description="Exact grand total amount string as printed, or null if absent",
    )
    currency: Optional[str] = Field(
        default=None,
        description="Printed currency code or symbol (e.g. 'USD', 'EUR', '$', '€', '£', '৳'), or null if absent",
    )
    discount: Optional[str] = Field(
        default=None,
        description="Exact discount amount string if printed on the invoice, or null if absent",
    )
    shipping: Optional[str] = Field(
        default=None,
        description="Exact shipping / freight / handling amount string if printed, or null if absent",
    )
    self_reported_confidence: Optional[float] = Field(
        default=None,
        description="Optional uncalibrated self-reported confidence score between 0.0 and 1.0",
    )
    line_items: list[RawLineItemLLM] = Field(
        default_factory=list,
        description="Ordered list of line items literally present in the invoice",
    )

