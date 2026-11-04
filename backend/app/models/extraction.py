from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class ExtractedInvoice(Base):
    __tablename__ = "extracted_invoices"
    __table_args__ = (
        Index("ix_extracted_invoices_invoice_number", "invoice_number"),
        Index("ix_extracted_invoices_invoice_date", "invoice_date"),
        Index("ix_extracted_invoices_total", "total"),
        Index(
            "ix_extracted_invoices_supplier_lower",
            sa.text("lower(supplier_name)"),
        ),
        Index(
            "ix_extracted_invoices_supplier_trgm",
            "supplier_name",
            postgresql_using="gin",
            postgresql_ops={"supplier_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    invoice_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)
    tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)
    total: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    document: Mapped[Document] = relationship("Document", back_populates="extracted_invoice")
    line_items: Mapped[List[InvoiceLineItem]] = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.line_no",
    )
    corrections: Mapped[List[DocumentCorrection]] = relationship(
        "DocumentCorrection",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        Index("ix_invoice_line_items_invoice_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extracted_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)

    invoice: Mapped[ExtractedInvoice] = relationship("ExtractedInvoice", back_populates="line_items")


class DocumentCorrection(Base):
    __tablename__ = "document_corrections"
    __table_args__ = (
        Index("ix_document_corrections_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extracted_invoices.id", ondelete="CASCADE"),
        nullable=True,
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    correction_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    document: Mapped[Document] = relationship("Document", back_populates="corrections")
    invoice: Mapped[Optional[ExtractedInvoice]] = relationship("ExtractedInvoice", back_populates="corrections")

