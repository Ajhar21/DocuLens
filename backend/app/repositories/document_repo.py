from __future__ import annotations

from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.visibility import visible_documents_filter
from app.models.document import Document
from app.models.extraction import ExtractedInvoice
from app.models.job import ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import User
from app.models.validation import ValidationResult


def list_visible_documents(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
    status_value: Optional[str] = None,
    review_status_value: Optional[str] = None,
) -> tuple[list[Document], int]:
    visibility_clause = visible_documents_filter(user)
    base = select(Document).where(visibility_clause)
    count_stmt = select(func.count()).select_from(Document).where(visibility_clause)

    if status_value is not None:
        base = base.where(Document.status == status_value)
        count_stmt = count_stmt.where(Document.status == status_value)
    if review_status_value is not None:
        base = base.where(Document.review_status == review_status_value)
        count_stmt = count_stmt.where(Document.review_status == review_status_value)

    total = int(db.execute(count_stmt).scalar_one())
    docs = list(
        db.execute(
            base.options(selectinload(Document.uploader))
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return docs, total


def get_visible_document(
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


def get_document_jobs(db: Session, document_id: uuid.UUID) -> list[ProcessingJob]:
    return list(
        db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
        )
        .scalars()
        .all()
    )


def get_document_parse_result(
    db: Session,
    document_id: uuid.UUID,
) -> Optional[DocumentParseResult]:
    return db.execute(
        select(DocumentParseResult).where(DocumentParseResult.document_id == document_id)
    ).scalar_one_or_none()


def get_document_invoice(
    db: Session,
    document_id: uuid.UUID,
) -> Optional[ExtractedInvoice]:
    return db.execute(
        select(ExtractedInvoice)
        .options(selectinload(ExtractedInvoice.line_items))
        .where(ExtractedInvoice.document_id == document_id)
    ).scalar_one_or_none()


def get_document_validations(
    db: Session,
    document_id: uuid.UUID,
) -> list[ValidationResult]:
    return list(
        db.execute(
            select(ValidationResult)
            .where(ValidationResult.document_id == document_id)
            .order_by(ValidationResult.created_at.asc(), ValidationResult.id.asc())
        )
        .scalars()
        .all()
    )

