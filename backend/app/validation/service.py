from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings as default_settings
from app.models.document import Document, ReviewStatus
from app.models.extraction import ExtractedInvoice, InvoiceLineItem
from app.models.validation import (
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from app.validation.rules import (
    ValidationItem,
    build_duplicate_key,
    evaluate_invoice_validation,
)


def find_duplicate_document_ids(
    session: Session,
    invoice: ExtractedInvoice,
) -> list[uuid.UUID]:
    """Query extracted_invoices excluding current document for an exact match on normalized key."""
    target_key = build_duplicate_key(
        supplier_name=invoice.supplier_name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        total=Decimal(invoice.total) if invoice.total is not None else None,
    )
    if target_key is None:
        return []

    target_supplier, target_inv_num, target_date, target_total = target_key

    candidates = (
        session.execute(
            select(ExtractedInvoice)
            .where(
                ExtractedInvoice.document_id != invoice.document_id,
                ExtractedInvoice.invoice_date == target_date,
                ExtractedInvoice.total == target_total,
                ExtractedInvoice.supplier_name.is_not(None),
                ExtractedInvoice.invoice_number.is_not(None),
            )
            .order_by(ExtractedInvoice.created_at.asc(), ExtractedInvoice.id.asc())
        )
        .scalars()
        .all()
    )

    matching_doc_ids: list[uuid.UUID] = []
    for cand in candidates:
        cand_key = build_duplicate_key(
            supplier_name=cand.supplier_name,
            invoice_number=cand.invoice_number,
            invoice_date=cand.invoice_date,
            total=Decimal(cand.total) if cand.total is not None else None,
        )
        if cand_key == target_key:
            matching_doc_ids.append(cand.document_id)

    return matching_doc_ids


def determine_review_status(validation_items: list[ValidationItem]) -> str:
    """Return ReviewStatus value based on validation results:
    - Empty validation items => pending (not yet evaluated)
    - Any FAILED item (ERROR, WARNING, INFO, duplicate, etc.) => needs_review
    - Any SKIPPED item of ERROR/WARNING severity (missing prerequisite math field) => needs_review
    - Otherwise (all rules PASSED, or only non-applicable INFO checks like OCR on native text were SKIPPED) => not_required
    """
    if not validation_items:
        return ReviewStatus.PENDING.value

    has_any_failed = any(
        item.status == ValidationStatus.FAILED.value
        for item in validation_items
    )
    if has_any_failed:
        return ReviewStatus.NEEDS_REVIEW.value

    has_skipped_critical = any(
        item.status == ValidationStatus.SKIPPED.value
        and item.severity in (ValidationSeverity.ERROR.value, ValidationSeverity.WARNING.value)
        for item in validation_items
    )
    if has_skipped_critical:
        return ReviewStatus.NEEDS_REVIEW.value

    return ReviewStatus.NOT_REQUIRED.value


def sync_legacy_pending_review_statuses(session: Session) -> int:
    """Upgrade parsed documents stuck in 'pending' review_status whose existing validation_results all passed."""
    has_validations = (
        select(ValidationResult.id)
        .where(ValidationResult.document_id == Document.id)
        .exists()
    )
    has_blocking_issue = (
        select(ValidationResult.id)
        .where(
            ValidationResult.document_id == Document.id,
            (ValidationResult.status == ValidationStatus.FAILED.value)
            | (
                (ValidationResult.status == ValidationStatus.SKIPPED.value)
                & ValidationResult.severity.in_(
                    [ValidationSeverity.ERROR.value, ValidationSeverity.WARNING.value]
                )
            ),
        )
        .exists()
    )
    stmt = (
        update(Document)
        .where(
            Document.status == "parsed",
            Document.review_status == ReviewStatus.PENDING.value,
            has_validations,
            ~has_blocking_issue,
        )
        .values(review_status=ReviewStatus.NOT_REQUIRED.value)
    )
    result = session.execute(stmt)
    if result.rowcount:
        session.commit()
    return int(result.rowcount or 0)


def run_invoice_validation(
    session: Session,
    document_id: uuid.UUID,
    app_settings: Optional[Settings] = None,
    reference_date: Optional[date] = None,
    update_review_status: bool = True,
) -> list[ValidationResult]:
    """Run deterministic financial validation + duplicate check and replace validation_results in one transaction."""
    cfg = app_settings or default_settings

    invoice = session.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == document_id)
    ).scalar_one_or_none()
    if invoice is None:
        raise ValueError(f"Cannot run validation: no extracted invoice found for document {document_id}")

    line_items = list(
        session.execute(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == invoice.id)
            .order_by(InvoiceLineItem.line_no.asc())
        )
        .scalars()
        .all()
    )

    duplicate_doc_ids = find_duplicate_document_ids(session, invoice)

    items = evaluate_invoice_validation(
        invoice=invoice,
        line_items=line_items,
        app_settings=cfg,
        duplicate_document_ids=duplicate_doc_ids,
        reference_date=reference_date,
    )

    session.execute(
        delete(ValidationResult).where(ValidationResult.document_id == document_id)
    )

    now = datetime.now(timezone.utc)
    persisted: list[ValidationResult] = []
    for item in items:
        row = ValidationResult(
            document_id=document_id,
            validation_code=item.validation_code,
            field_name=item.field_name,
            severity=item.severity,
            message=item.message,
            expected_value=item.expected_value,
            actual_value=item.actual_value,
            status=item.status,
            created_at=now,
        )
        session.add(row)
        persisted.append(row)

    doc = session.get(Document, document_id)
    if doc is not None:
        if update_review_status:
            doc.review_status = determine_review_status(items)
        doc.updated_at = now

    session.flush()
    return persisted

