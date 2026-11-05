from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Optional
import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.document import Document, DocumentStatus
from app.models.job import JobStatus, ProcessingJob
from app.models.user import User
from app.repositories import job_repo
from app.schemas.job import JobPage, JobPagination, JobRead
from app.services.audit_service import AuditService


class JobService:
    @staticmethod
    def get_job(db: Session, job_id: uuid.UUID) -> JobRead:
        job = job_repo.get_job(db, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        return JobRead.model_validate(job)

    @staticmethod
    def list_jobs(
        db: Session,
        *,
        status_filter: Optional[str] = None,
        job_type: Optional[str] = None,
        document_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> JobPage:
        items, total = job_repo.list_jobs(
            db,
            status=status_filter,
            job_type=job_type,
            document_id=document_id,
            page=page,
            page_size=page_size,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        pagination = JobPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )
        return JobPage(
            items=[JobRead.model_validate(j) for j in items],
            pagination=pagination,
        )

    @staticmethod
    def retry_job(
        db: Session,
        job_id: uuid.UUID,
        current_user: User,
    ) -> JobRead:
        job = job_repo.get_job(db, job_id, for_update=True)
        if job is None:
            raise NotFoundError("Job not found")

        # 1. State check: Reject if job status is NOT 'failed' (409 Conflict)
        if job.status != JobStatus.FAILED.value:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "invalid_job_state",
                f"Cannot retry job in status '{job.status}'. Only failed jobs can be retried.",
            )

        # 2. Check active job uniqueness conflict
        if job_repo.has_active_job(
            db,
            document_id=job.document_id,
            job_type=job.job_type,
            exclude_job_id=job.id,
        ):
            raise AppError(
                status.HTTP_409_CONFLICT,
                "active_job_conflict",
                f"An active {job.job_type} job already exists for document {job.document_id}.",
            )

        # 3. Preserve old failure state for audit
        old_values = {
            "status": job.status,
            "attempts": job.attempts,
            "last_error": job.last_error,
            "current_stage": job.current_stage,
        }

        # 4. In-place reset
        now = datetime.now(timezone.utc)
        job.status = JobStatus.PENDING.value
        job.run_after = now
        job.attempts = 0
        job.locked_by = None
        job.locked_at = None
        job.current_stage = None
        job.started_at = None
        job.finished_at = None
        job.last_error = None

        doc = db.get(Document, job.document_id)
        if doc is not None and doc.status == DocumentStatus.FAILED.value:
            doc.status = DocumentStatus.PROCESSING.value
            doc.error = None
            doc.updated_at = now

        # 5. Record audit log
        AuditService.record(
            db,
            user_id=current_user.id,
            action="job:retry",
            entity_type="processing_job",
            entity_id=job.id,
            old_values=old_values,
            new_values={
                "status": JobStatus.PENDING.value,
                "attempts": 0,
                "run_after": now.isoformat(),
                "document_id": str(job.document_id),
                "job_type": job.job_type,
            },
        )

        db.commit()
        db.refresh(job)
        return JobRead.model_validate(job)

