"""Job queue operations: enqueue, claim (SKIP LOCKED), recover, heartbeat.

All SQL lives here. Services and the runner call these functions
but never build queries themselves.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models.job import ProcessingJob

logger = logging.getLogger(__name__)


def enqueue(
    session: Session,
    job_type: str,
    document_id: uuid.UUID | None = None,
    run_after: datetime | None = None,
) -> ProcessingJob:
    """Insert a new job in PENDING state.

    Args:
        session: Active SQLAlchemy session.
        job_type: One of DOCUMENT_PROCESSING, EMBEDDING.
        document_id: Optional associated document.
        run_after: Earliest time the job may be claimed (default: now).

    Returns:
        The persisted ProcessingJob with server-generated id and timestamps.
    """
    job = ProcessingJob(
        job_type=job_type,
        document_id=document_id,
        status="PENDING",
        run_after=run_after or datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    logger.info("Enqueued job %s (type=%s)", job.id, job.job_type)
    return job


def claim(session: Session) -> ProcessingJob | None:
    """Claim the oldest eligible PENDING job via FOR UPDATE SKIP LOCKED.

    The claim is committed immediately so the row lock is released
    before the handler runs (logical lease pattern).

    Returns:
        The claimed ProcessingJob (now PROCESSING), or None if the queue
        is empty.
    """
    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == "PENDING",
            ProcessingJob.run_after <= func.now(),
        )
        .order_by(
            ProcessingJob.run_after.asc(),
            ProcessingJob.created_at.asc(),
        )
        .with_for_update (skip_locked=True)
        .limit(1)
    )
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None

    job.status = "PROCESSING"
    job.locked_at = datetime.now(timezone.utc)
    job.attempt_count += 1
    if job.started_at is None:
        job.started_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(job)
    logger.info(
        "Claimed job %s (type=%s, attempt=%d)",
        job.id,
        job.job_type,
        job.attempt_count,
    )
    return job


def recover_stuck_jobs(
    session: Session,
    timeout_seconds: int,
    max_attempts: int,
) -> int:
    """Recover jobs stuck in PROCESSING beyond the lease timeout.

    Jobs that have exhausted max_attempts are marked FAILED.
    Otherwise they are returned to PENDING for retry.

    Returns:
        Number of jobs recovered or failed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == "PROCESSING",
            ProcessingJob.locked_at < cutoff,
        )
        .with_for_update (skip_locked=True)
    )
    stuck_jobs = list(session.execute(stmt).scalars().all())

    for job in stuck_jobs:
        if job.attempt_count >= max_attempts:
            job.status = "FAILED"
            job.error_message = (
                f"Job timed out after {job.attempt_count} attempts "
                f"(locked_at older than {timeout_seconds}s)"
            )
            job.completed_at = datetime.now(timezone.utc)
            logger.warning(
                "Marked stuck job %s as FAILED (attempts exhausted)", job.id
            )
        else:
            job.status = "PENDING"
            job.locked_at = None
            job.run_after = datetime.now(timezone.utc)
            logger.info("Recovered stuck job %s back to PENDING", job.id)

    if stuck_jobs:
        session.commit()

    return len(stuck_jobs)


def heartbeat(
    session: Session,
    job_id: uuid.UUID,
    current_stage: str | None = None,
) -> None:
    """Update the lease heartbeat and optionally the current stage.

    Called by handlers between long-running stages to prevent
    the stuck-job reaper from reclaiming this job.
    """
    values: dict = {"locked_at": datetime.now(timezone.utc)}
    if current_stage is not None:
        values["current_stage"] = current_stage

    stmt = (
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(**values)
    )
    session.execute(stmt)
    session.commit()


def complete_job(session: Session, job_id: uuid.UUID) -> None:
    """Mark a job as successfully completed."""
    stmt = (
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status="COMPLETED",
            completed_at=datetime.now(timezone.utc),
        )
    )
    session.execute(stmt)
    session.commit()
    logger.info("Job %s completed successfully", job_id)


def retry_job(
    session: Session,
    job_id: uuid.UUID,
    delay_seconds: float,
    error_message: str,
) -> None:
    """Schedule a job for retry with the given backoff delay."""
    run_after = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    stmt = (
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status="PENDING",
            locked_at=None,
            run_after=run_after,
            error_message=error_message,
        )
    )
    session.execute(stmt)
    session.commit()
    logger.info(
        "Job %s scheduled for retry at %s (delay=%.1fs)",
        job_id,
        run_after,
        delay_seconds,
    )


def fail_job(
    session: Session,
    job_id: uuid.UUID,
    error_message: str,
) -> None:
    """Mark a job as permanently failed."""
    stmt = (
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status="FAILED",
            completed_at=datetime.now(timezone.utc),
            error_message=error_message,
        )
    )
    session.execute(stmt)
    session.commit()
    logger.warning("Job %s marked FAILED: %s", job_id, error_message)

