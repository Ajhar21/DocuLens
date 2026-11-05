"""Manual verification script for Day 2: takes a document_id, runs real Gemini extraction,
deterministic validation, and Gemini embeddings, and prints a structured summary.

Usage (from backend directory):
    python -m scripts.smoke_day2 <document_id>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import uuid

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.embeddings.service import run_document_embedding
from app.extraction.service import run_invoice_extraction
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.extraction import InvoiceLineItem
from app.validation.service import run_invoice_validation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Day 2 extraction, validation, and embedding on a parsed document."
    )
    parser.add_argument(
        "document_id",
        type=uuid.UUID,
        help="UUID of the parsed document in the database",
    )
    args = parser.parse_args()
    doc_id: uuid.UUID = args.document_id

    with SessionLocal() as session:
        doc = session.get(Document, doc_id)
        if doc is None:
            print(f"[ERROR] Document {doc_id} not found in database.")
            sys.exit(1)

        print(f"=== DocuLens Day 2 Smoke Run ===")
        print(f"Document ID : {doc.id}")
        print(f"Filename    : {doc.original_filename} ({doc.file_ext})")
        print(f"Status      : {doc.status} | Review Status: {doc.review_status}")

        print("\n--- 1. Running Gemini Invoice Extraction ---")
        invoice = run_invoice_extraction(session, document_id=doc_id)
        session.commit()
        session.refresh(invoice)

        line_items = list(
            session.execute(
                select(InvoiceLineItem)
                .where(InvoiceLineItem.invoice_id == invoice.id)
                .order_by(InvoiceLineItem.line_no.asc())
            )
            .scalars()
            .all()
        )
        print(f"Invoice Number : {invoice.invoice_number}")
        print(f"Invoice Date   : {invoice.invoice_date}")
        print(f"Supplier Name  : {invoice.supplier_name}")
        print(f"Customer Name  : {invoice.customer_name}")
        print(f"Currency       : {invoice.currency}")
        print(f"Subtotal       : {invoice.subtotal}")
        print(f"Tax            : {invoice.tax}")
        print(f"Total          : {invoice.total}")
        print(f"Discount (meta): {invoice.extraction_metadata.get('discount')}")
        print(f"Shipping (meta): {invoice.extraction_metadata.get('shipping')}")
        print(f"OCR Avg / Min  : {invoice.extraction_metadata.get('ocr_confidence_avg')} / {invoice.extraction_metadata.get('ocr_confidence_min')}")
        print(f"Line Items ({len(line_items)}):")
        for li in line_items:
            print(
                f"  [{li.line_no}] {li.description!r} | qty={li.quantity} | unit_price={li.unit_price} | amount={li.amount}"
            )

        print("\n--- 2. Running Deterministic Financial Validation ---")
        validations = run_invoice_validation(session, document_id=doc_id)
        session.commit()
        session.refresh(doc)
        for v in validations:
            print(
                f"  [{v.status:<7}] [{v.severity:<7}] {v.validation_code:<28} "
                f"field={v.field_name} expected={v.expected_value} actual={v.actual_value} | {v.message}"
            )
        print(f"Updated Document Review Status: {doc.review_status}")

        print("\n--- 3. Running Chunking & Gemini Embeddings ---")
        chunks = run_document_embedding(session, document_id=doc_id)
        session.commit()

        dims = session.execute(
            select(func.vector_dims(DocumentChunk.embedding))
            .where(DocumentChunk.document_id == doc_id)
            .limit(1)
        ).scalar_one_or_none()
        print(f"Chunks Persisted : {len(chunks)}")
        if chunks:
            print(f"Embedding Model  : {chunks[0].embedding_model}")
            print(f"Vector Dimension : {dims}")
            print(f"First Chunk Page : {chunks[0].page_number}")
            print(f"First Chunk Preview: {chunks[0].content[:160]!r}...")

        print("\n=== Smoke Run Completed Successfully ===")


if __name__ == "__main__":
    main()

