from __future__ import annotations

from typing import Optional
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.visibility import visible_documents_filter
from app.models.document import Document
from app.models.extraction import DocumentCorrection, ExtractedInvoice
from app.models.user import User
from app.models.validation import ValidationResult, ValidationSeverity

_DEFAULT_QUEUE_STATUSES = ("pending", "needs_review", "in_review", "corrected")


def list_review_queue(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
    review_status_filter: Optional[str] = None,
) -> tuple[list[dict], int]:
    vis_clause = visible_documents_filter(user)

    # Base filter: parsed documents only
    base = select(Document).where(vis_clause, Document.status == "parsed")

    if review_status_filter is not None:
        base = base.where(Document.review_status == review_status_filter)
    else:
        base = base.where(Document.review_status.in_(_DEFAULT_QUEUE_STATUSES))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.execute(count_stmt).scalar_one())

    # Build aggregation subquery for validation issue counts
    val_subq = (
        select(
            ValidationResult.document_id,
            func.count(
                case(
                    (
                        (ValidationResult.severity == ValidationSeverity.ERROR.value)
                        & (ValidationResult.status == "FAILED"),
                        1,
                    )
                )
            ).label("error_count"),
            func.count(
                case(
                    (
                        (ValidationResult.severity == ValidationSeverity.WARNING.value)
                        & (ValidationResult.status == "FAILED"),
                        1,
                    )
                )
            ).label("warning_count"),
        )
        .group_by(ValidationResult.document_id)
        .subquery()
    )

    query = (
        select(
            Document,
            ExtractedInvoice,
            func.coalesce(val_subq.c.error_count, 0).label("error_count"),
            func.coalesce(val_subq.c.warning_count, 0).label("warning_count"),
        )
        .outerjoin(ExtractedInvoice, Document.id == ExtractedInvoice.document_id)
        .outerjoin(val_subq, Document.id == val_subq.c.document_id)
        .options(joinedload(Document.uploader))
        .where(vis_clause, Document.status == "parsed")
    )

    if review_status_filter is not None:
        query = query.where(Document.review_status == review_status_filter)
    else:
        query = query.where(Document.review_status.in_(_DEFAULT_QUEUE_STATUSES))

    query = query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit).offset(offset)
    rows = db.execute(query).all()

    items = []
    for doc, inv, err_cnt, warn_cnt in rows:
        items.append(
            {
                "id": doc.id,
                "original_filename": doc.original_filename,
                "content_type": doc.content_type,
                "file_ext": doc.file_ext,
                "size_bytes": doc.size_bytes,
                "status": doc.status,
                "review_status": doc.review_status,
                "uploaded_by": doc.uploaded_by,
                "uploader": doc.uploader,
                "reviewed_by": doc.reviewed_by,
                "reviewed_at": doc.reviewed_at,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "invoice_number": inv.invoice_number if inv else None,
                "supplier_name": inv.supplier_name if inv else None,
                "total": inv.total if inv else None,
                "currency": inv.currency if inv else None,
                "error_count": int(err_cnt),
                "warning_count": int(warn_cnt),
            }
        )

    return items, total


def get_review_document(
    db: Session,
    document_id: uuid.UUID,
    user: User,
    *,
    for_update: bool = False,
) -> Optional[Document]:
    stmt = (
        select(Document)
        .options(selectinload(Document.uploader))
        .where(
            Document.id == document_id,
            visible_documents_filter(user),
        )
    )
    if for_update:
        stmt = stmt.with_for_update(of=Document)
    return db.execute(stmt).scalar_one_or_none()


def get_document_invoice(
    db: Session,
    document_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Optional[ExtractedInvoice]:
    stmt = (
        select(ExtractedInvoice)
        .options(selectinload(ExtractedInvoice.line_items))
        .where(ExtractedInvoice.document_id == document_id)
    )
    if for_update:
        stmt = stmt.with_for_update(of=ExtractedInvoice)
    return db.execute(stmt).scalar_one_or_none()


def get_corrections(
    db: Session,
    document_id: uuid.UUID,
) -> list[DocumentCorrection]:
    return list(
        db.execute(
            select(DocumentCorrection)
            .where(DocumentCorrection.document_id == document_id)
            .order_by(DocumentCorrection.created_at.desc(), DocumentCorrection.id.desc())
        )
        .scalars()
        .all()
    )


def insert_corrections(
    db: Session,
    corrections: list[DocumentCorrection],
) -> list[DocumentCorrection]:
    for c in corrections:
        db.add(c)
    db.flush()
    return corrections

