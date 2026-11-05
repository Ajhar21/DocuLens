from __future__ import annotations

from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.reconciliation import ReconciliationJob, ReconciliationResult


def create_reconciliation_job(
    db: Session,
    job: ReconciliationJob,
    results: list[ReconciliationResult],
) -> ReconciliationJob:
    db.add(job)
    db.flush()
    for r in results:
        r.job_id = job.id
        db.add(r)
    db.flush()
    return job


def get_reconciliation_job(
    db: Session,
    job_id: uuid.UUID,
) -> Optional[ReconciliationJob]:
    stmt = (
        select(ReconciliationJob)
        .options(selectinload(ReconciliationJob.results))
        .where(ReconciliationJob.id == job_id)
    )
    return db.scalars(stmt).unique().one_or_none()


def list_reconciliation_jobs(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    document_id: Optional[uuid.UUID] = None,
) -> tuple[list[ReconciliationJob], int]:
    count_stmt = select(func.count(ReconciliationJob.id))
    if document_id is not None:
        count_stmt = count_stmt.where(
            or_(
                ReconciliationJob.document_id_a == document_id,
                ReconciliationJob.document_id_b == document_id,
            )
        )
    total = db.scalar(count_stmt) or 0

    query_stmt = (
        select(ReconciliationJob)
        .order_by(ReconciliationJob.initiated_at.desc(), ReconciliationJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if document_id is not None:
        query_stmt = query_stmt.where(
            or_(
                ReconciliationJob.document_id_a == document_id,
                ReconciliationJob.document_id_b == document_id,
            )
        )

    items = list(db.scalars(query_stmt).all())
    return items, total

