from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.errors import NotFoundError
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.job import ProcessingJob
from app.models.user import UserRole
from app.schemas.job import JobRead

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER))],
)


@router.get("/{job_id}", response_model=APIResponse[JobRead])
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> APIResponse[JobRead]:
    job = db.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id)
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")
    return ok(JobRead.model_validate(job))
