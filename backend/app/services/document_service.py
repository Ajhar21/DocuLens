"""Document domain service: upload, listing, detail and upload policy.

Routers stay thin HTTP adapters; all persistence and business rules live here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import uuid

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import NotFoundError
from app.models.document import Document, DocumentStatus
from app.models.job import ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import User
from app.schemas.document import (
    BatchUploadResponse,
    DocumentDetailRead,
    DocumentPage,
    DocumentRead,
    FileUploadItemResult,
    ParseSummary,
    UploadPolicy,
)
from app.schemas.job import JobRead
from app.services import job_queue
from app.services.storage import (
    ALLOWED_EXTENSIONS,
    EXTENSION_CONTENT_TYPES,
    StorageValidationError,
    storage_service,
)

logger = logging.getLogger(__name__)

_ALLOWED_LIST = ", ".join(sorted(ALLOWED_EXTENSIONS))


def get_upload_policy() -> UploadPolicy:
    return UploadPolicy(
        max_upload_mb=settings.MAX_UPLOAD_MB,
        max_upload_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
        accepted_content_types=sorted(set(EXTENSION_CONTENT_TYPES.values())),
    )


def _rejected(filename: str, reason: str) -> FileUploadItemResult:
    return FileUploadItemResult(filename=filename, status="rejected", reason=reason)


def _store_one(db: Session, upload: UploadFile, uploader: User, max_bytes: int) -> FileUploadItemResult:
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
        # Never leak internal exception text to clients; details go to the log.
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
            job_type="parse",
            commit=False,
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
    limit: int,
    offset: int,
    status_filter: Optional[DocumentStatus],
) -> DocumentPage:
    base = select(Document)
    count_stmt = select(func.count()).select_from(Document)
    if status_filter is not None:
        base = base.where(Document.status == status_filter.value)
        count_stmt = count_stmt.where(Document.status == status_filter.value)

    total = db.execute(count_stmt).scalar_one()
    docs = (
        db.execute(
            base.options(selectinload(Document.uploader))
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return DocumentPage(
        items=[DocumentRead.model_validate(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_document(db: Session, document_id: uuid.UUID) -> Document:
    doc = db.execute(
        select(Document)
        .options(selectinload(Document.uploader))
        .where(Document.id == document_id)
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


def get_document_detail(db: Session, document_id: uuid.UUID) -> DocumentDetailRead:
    doc = get_document(db, document_id)

    latest_job = (
        db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    parse_row = db.execute(
        select(DocumentParseResult).where(DocumentParseResult.document_id == document_id)
    ).scalar_one_or_none()

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

    base_doc = DocumentRead.model_validate(doc)
    return DocumentDetailRead(
        **base_doc.model_dump(),
        latest_job=JobRead.model_validate(latest_job) if latest_job else None,
        parse_summary=parse_summary,
    )


def resolve_document_file(db: Session, document_id: uuid.UUID) -> tuple[Document, Path]:
    doc = get_document(db, document_id)
    try:
        file_path = storage_service.resolve_path(doc.stored_path)
    except ValueError:
        raise NotFoundError("Stored file path is invalid")
    if not file_path.exists():
        raise NotFoundError("Stored file not found on disk")
    return doc, file_path

