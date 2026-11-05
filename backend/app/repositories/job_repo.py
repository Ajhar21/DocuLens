from __future__ import annotations

from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import JobStatus, ProcessingJob


def get_job(
    db: Session,
    job_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Optional[ProcessingJob]:
    stmt = select(ProcessingJob).where(ProcessingJob.id == job_id)
    if for_update:
        stmt = stmt.with_for_update(of=ProcessingJob)
    return db.execute(stmt).scalar_one_or_none()


def has_active_job(
    db: Session,
    *,
    document_id: uuid.UUID,
    job_type: str,
    exclude_job_id: Optional[uuid.UUID] = None,
) -> bool:
    stmt = select(func.count(ProcessingJob.id)).where(
        ProcessingJob.document_id == document_id,
        ProcessingJob.job_type == job_type,
        ProcessingJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
    )
    if exclude_job_id is not None:
        stmt = stmt.where(ProcessingJob.id != exclude_job_id)
    count = db.scalar(stmt) or 0
    return count > 0


def list_jobs(
    db: Session,
    *,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    document_id: Optional[uuid.UUID] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ProcessingJob], int]:
    filters = []
    if status is not None and status.strip():
        filters.append(ProcessingJob.status == status.strip().lower())
    if job_type is not None and job_type.strip():
        filters.append(ProcessingJob.job_type == job_type.strip().lower())
    if document_id is not None:
        filters.append(ProcessingJob.document_id == document_id)

    count_stmt = select(func.count(ProcessingJob.id))
    if filters:
        count_stmt = count_stmt.where(sa.and_(*filters))
    total = db.scalar(count_stmt) or 0

    query_stmt = (
        select(ProcessingJob)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if filters:
        query_stmt = query_stmt.where(sa.and_(*filters))

    items = list(db.scalars(query_stmt).all())
    return items, total

