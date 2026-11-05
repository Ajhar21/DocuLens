from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.job import JobPage, JobRead
from app.services.job_service import JobService

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_permission(Permission.JOB_VIEW))],
)


@router.get("", response_model=APIResponse[JobPage], summary="List processing jobs")
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status (pending, running, succeeded, failed)"),
    job_type: Optional[str] = Query(None, description="Filter by job type (parse, extraction, embedding)"),
    document_id: Optional[uuid.UUID] = Query(None, description="Filter by associated document UUID"),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.JOB_VIEW)),
) -> APIResponse[JobPage]:
    page_data = JobService.list_jobs(
        db,
        status_filter=status,
        job_type=job_type,
        document_id=document_id,
        page=page,
        page_size=page_size,
    )
    return ok(page_data, "Processing jobs retrieved successfully")


@router.get("/{job_id}", response_model=APIResponse[JobRead], summary="Get job detail")
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.JOB_VIEW)),
) -> APIResponse[JobRead]:
    return ok(JobService.get_job(db, job_id))


@router.post(
    "/{job_id}/retry",
    response_model=APIResponse[JobRead],
    summary="Retry a failed processing job in-place",
)
def retry_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.JOB_RETRY)),
) -> APIResponse[JobRead]:
    retried = JobService.retry_job(db, job_id, current_user)
    return ok(retried, f"Job {job_id} successfully queued for retry")
