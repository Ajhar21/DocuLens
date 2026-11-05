"""Document domain service: upload, listing, detail, status, extraction, validation, reprocessing, and upload policy.

Routers stay thin HTTP adapters; all persistence, visibility filtering, and business rules live here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union
import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.responses import ErrorDetail
from app.models.document import Document, DocumentStatus, ReviewStatus
from app.models.job import JobType
from app.models.user import User
from app.repositories import document_repo
from app.schemas.document import (
    BatchUploadResponse,
    DocumentDetailRead,
    DocumentPage,
    DocumentRead,
    DocumentStatusRead,
    ExtractedInvoiceRead,
    FileUploadItemResult,
    ParseSummary,
    UploadPolicy,
    ValidationResultRead,
)
from app.schemas.job import JobRead
from app.services import job_queue
from app.services.audit_service import AuditService
from app.services.storage import (
    ALLOWED_EXTENSIONS,
    EXTENSION_CONTENT_TYPES,
    StorageValidationError,
    storage_service,
)

logger = logging.getLogger(__name__)

_ALLOWED_LIST = ", ".join(sorted(ALLOWED_EXTENSIONS))
_ALLOWED_REPROCESS_STAGES = {
    JobType.EXTRACTION.value,
    JobType.EMBEDDING.value,
}

_DOC_STATUS_ALIASES: dict[str, str] = {
    "uploaded": DocumentStatus.UPLOADED.value,
    "pending": DocumentStatus.UPLOADED.value,
    "processing": DocumentStatus.PROCESSING.value,
    "parsed": DocumentStatus.PARSED.value,
    "completed": DocumentStatus.PARSED.value,
    "failed": DocumentStatus.FAILED.value,
}

_REVIEW_STATUS_ALIASES: dict[str, str] = {
    "pending": ReviewStatus.PENDING.value,
    "needs_review": ReviewStatus.NEEDS_REVIEW.value,
    "in_review": "in_review",
    "corrected": "corrected",
    "approved": ReviewStatus.APPROVED.value,
    "rejected": ReviewStatus.REJECTED.value,
    "not_required": ReviewStatus.NOT_REQUIRED.value,
}


def normalize_document_status_filter(
    raw: Optional[Union[str, DocumentStatus]],
) -> Optional[str]:
    if raw is None:
        return None
    val = raw.value if isinstance(raw, DocumentStatus) else str(raw).strip().lower()
    if not val:
        return None
    mapped = _DOC_STATUS_ALIASES.get(val)
    if mapped is None:
        raise AppError(
            422,
            "validation_error",
            f"Invalid document status filter '{raw}'",
            details=[ErrorDetail(field="status", message=f"Invalid document status '{raw}'")],
        )
    return mapped


def normalize_review_status_filter(
    raw: Optional[Union[str, ReviewStatus]],
) -> Optional[str]:
    if raw is None:
        return None
    val = raw.value if isinstance(raw, ReviewStatus) else str(raw).strip().lower()
    if not val:
        return None
    mapped = _REVIEW_STATUS_ALIASES.get(val)
    if mapped is None:
        raise AppError(
            422,
            "validation_error",
            f"Invalid review_status filter '{raw}'",
            details=[
                ErrorDetail(
                    field="review_status",
                    message=f"Invalid review_status '{raw}'",
                )
            ],
        )
    return mapped


def get_upload_policy() -> UploadPolicy:
    return UploadPolicy(
        max_upload_mb=settings.MAX_UPLOAD_MB,
        max_upload_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
        accepted_content_types=sorted(set(EXTENSION_CONTENT_TYPES.values())),
    )


def _rejected(filename: str, reason: str) -> FileUploadItemResult:
    return FileUploadItemResult(filename=filename, status="rejected", reason=reason)


def _store_one(
    db: Session,
    upload: UploadFile,
    uploader: User,
    max_bytes: int,
) -> FileUploadItemResult:
    raw_filename = upload.filename or "unnamed"
    ext = Path(raw_filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        return _rejected(
            raw_filename,
            f"Unsupported file extension '{ext or '<none>'}'. Allowed: {_ALLOWED_LIST}",
        )

    doc_id = uuid.uuid4()
    try:
        stored_info = storage_service.save_stream(
            stream=upload.file,
            document_id=doc_id,
            ext=ext,
            max_bytes=max_bytes,
        )
    except StorageValidationError as exc:
        return _rejected(raw_filename, str(exc))
    except Exception:
        logger.exception("Unexpected error saving uploaded file %s", raw_filename)
        return _rejected(raw_filename, "The file could not be stored. Please try again.")

    content_type = upload.content_type or EXTENSION_CONTENT_TYPES.get(ext, "application/octet-stream")

    try:
        doc = Document(
            id=doc_id,
            original_filename=raw_filename,
            stored_path=stored_info.stored_path,
            content_type=content_type,
            file_ext=ext,
            size_bytes=stored_info.size_bytes,
            sha256=stored_info.sha256,
            status=DocumentStatus.UPLOADED.value,
            uploaded_by=uploader.id,
        )
        db.add(doc)
        db.flush()

        job = job_queue.enqueue(
            session=db,
            document_id=doc.id,
            job_type=JobType.PARSE.value,
            commit=False,
        )

        AuditService.record(
            db,
            user_id=uploader.id,
            action="DOCUMENT_UPLOADED",
            entity_type="DOCUMENT",
            entity_id=doc.id,
            old_values=None,
            new_values={
                "original_filename": raw_filename,
                "file_ext": ext,
                "size_bytes": stored_info.size_bytes,
                "sha256": stored_info.sha256,
                "status": doc.status,
                "job_id": str(job.id),
            },
        )
        db.commit()
        db.refresh(doc)
        db.refresh(job)
    except Exception:
        db.rollback()
        storage_service.delete(stored_info.stored_path)
        logger.exception("Database error persisting document %s", raw_filename)
        return _rejected(raw_filename, "The file could not be saved. Please try again.")

    return FileUploadItemResult(
        filename=raw_filename,
        status="accepted",
        document_id=doc.id,
        job_id=job.id,
    )


def upload_documents(db: Session, files: list[UploadFile], uploader: User) -> BatchUploadResponse:
    """Store each file independently; one bad file never fails the whole batch."""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    results = [_store_one(db, upload, uploader, max_bytes) for upload in files]
    accepted_count = sum(1 for r in results if r.status == "accepted")
    return BatchUploadResponse(
        results=results,
        accepted_count=accepted_count,
        rejected_count=len(results) - accepted_count,
    )


def list_documents(
    db: Session,
    current_user: User,
    limit: int,
    offset: int,
    status_filter: Optional[Union[str, DocumentStatus]] = None,
    review_status_filter: Optional[Union[str, ReviewStatus]] = None,
) -> DocumentPage:
    status_val = normalize_document_status_filter(status_filter)
    review_val = normalize_review_status_filter(review_status_filter)
    docs, total = document_repo.list_visible_documents(
        db,
        current_user,
        limit=limit,
        offset=offset,
        status_value=status_val,
        review_status_value=review_val,
    )
    return DocumentPage(
        items=[DocumentRead.model_validate(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_document(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> Document:
    doc = document_repo.get_visible_document(db, document_id, current_user)
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


def get_document_detail(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> DocumentDetailRead:
    doc = get_document(db, document_id, current_user)
    all_jobs = document_repo.get_document_jobs(db, document_id)
    latest_job = all_jobs[0] if all_jobs else None

    parse_row = document_repo.get_document_parse_result(db, document_id)
    parse_summary: Optional[ParseSummary] = None
    if parse_row is not None:
        pages_list = parse_row.pages if isinstance(parse_row.pages, list) else []
        tables_list = parse_row.tables if isinstance(parse_row.tables, list) else []
        meta_dict = parse_row.doc_metadata if isinstance(parse_row.doc_metadata, dict) else {}
        parse_summary = ParseSummary(
            page_count=len(pages_list),
            table_count=len(tables_list),
            ocr_used=parse_row.ocr_used,
            metadata=meta_dict,
            pages=pages_list,
            tables=tables_list,
            created_at=parse_row.created_at,
        )

    invoice_row = document_repo.get_document_invoice(db, document_id)
    validation_rows = document_repo.get_document_validations(db, document_id)

    base_doc = DocumentRead.model_validate(doc)
    return DocumentDetailRead(
        **base_doc.model_dump(),
        latest_job=JobRead.model_validate(latest_job) if latest_job else None,
        processing_jobs=[JobRead.model_validate(j) for j in all_jobs],
        parse_summary=parse_summary,
        extracted_invoice=(
            ExtractedInvoiceRead.model_validate(invoice_row)
            if invoice_row is not None
            else None
        ),
        validation_results=[ValidationResultRead.model_validate(v) for v in validation_rows],
    )


def get_document_status(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> DocumentStatusRead:
    doc = get_document(db, document_id, current_user)
    all_jobs = document_repo.get_document_jobs(db, document_id)
    latest_job = all_jobs[0] if all_jobs else None
    doc_status = DocumentStatus(doc.status)
    return DocumentStatusRead(
        id=doc.id,
        status=doc_status,
        processing_status=doc_status,
        review_status=ReviewStatus(doc.review_status) if doc.review_status in {r.value for r in ReviewStatus} else None,
        error=doc.error,
        latest_job=JobRead.model_validate(latest_job) if latest_job else None,
        processing_jobs=[JobRead.model_validate(j) for j in all_jobs],
        updated_at=doc.updated_at,
    )


def get_document_extraction(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> Optional[ExtractedInvoiceRead]:
    doc = get_document(db, document_id, current_user)
    invoice_row = document_repo.get_document_invoice(db, doc.id)
    if invoice_row is None:
        return None
    return ExtractedInvoiceRead.model_validate(invoice_row)


def get_document_validation(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> list[ValidationResultRead]:
    doc = get_document(db, document_id, current_user)
    validation_rows = document_repo.get_document_validations(db, doc.id)
    return [ValidationResultRead.model_validate(v) for v in validation_rows]


def reprocess_document(
    db: Session,
    document_id: uuid.UUID,
    stage: str,
    current_user: User,
) -> JobRead:
    doc = get_document(db, document_id, current_user)

    normalized_stage = (stage or "").strip().lower()
    if normalized_stage not in _ALLOWED_REPROCESS_STAGES:
        raise AppError(
            422,
            "validation_error",
            "Invalid stage parameter. Allowed values: 'extraction', 'embedding'.",
        )

    parse_row = document_repo.get_document_parse_result(db, doc.id)
    if parse_row is None:
        raise ConflictError(
            "Cannot reprocess extraction or embedding before document parsing has succeeded."
        )

    job = job_queue.enqueue(
        session=db,
        document_id=doc.id,
        job_type=normalized_stage,
        commit=True,
    )
    return JobRead.model_validate(job)


def resolve_document_file(
    db: Session,
    document_id: uuid.UUID,
    current_user: User,
) -> tuple[Document, Path]:
    doc = get_document(db, document_id, current_user)
    try:
        file_path = storage_service.resolve_path(doc.stored_path)
    except ValueError:
        raise NotFoundError("Stored file path is invalid")
    if not file_path.exists():
        raise NotFoundError("Stored file not found on disk")
    return doc, file_path
