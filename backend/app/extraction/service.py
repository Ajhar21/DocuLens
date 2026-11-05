from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.base import LLMParseError, LLMProvider, LLMResult, PermanentAIError
from app.ai.registry import get_llm_provider
from app.core.config import settings
from app.extraction.normalizer import (
    normalize_currency,
    normalize_date,
    normalize_decimal,
)
from app.extraction.prompts import PROMPT_VERSION
from app.extraction.schemas import RawInvoiceLLM
from app.models.document import Document
from app.models.extraction import (
    DocumentCorrection,
    ExtractedInvoice,
    InvoiceLineItem,
)
from app.models.parse_result import DocumentParseResult


@dataclass(frozen=True)
class ExtractionInputBundle:
    text: str
    truncated: bool
    original_char_count: int
    sent_char_count: int
    ocr_confidence_avg: Optional[float]
    ocr_confidence_min: Optional[float]


def _serialize_spreadsheet_tables(tables: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for idx, table in enumerate(tables):
        sheet_name = str(table.get("name") or f"Sheet_{idx + 1}").strip()
        columns = [str(col) for col in (table.get("columns") or [])]
        rows = table.get("rows") or []

        lines: list[str] = [f"Sheet: {sheet_name}"]
        if columns:
            lines.append("\t".join(columns))
        for row in rows:
            if isinstance(row, list):
                lines.append("\t".join("" if cell is None else str(cell) for cell in row))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _serialize_document_pages(pages: list[dict[str, Any]]) -> str:
    sorted_pages = sorted(
        pages,
        key=lambda p: int(p.get("page_number", 0) or 0),
    )
    blocks: list[str] = []
    for idx, page in enumerate(sorted_pages):
        page_num = int(page.get("page_number") or (idx + 1))
        page_text = str(page.get("text") or "").strip()
        blocks.append(f"--- [PAGE {page_num}] ---\n{page_text}")
    return "\n\n".join(blocks)


def build_extraction_input(
    parse_result: DocumentParseResult,
    max_chars: Optional[int] = None,
) -> ExtractionInputBundle:
    limit = max_chars if max_chars is not None else settings.LLM_MAX_INPUT_CHARS

    pages = parse_result.pages if isinstance(parse_result.pages, list) else []
    tables = parse_result.tables if isinstance(parse_result.tables, list) else []
    meta = parse_result.doc_metadata if isinstance(parse_result.doc_metadata, dict) else {}
    doc_format = str(meta.get("format") or "").lower()

    # Compute average and minimum OCR confidence across pages when present
    confidences: list[float] = []
    for p in pages:
        if isinstance(p, dict) and p.get("ocr_confidence") is not None:
            try:
                confidences.append(float(p["ocr_confidence"]))
            except (TypeError, ValueError):
                pass

    ocr_avg: Optional[float] = (
        round(sum(confidences) / len(confidences), 6) if confidences else None
    )
    ocr_min: Optional[float] = round(min(confidences), 6) if confidences else None

    if doc_format in ("csv", "xlsx") or (tables and not pages):
        full_text = _serialize_spreadsheet_tables(tables)
        if not full_text.strip() and pages:
            full_text = _serialize_document_pages(pages)
    else:
        full_text = _serialize_document_pages(pages)

    original_len = len(full_text)
    if original_len > limit:
        sent_text = full_text[:limit]
        truncated = True
    else:
        sent_text = full_text
        truncated = False

    return ExtractionInputBundle(
        text=sent_text,
        truncated=truncated,
        original_char_count=original_len,
        sent_char_count=len(sent_text),
        ocr_confidence_avg=ocr_avg,
        ocr_confidence_min=ocr_min,
    )


def _persist_failed_parse_metadata(
    session: Session,
    document_id: uuid.UUID,
    metadata_payload: dict[str, Any],
) -> None:
    """Persist raw LLM output in extraction_metadata when parse/repair fails so raw output is never lost."""
    existing = session.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == document_id)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is not None:
        merged_meta = dict(existing.extraction_metadata or {})
        merged_meta["last_failed_attempt"] = metadata_payload
        existing.extraction_metadata = merged_meta
        existing.updated_at = now
    else:
        invoice_row = ExtractedInvoice(
            document_id=document_id,
            extraction_metadata=metadata_payload,
            created_at=now,
            updated_at=now,
        )
        session.add(invoice_row)
    session.commit()


def run_invoice_extraction(
    session: Session,
    document_id: uuid.UUID,
    llm_provider: Optional[LLMProvider] = None,
    stage_callback: Optional[Callable[[str], None]] = None,
) -> ExtractedInvoice:
    """Extract, normalize, and persist invoice data for a parsed document."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise PermanentAIError(f"Document {document_id} not found")

    # Guard: never overwrite extracted invoice if human corrections exist for this document
    existing_correction_id = session.execute(
        select(DocumentCorrection.id)
        .where(DocumentCorrection.document_id == document_id)
        .limit(1)
    ).scalar_one_or_none()
    if existing_correction_id is not None:
        raise PermanentAIError(
            f"Refusing to overwrite extracted values: human corrections already exist for document {document_id}"
        )

    parse_result = session.execute(
        select(DocumentParseResult).where(DocumentParseResult.document_id == document_id)
    ).scalar_one_or_none()
    if parse_result is None:
        raise PermanentAIError(
            f"Cannot run extraction: no parse result found for document {document_id}"
        )

    input_bundle = build_extraction_input(parse_result)
    if not input_bundle.text.strip():
        raise PermanentAIError(
            f"Cannot run extraction: parsed text is empty for document {document_id}"
        )

    provider = llm_provider or get_llm_provider()

    if stage_callback:
        stage_callback("extracting")

    repair_retry_used = False
    initial_raw_output: Optional[str] = None
    initial_parse_error: Optional[str] = None

    try:
        llm_result: LLMResult = provider.extract_invoice(input_bundle.text)
    except LLMParseError as first_err:
        repair_retry_used = True
        initial_raw_output = first_err.raw_text
        initial_parse_error = str(first_err)
        try:
            llm_result = provider.extract_invoice(
                input_bundle.text,
                repair_error=str(first_err),
                previous_raw_output=first_err.raw_text,
            )
        except LLMParseError as second_err:
            failed_meta = {
                "status": "parse_failed",
                "prompt_version": PROMPT_VERSION,
                "model_name": provider.model_name,
                "repair_retry_used": True,
                "initial_raw_llm_output": initial_raw_output,
                "initial_parse_error": initial_parse_error,
                "raw_llm_output": second_err.raw_text,
                "parse_error": str(second_err),
                "truncated": input_bundle.truncated,
                "original_char_count": input_bundle.original_char_count,
                "sent_char_count": input_bundle.sent_char_count,
                "ocr_confidence_avg": input_bundle.ocr_confidence_avg,
                "ocr_confidence_min": input_bundle.ocr_confidence_min,
            }
            _persist_failed_parse_metadata(session, document_id, failed_meta)
            raise LLMParseError(
                f"LLM output failed schema validation after 1 repair retry: {second_err}",
                raw_text=second_err.raw_text,
                model_name=second_err.model_name,
                token_usage=second_err.token_usage,
            ) from second_err

    if stage_callback:
        stage_callback("normalizing")

    raw_invoice = RawInvoiceLLM.model_validate(llm_result.parsed)

    invoice_number = (raw_invoice.invoice_number or "").strip() or None
    supplier_name = (raw_invoice.supplier_name or "").strip() or None
    customer_name = (raw_invoice.customer_name or "").strip() or None

    date_norm = normalize_date(raw_invoice.invoice_date)
    subtotal_dec = normalize_decimal(raw_invoice.subtotal, scale=4)
    tax_dec = normalize_decimal(raw_invoice.tax, scale=4)
    total_dec = normalize_decimal(raw_invoice.total, scale=4)
    discount_dec = normalize_decimal(raw_invoice.discount, scale=4)
    shipping_dec = normalize_decimal(raw_invoice.shipping, scale=4)

    fallback_amounts = [
        raw_invoice.total,
        raw_invoice.subtotal,
        raw_invoice.tax,
        raw_invoice.discount,
        raw_invoice.shipping,
        *(li.amount for li in raw_invoice.line_items),
        *(li.unit_price for li in raw_invoice.line_items),
    ]
    currency_norm = normalize_currency(
        raw_invoice.currency,
        fallback_amount_strings=fallback_amounts,
    )

    extraction_metadata: dict[str, Any] = {
        "raw_llm_output": llm_result.raw_text,
        "parsed_llm_json": llm_result.parsed,
        "prompt_version": PROMPT_VERSION,
        "model_name": llm_result.model_name,
        "token_usage": llm_result.token_usage,
        "repair_retry_used": repair_retry_used,
        "truncated": input_bundle.truncated,
        "original_char_count": input_bundle.original_char_count,
        "sent_char_count": input_bundle.sent_char_count,
        "ocr_confidence_avg": input_bundle.ocr_confidence_avg,
        "ocr_confidence_min": input_bundle.ocr_confidence_min,
        "discount": str(discount_dec) if discount_dec is not None else None,
        "shipping": str(shipping_dec) if shipping_dec is not None else None,
        "raw_discount": raw_invoice.discount,
        "raw_shipping": raw_invoice.shipping,
        "self_reported_uncalibrated": raw_invoice.self_reported_confidence,
        "normalization": {
            "date_ambiguous": date_norm.is_ambiguous,
            "date_raw": date_norm.raw_value,
            "date_parse_failed": date_norm.parse_failed,
            "currency_ambiguous": currency_norm.is_ambiguous,
            "currency_raw": currency_norm.raw_value,
        },
    }
    if repair_retry_used:
        extraction_metadata["initial_raw_llm_output"] = initial_raw_output
        extraction_metadata["initial_parse_error"] = initial_parse_error

    now = datetime.now(timezone.utc)
    invoice_row = session.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == document_id)
    ).scalar_one_or_none()

    if invoice_row is None:
        invoice_row = ExtractedInvoice(
            document_id=document_id,
            invoice_number=invoice_number,
            invoice_date=date_norm.value,
            supplier_name=supplier_name,
            customer_name=customer_name,
            subtotal=subtotal_dec,
            tax=tax_dec,
            total=total_dec,
            currency=currency_norm.value,
            extraction_metadata=extraction_metadata,
            created_at=now,
            updated_at=now,
        )
        session.add(invoice_row)
        session.flush()
    else:
        invoice_row.invoice_number = invoice_number
        invoice_row.invoice_date = date_norm.value
        invoice_row.supplier_name = supplier_name
        invoice_row.customer_name = customer_name
        invoice_row.subtotal = subtotal_dec
        invoice_row.tax = tax_dec
        invoice_row.total = total_dec
        invoice_row.currency = currency_norm.value
        invoice_row.extraction_metadata = extraction_metadata
        invoice_row.updated_at = now
        session.execute(
            delete(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice_row.id)
        )
        session.flush()

    for idx, raw_item in enumerate(raw_invoice.line_items, start=1):
        desc = (raw_item.description or "").strip() or None
        qty_dec = normalize_decimal(raw_item.quantity, scale=6)
        unit_price_dec = normalize_decimal(raw_item.unit_price, scale=4)
        amount_dec = normalize_decimal(raw_item.amount, scale=4)

        line_item = InvoiceLineItem(
            invoice_id=invoice_row.id,
            line_no=idx,
            description=desc,
            quantity=qty_dec,
            unit_price=unit_price_dec,
            amount=amount_dec,
        )
        session.add(line_item)

    session.flush()
    session.refresh(invoice_row)
    return invoice_row

