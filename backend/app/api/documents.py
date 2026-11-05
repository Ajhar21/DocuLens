from __future__ import annotations

from typing import Any, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit import DocumentHistoryResponse
from app.schemas.document import (
    BatchUploadResponse,
    DocumentDetailRead,
    DocumentPage,
    DocumentStatusRead,
    ExtractedInvoiceRead,
    UploadPolicy,
    ValidationResultRead,
)
from app.schemas.job import JobRead
from app.services import document_service
from app.services.audit_service import AuditService

router = APIRouter(prefix="/documents", tags=["documents"])

_BATCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_207_MULTI_STATUS: {
        "model": APIResponse[BatchUploadResponse],
        "description": "Some files accepted, some rejected (see per-file results).",
    },
    422: {
        "model": APIResponse[BatchUploadResponse],
        "description": "All files rejected (error.code='all_files_rejected', data holds "
        "per-file reasons) or request validation failed (error.code='validation_error').",
    },
}


def _handle_upload(
    response: Response,
    files: list[UploadFile],
    db: Session,
    current_user: User,
) -> APIResponse[BatchUploadResponse]:
    batch = document_service.upload_documents(db, files, current_user)
    total = len(batch.results)

    if batch.accepted_count == 0:
        raise AppError(
            422,
            "all_files_rejected",
            "No files were accepted" if total != 1 else "The file was rejected",
            data=batch,
        )
    if batch.rejected_count > 0:
        response.status_code = status.HTTP_207_MULTI_STATUS
        return ok(batch, f"{batch.accepted_count} of {total} files accepted")
    return ok(batch, f"{total} file{'s' if total != 1 else ''} accepted")


@router.post(
    "",
    response_model=APIResponse[BatchUploadResponse],
    status_code=status.HTTP_201_CREATED,
    responses=_BATCH_RESPONSES,
)
def upload_documents(
    response: Response,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> APIResponse[BatchUploadResponse]:
    """Batch upload. 201 = all accepted, 207 = partial, 422 = all rejected."""
    return _handle_upload(response, files, db, current_user)


@router.post(
    "/upload",
    response_model=APIResponse[BatchUploadResponse],
    status_code=status.HTTP_201_CREATED,
    responses=_BATCH_RESPONSES,
)
def upload_documents_alias(
    response: Response,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> APIResponse[BatchUploadResponse]:
    """PRD 6.3 canonical upload path (/api/v1/documents/upload)."""
    return _handle_upload(response, files, db, current_user)


@router.get(
    "/upload-policy",
    response_model=APIResponse[UploadPolicy],
    dependencies=[Depends(require_permission(Permission.DOCUMENT_VIEW))],
)
def get_upload_policy() -> APIResponse[UploadPolicy]:
    return ok(document_service.get_upload_policy())


@router.get(
    "",
    response_model=APIResponse[DocumentPage],
)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    review_status_filter: Optional[str] = Query(default=None, alias="review_status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[DocumentPage]:
    return ok(
        document_service.list_documents(
            db,
            current_user,
            limit,
            offset,
            status_filter,
            review_status_filter,
        )
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[DocumentDetailRead],
)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[DocumentDetailRead]:
    return ok(document_service.get_document_detail(db, document_id, current_user))


@router.get(
    "/{document_id}/status",
    response_model=APIResponse[DocumentStatusRead],
)
def get_document_status(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[DocumentStatusRead]:
    return ok(document_service.get_document_status(db, document_id, current_user))


@router.get(
    "/{document_id}/extraction",
    response_model=APIResponse[Optional[ExtractedInvoiceRead]],
)
def get_document_extraction(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.EXTRACTION_VIEW)),
) -> APIResponse[Optional[ExtractedInvoiceRead]]:
    return ok(document_service.get_document_extraction(db, document_id, current_user))


@router.get(
    "/{document_id}/validation",
    response_model=APIResponse[list[ValidationResultRead]],
)
def get_document_validation(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.VALIDATION_VIEW)),
) -> APIResponse[list[ValidationResultRead]]:
    return ok(document_service.get_document_validation(db, document_id, current_user))


@router.post(
    "/{document_id}/reprocess",
    response_model=APIResponse[JobRead],
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_document(
    document_id: uuid.UUID,
    stage: Literal["extraction", "embedding"] = Query(
        ...,
        description="Pipeline stage to enqueue: 'extraction' or 'embedding'",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> APIResponse[JobRead]:
    job_read = document_service.reprocess_document(db, document_id, stage, current_user)
    return ok(job_read, f"Enqueued '{stage}' job for document {document_id}")


@router.get(
    "/{document_id}/file",
)
def download_document_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> FileResponse:
    """Binary download; intentionally not enveloped."""
    doc, file_path = document_service.resolve_document_file(db, document_id, current_user)
    return FileResponse(
        path=str(file_path),
        media_type=doc.content_type,
        filename=doc.original_filename,
    )


@router.get(
    "/{document_id}/history",
    response_model=APIResponse[DocumentHistoryResponse],
    summary="Get unified chronological timeline for a document",
)
def get_document_history(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[DocumentHistoryResponse]:
    history = AuditService.get_document_history(db, document_id, current_user)
    return ok(history, "Document timeline history retrieved successfully")

