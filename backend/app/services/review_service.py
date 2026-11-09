"""Human review and correction domain service.

Enforces:
- Header-only field corrections (invoice_number, invoice_date, supplier_name, customer_name, subtotal, tax, total, currency).
- Line-item editing is out of scope (rejected with 422).
- Pure normalizers for Decimal, date, and currency parsing.
- SELECT ... FOR UPDATE row-locking on document during correction/approve/reject.
- Review status transitions with 409 on conflict.
- Editing an approved document returns 409 (must be rejected to reopen).
- Transactional re-validation preserving review_status='corrected'.
- Preserving original LLM output untouched in extraction_metadata.
- DocumentCorrection history tracking.
- Centralized audit logging.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.responses import ErrorDetail
from app.extraction.normalizer import (
    normalize_currency,
    normalize_date,
    normalize_decimal,
)
from app.models.document import Document
from app.models.extraction import DocumentCorrection, ExtractedInvoice
from app.models.user import User
from app.repositories import document_repo, review_repo
from app.schemas.document import ExtractedInvoiceRead, ValidationResultRead
from app.schemas.review import (
    CorrectionItem,
    DocumentCorrectionRead,
    ReviewDetailRead,
    ReviewQueueItem,
    ReviewQueuePage,
)
from app.services.audit_service import AuditService
from app.validation.service import (
    run_invoice_validation,
    sync_legacy_pending_review_statuses,
)

ALLOWED_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "invoice_number",
        "invoice_date",
        "supplier_name",
        "customer_name",
        "subtotal",
        "tax",
        "total",
        "currency",
    }
)

_VALID_APPROVE_STATES: frozenset[str] = frozenset(
    {"pending", "needs_review", "in_review", "corrected", "not_required"}
)

_VALID_REJECT_STATES: frozenset[str] = frozenset(
    {"pending", "needs_review", "in_review", "corrected", "approved", "not_required"}
)

_REVIEW_STATUS_MAP: dict[str, str] = {
    "pending": "pending",
    "needs_review": "needs_review",
    "in_review": "in_review",
    "corrected": "corrected",
    "approved": "approved",
    "rejected": "rejected",
    "not_required": "not_required",
}


def normalize_review_filter(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    val = raw.strip().lower()
    if not val:
        return None
    mapped = _REVIEW_STATUS_MAP.get(val)
    if mapped is None:
        raise AppError(
            422,
            "validation_error",
            f"Invalid review_status filter '{raw}'",
            details=[ErrorDetail(field="review_status", message=f"Invalid review_status filter '{raw}'")],
        )
    return mapped


def list_reviews(
    db: Session,
    current_user: User,
    *,
    limit: int,
    offset: int,
    review_status_filter: Optional[str] = None,
) -> ReviewQueuePage:
    norm_filter = normalize_review_filter(review_status_filter)
    sync_legacy_pending_review_statuses(db)
    items_raw, total = review_repo.list_review_queue(
        db,
        current_user,
        limit=limit,
        offset=offset,
        review_status_filter=norm_filter,
    )
    items = [ReviewQueueItem.model_validate(it) for it in items_raw]
    return ReviewQueuePage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


def get_review_detail(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> ReviewDetailRead:
    doc = review_repo.get_review_document(db, document_id, current_user)
    if doc is None:
        raise NotFoundError("Document not found")

    invoice_row = document_repo.get_document_invoice(db, doc.id)
    validation_rows = document_repo.get_document_validations(db, doc.id)
    corrections_rows = review_repo.get_corrections(db, doc.id)

    raw_llm: Optional[dict[str, Any]] = None
    if invoice_row is not None and isinstance(invoice_row.extraction_metadata, dict):
        raw_llm = invoice_row.extraction_metadata.get("raw_llm_output") or invoice_row.extraction_metadata

    return ReviewDetailRead(
        document_id=doc.id,
        original_filename=doc.original_filename,
        status=doc.status,
        review_status=doc.review_status,
        uploaded_by=doc.uploaded_by,
        uploader=doc.uploader,
        reviewed_by=doc.reviewed_by,
        reviewed_at=doc.reviewed_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        extracted_invoice=(
            ExtractedInvoiceRead.model_validate(invoice_row)
            if invoice_row is not None
            else None
        ),
        original_llm_output=raw_llm if isinstance(raw_llm, dict) else None,
        validation_results=[ValidationResultRead.model_validate(v) for v in validation_rows],
        corrections=[DocumentCorrectionRead.model_validate(c) for c in corrections_rows],
    )


def _normalize_correction_value(field_name: str, raw_value: Any) -> Any:
    if raw_value is None or raw_value == "":
        return None

    if field_name in ("subtotal", "tax", "total"):
        norm_dec = normalize_decimal(raw_value, scale=4)
        if norm_dec is None and raw_value is not None:
            raise AppError(
                422,
                "validation_error",
                f"Invalid monetary value '{raw_value}' for field '{field_name}'",
                details=[ErrorDetail(field=field_name, message="Must be a valid decimal amount")],
            )
        return norm_dec

    if field_name == "invoice_date":
        norm_dt = normalize_date(raw_value)
        if norm_dt.is_ambiguous:
            raise AppError(
                422,
                "validation_error",
                f"Ambiguous date '{raw_value}'. Please provide ISO YYYY-MM-DD or unambiguous format.",
                details=[ErrorDetail(field=field_name, message="Ambiguous date format")],
            )
        if norm_dt.parse_failed or norm_dt.value is None:
            raise AppError(
                422,
                "validation_error",
                f"Invalid date format '{raw_value}' for field '{field_name}'",
                details=[ErrorDetail(field=field_name, message="Could not parse date")],
            )
        return norm_dt.value

    if field_name == "currency":
        norm_curr = normalize_currency(str(raw_value))
        if norm_curr.is_ambiguous or norm_curr.value is None:
            raise AppError(
                422,
                "validation_error",
                f"Invalid or ambiguous currency '{raw_value}'. Please provide a standard 3-letter ISO code.",
                details=[ErrorDetail(field=field_name, message="Invalid or ambiguous currency code")],
            )
        return norm_curr.value

    return str(raw_value).strip() or None


def submit_corrections(
    db: Session,
    document_id: uuid.UUID,
    corrections: list[CorrectionItem],
    actor: User,
) -> ReviewDetailRead:
    # 1. Row-lock document with SELECT ... FOR UPDATE
    doc = review_repo.get_review_document(db, document_id, actor, for_update=True)
    if doc is None:
        raise NotFoundError("Document not found")

    # 2. Status guard: editing an APPROVED document returns 409 for everyone
    if doc.review_status == "approved":
        raise ConflictError(
            "Cannot edit an approved document. A Finance Manager must reject it first to reopen."
        )

    # 3. Document must be parsed and have extracted invoice
    invoice = review_repo.get_document_invoice(db, doc.id, for_update=True)
    if invoice is None:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "conflict",
            "Cannot apply corrections: no extracted invoice exists for this document.",
        )

    now = datetime.now(timezone.utc)
    applied_corrections: list[DocumentCorrection] = []
    old_values_dict: dict[str, Any] = {}
    new_values_dict: dict[str, Any] = {}

    for item in corrections:
        field_name = item.field_name.strip()

        # Reject line-item editing or unknown fields with 422
        if field_name.lower().startswith("line_item") or field_name.lower() in ("items", "lines"):
            raise AppError(
                422,
                "validation_error",
                "Line-item editing is out of scope. Only invoice header fields are permitted.",
                details=[ErrorDetail(field=field_name, message="Line item editing is not supported")],
            )

        if field_name not in ALLOWED_EDITABLE_FIELDS:
            raise AppError(
                422,
                "validation_error",
                f"Field '{field_name}' is not editable. Allowed header fields: {sorted(ALLOWED_EDITABLE_FIELDS)}",
                details=[ErrorDetail(field=field_name, message=f"Unknown or non-editable field '{field_name}'")],
            )

        cleaned_value = _normalize_correction_value(field_name, item.corrected_value)
        current_val = getattr(invoice, field_name)

        # Skip no-op changes
        if str(current_val or "") == str(cleaned_value or ""):
            continue

        applied_corrections.append(
            DocumentCorrection(
                document_id=doc.id,
                invoice_id=invoice.id,
                field_name=field_name,
                original_value=str(current_val) if current_val is not None else None,
                corrected_value=str(cleaned_value) if cleaned_value is not None else None,
                corrected_by=actor.id,
                correction_reason=item.reason.strip() if item.reason else None,
                created_at=now,
            )
        )

        old_values_dict[field_name] = current_val
        new_values_dict[field_name] = cleaned_value

        setattr(invoice, field_name, cleaned_value)

    if applied_corrections:
        review_repo.insert_corrections(db, applied_corrections)
        invoice.updated_at = now

        # Update review_status to CORRECTED
        old_status = doc.review_status
        doc.review_status = "corrected"
        doc.updated_at = now

        # Re-run deterministic validation + duplicate detection in same transaction
        # update_review_status=False guarantees review_status stays 'corrected'
        run_invoice_validation(db, doc.id, update_review_status=False)

        AuditService.record(
            db,
            user_id=actor.id,
            action="DOCUMENT_CORRECTED",
            entity_type="DOCUMENT",
            entity_id=doc.id,
            old_values={"review_status": old_status, **old_values_dict},
            new_values={"review_status": doc.review_status, **new_values_dict},
        )
        db.commit()

    return get_review_detail(db, doc.id, actor)


def approve_document(
    db: Session,
    document_id: uuid.UUID,
    actor: User,
    notes: Optional[str] = None,
) -> ReviewDetailRead:
    doc = review_repo.get_review_document(db, document_id, actor, for_update=True)
    if doc is None:
        raise NotFoundError("Document not found")

    if doc.review_status == "approved":
        raise ConflictError("Document is already approved.")

    if doc.review_status not in _VALID_APPROVE_STATES:
        raise ConflictError(
            f"Cannot approve document with review status '{doc.review_status}'. "
            f"Allowed states: {sorted(_VALID_APPROVE_STATES)}"
        )

    now = datetime.now(timezone.utc)
    old_status = doc.review_status
    doc.review_status = "approved"
    doc.reviewed_by = actor.id
    doc.reviewed_at = now
    doc.updated_at = now

    AuditService.record(
        db,
        user_id=actor.id,
        action="DOCUMENT_APPROVED",
        entity_type="DOCUMENT",
        entity_id=doc.id,
        old_values={"review_status": old_status},
        new_values={
            "review_status": "approved",
            "reviewed_by": actor.id,
            "reviewed_at": now,
            "notes": notes,
        },
    )
    db.commit()
    return get_review_detail(db, doc.id, actor)


def reject_document(
    db: Session,
    document_id: uuid.UUID,
    reason: str,
    actor: User,
) -> ReviewDetailRead:
    cleaned_reason = (reason or "").strip()
    if not cleaned_reason:
        raise AppError(
            422,
            "validation_error",
            "A reason is required to reject a document.",
            details=[ErrorDetail(field="reason", message="Rejection reason cannot be empty")],
        )

    doc = review_repo.get_review_document(db, document_id, actor, for_update=True)
    if doc is None:
        raise NotFoundError("Document not found")

    if doc.review_status == "rejected":
        raise ConflictError("Document is already rejected.")

    if doc.review_status not in _VALID_REJECT_STATES:
        raise ConflictError(
            f"Cannot reject document with review status '{doc.review_status}'. "
            f"Allowed states: {sorted(_VALID_REJECT_STATES)}"
        )

    now = datetime.now(timezone.utc)
    old_status = doc.review_status
    doc.review_status = "rejected"
    doc.reviewed_by = actor.id
    doc.reviewed_at = now
    doc.updated_at = now

    AuditService.record(
        db,
        user_id=actor.id,
        action="DOCUMENT_REJECTED",
        entity_type="DOCUMENT",
        entity_id=doc.id,
        old_values={"review_status": old_status},
        new_values={
            "review_status": "rejected",
            "reason": cleaned_reason,
            "reviewed_by": actor.id,
            "reviewed_at": now,
        },
    )
    db.commit()
    return get_review_detail(db, doc.id, actor)

