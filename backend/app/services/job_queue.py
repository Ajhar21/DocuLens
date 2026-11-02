from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.job import JobStatus, ProcessingJob

logger = logging.getLogger(__name__)


def enqueue(
    session: Session,
    document_id: uuid.UUID,
    job_type: str = "parse",
    max_attempts: int = 3,
    run_after: Optional[datetime] = None,
    commit: bool = True,
) -> ProcessingJob:
    now = datetime.now(timezone.utc)
    job = ProcessingJob(
        document_id=document_id,
        job_type=job_type,
        status=JobStatus.PENDING.value,
        attempts=0,
        max_attempts=max_attempts,
        run_after=run_after or now,
        created_at=now,
    )
    session.add(job)
    if commit:
        session.commit()
        session.refresh(job)
    else:
        session.flush()
    return job


def claim_next(session: Session, worker_id: str) -> Optional[ProcessingJob]:
    now = datetime.now(timezone.utc)
    subq = (
        select(ProcessingJob.id)
        .where(
            ProcessingJob.status == JobStatus.PENDING.value,
            ProcessingJob.run_after <= now,
        )
        .order_by(ProcessingJob.run_after.asc(), ProcessingJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
        .scalar_subquery()
    )

    stmt = (
        update(ProcessingJob)
        .where(ProcessingJob.id == subq)
        .values(
            status=JobStatus.RUNNING.value,
            locked_by=worker_id,
            locked_at=now,
            started_at=func.coalesce(ProcessingJob.started_at, now),
            attempts=ProcessingJob.attempts + 1,
        )
        .returning(ProcessingJob)
    )

    job = session.scalars(
        stmt, execution_options={"populate_existing": True}
    ).first()

    if job is None:
        session.rollback()
        return None

    doc = session.get(Document, job.document_id)
    if doc is not None:
        doc.status = DocumentStatus.PROCESSING.value
        doc.updated_at = now

    session.commit()
    session.refresh(job)
    return job


def mark_succeeded(session: Session, job_id: uuid.UUID) -> Optional[ProcessingJob]:
    now = datetime.now(timezone.utc)
    job = session.get(ProcessingJob, job_id)
    if job is None:
        return None

    job.status = JobStatus.SUCCEEDED.value
    job.finished_at = now
    job.locked_by = None
    job.locked_at = None
    job.last_error = None

    doc = session.get(Document, job.document_id)
    if doc is not None:
        doc.status = DocumentStatus.PARSED.value
        doc.error = None
        doc.updated_at = now

    session.commit()
    session.refresh(job)
    return job


def mark_failed(
    session: Session,
    job_id: uuid.UUID,
    error: str,
    backoff_base_seconds: float = 5.0,
) -> Optional[ProcessingJob]:
    now = datetime.now(timezone.utc)
    job = session.get(ProcessingJob, job_id)
    if job is None:
        return None

    clean_error = (error or "Unknown processing error").strip()
    job.last_error = clean_error
    job.locked_by = None
    job.locked_at = None

    if job.attempts < job.max_attempts:
        delay = backoff_base_seconds * (2 ** max(0, job.attempts - 1))
        job.status = JobStatus.PENDING.value
        job.run_after = now + timedelta(seconds=delay)
    else:
        job.status = JobStatus.FAILED.value
        job.finished_at = now
        doc = session.get(Document, job.document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED.value
            doc.error = clean_error
            doc.updated_at = now

    session.commit()
    session.refresh(job)
    return job


def requeue_stale(
    session: Session,
    stale_minutes: Optional[int] = None,
) -> int:
    timeout_mins = stale_minutes if stale_minutes is not None else settings.JOB_STALE_MINUTES
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=timeout_mins)

    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == JobStatus.RUNNING.value,
            ProcessingJob.locked_at < cutoff,
        )
        .with_for_update(skip_locked=True)
    )
    stale_jobs = list(session.scalars(stmt).all())
    for job in stale_jobs:
        job.status = JobStatus.PENDING.value
        job.locked_by = None
        job.locked_at = None
        job.run_after = now

    if stale_jobs:
        session.commit()

    return len(stale_jobs)
