from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.job import ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import User, UserRole
from app.schemas.document import (
    BatchUploadResponse,
    DocumentDetailRead,
    DocumentRead,
    FileUploadItemResult,
    ParseSummary,
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

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.REVIEWER))],
)
def upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchUploadResponse:
    results: list[FileUploadItemResult] = []
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    for upload in files:
        raw_filename = upload.filename or "unnamed"
        ext = Path(raw_filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            results.append(
                FileUploadItemResult(
                    filename=raw_filename,
                    status="rejected",
                    reason=f"Unsupported file extension '{ext or '<none>'}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
                )
            )
            continue

        doc_id = uuid.uuid4()
        try:
            stored_info = storage_service.save_stream(
                stream=upload.file,
                document_id=doc_id,
                ext=ext,
                max_bytes=max_bytes,
            )
        except StorageValidationError as exc:
            results.append(
                FileUploadItemResult(
                    filename=raw_filename,
                    status="rejected",
                    reason=str(exc),
                )
            )
            continue
        except Exception as exc:
            logger.exception("Unexpected error saving uploaded file %s", raw_filename)
            results.append(
                FileUploadItemResult(
                    filename=raw_filename,
                    status="rejected",
                    reason=f"Storage error: {exc}",
                )
            )
            continue

        content_type = upload.content_type or EXTENSION_CONTENT_TYPES.get(
            ext, "application/octet-stream"
        )

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
                uploaded_by=current_user.id,
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

            results.append(
                FileUploadItemResult(
                    filename=raw_filename,
                    status="accepted",
                    document_id=doc.id,
                    job_id=job.id,
                )
            )
        except Exception as exc:
            db.rollback()
            storage_service.delete(stored_info.stored_path)
            logger.exception("Database error persisting document %s", raw_filename)
            results.append(
                FileUploadItemResult(
                    filename=raw_filename,
                    status="rejected",
                    reason=f"Database error: {exc}",
                )
            )

    accepted_count = sum(1 for r in results if r.status == "accepted")
    rejected_count = len(results) - accepted_count
    return BatchUploadResponse(
        results=results,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )


@router.get(
    "",
    response_model=list[DocumentRead],
    dependencies=[Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER))],
)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[DocumentStatus] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    stmt = select(Document).order_by(Document.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Document.status == status_filter.value)
    stmt = stmt.limit(limit).offset(offset)
    docs = db.execute(stmt).scalars().all()
    return [DocumentRead.model_validate(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentDetailRead,
    dependencies=[Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER))],
)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentDetailRead:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

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


@router.get(
    "/{document_id}/file",
    dependencies=[Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER))],
)
def download_document_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    try:
        file_path = storage_service.resolve_path(doc.stored_path)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file path is invalid",
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file not found on disk",
        )

    return FileResponse(
        path=str(file_path),
        media_type=doc.content_type,
        filename=doc.original_filename,
    )
