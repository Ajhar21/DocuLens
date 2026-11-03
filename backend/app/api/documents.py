from __future__ import annotations

from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.errors import AppError
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.document import DocumentStatus
from app.models.user import User, UserRole
from app.schemas.document import (
    BatchUploadResponse,
    DocumentDetailRead,
    DocumentPage,
    UploadPolicy,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])

_read_roles = Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER))

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


@router.post(
    "",
    response_model=APIResponse[BatchUploadResponse],
    status_code=status.HTTP_201_CREATED,
    responses=_BATCH_RESPONSES,
    dependencies=[Depends(require_role(UserRole.REVIEWER))],
)
def upload_documents(
    response: Response,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[BatchUploadResponse]:
    """Batch upload. 201 = all accepted, 207 = partial, 422 = all rejected."""
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


@router.get(
    "/upload-policy",
    response_model=APIResponse[UploadPolicy],
    dependencies=[_read_roles],
)
def get_upload_policy() -> APIResponse[UploadPolicy]:
    return ok(document_service.get_upload_policy())


@router.get(
    "",
    response_model=APIResponse[DocumentPage],
    dependencies=[_read_roles],
)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[DocumentStatus] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> APIResponse[DocumentPage]:
    return ok(document_service.list_documents(db, limit, offset, status_filter))


@router.get(
    "/{document_id}",
    response_model=APIResponse[DocumentDetailRead],
    dependencies=[_read_roles],
)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> APIResponse[DocumentDetailRead]:
    return ok(document_service.get_document_detail(db, document_id))


@router.get(
    "/{document_id}/file",
    dependencies=[_read_roles],
)
def download_document_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Binary download; intentionally not enveloped."""
    doc, file_path = document_service.resolve_document_file(db, document_id)
    return FileResponse(
        path=str(file_path),
        media_type=doc.content_type,
        filename=doc.original_filename,
    )
