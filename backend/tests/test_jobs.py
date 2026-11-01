"""Integration tests for DocuLens background job processing engine.

Verifies:
1. Claim concurrency (two claimers never get the same job)
2. Retry with exponential backoff on RetryableError
3. Attempt exhaustion leads to FAILED status
4. Stuck-job recovery sweeps timed-out jobs
5. One-active-job-per-document-and-type uniqueness constraint
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.job import ProcessingJob
from app.db.session import SessionLocal
from app.modules.jobs import queue
from app.modules.jobs.exceptions import RetryableError
from app.modules.jobs.handlers import JOB_HANDLERS
from app.modules.jobs.runner import run_job


def _track(session: Session, job: ProcessingJob) -> ProcessingJob:
    """Register job ID for post-test cleanup."""
    if "test_job_ids" in session.info:
        session.info["test_job_ids"].append(job.id)
    return job


def test_claim_single_winner(db_session: Session) -> None:
    """Verify that when a job is available, only one claimer receives it."""
    doc_id = uuid.uuid4()
    job = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job)

    # First claim succeeds
    claimed_1 = queue.claim(db_session)
    assert claimed_1 is not None
    assert claimed_1.id == job.id
    assert claimed_1.status == "PROCESSING"
    assert claimed_1.attempt_count == 1
    assert claimed_1.locked_at is not None

    # Second claim attempt on empty queue returns None
    claimed_2 = queue.claim(db_session)
    assert claimed_2 is None


def test_claim_concurrent_skip_locked(db_session: Session) -> None:
    """Verify that two concurrent worker threads never claim the same job."""
    doc_id = uuid.uuid4()
    job = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job)

    claimed_results: list[uuid.UUID | None] = []
    lock = threading.Lock()

    def worker_claim() -> None:
        local_session = SessionLocal()
        try:
            claimed = queue.claim(local_session)
            with lock:
                claimed_results.append(claimed.id if claimed else None)
        finally:
            local_session.close()

    t1 = threading.Thread(target=worker_claim)
    t2 = threading.Thread(target=worker_claim)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one thread should claim the job, the other gets None
    non_none_claims = [cid for cid in claimed_results if cid is not None]
    assert len(non_none_claims) == 1
    assert non_none_claims[0] == job.id
    assert None in claimed_results


def test_retry_with_backoff(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that RetryableError reschedules job to PENDING with exponential backoff."""
    doc_id = uuid.uuid4()
    job = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job)

    claimed = queue.claim(db_session)
    assert claimed is not None
    assert claimed.attempt_count == 1

    # Mock handler to raise RetryableError
    def failing_handler(j: ProcessingJob, s: Session) -> None:
        raise RetryableError("Simulated upstream 503 timeout")

    monkeypatch.setitem(JOB_HANDLERS, "DOCUMENT_PROCESSING", failing_handler)

    now_before = datetime.now(timezone.utc)
    success = run_job(claimed.id)
    assert success is True

    db_session.expire_all()
    updated_job = db_session.get(ProcessingJob, claimed.id)
    assert updated_job is not None
    assert updated_job.status == "PENDING"
    assert updated_job.locked_at is None
    assert "Simulated upstream 503 timeout" in (updated_job.error_message or "")

    # Expected delay = WORKER_BACKOFF_BASE_SECONDS * 2^(1 - 1) = base * 1
    expected_min_run_after = now_before + timedelta(
        seconds=settings.WORKER_BACKOFF_BASE_SECONDS - 1.0
    )
    assert updated_job.run_after >= expected_min_run_after


def test_attempts_exhausted_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that exceeding max_attempts marks the job as FAILED."""
    doc_id = uuid.uuid4()
    job = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job)

    # Set attempt_count to max
    job.status = "PROCESSING"
    job.attempt_count = settings.WORKER_MAX_ATTEMPTS
    job.locked_at = datetime.now(timezone.utc)
    db_session.commit()

    def failing_handler(j: ProcessingJob, s: Session) -> None:
        raise RetryableError("Unrecoverable after max retries")

    monkeypatch.setitem(JOB_HANDLERS, "DOCUMENT_PROCESSING", failing_handler)

    success = run_job(job.id)
    assert success is True

    db_session.expire_all()
    failed_job = db_session.get(ProcessingJob, job.id)
    assert failed_job is not None
    assert failed_job.status == "FAILED"
    assert failed_job.completed_at is not None
    assert "max" in (failed_job.error_message or "").lower()


def test_stuck_job_recovery(db_session: Session) -> None:
    """Verify that stuck PROCESSING jobs are recovered back to PENDING or FAILED."""
    # Subtest A: Stuck job with remaining attempts resets to PENDING
    doc_id_1 = uuid.uuid4()
    stuck_job_1 = queue.enqueue(
        db_session, "DOCUMENT_PROCESSING", document_id=doc_id_1
    )
    _track(db_session, stuck_job_1)

    stuck_job_1.status = "PROCESSING"
    stuck_job_1.attempt_count = 1
    stuck_job_1.locked_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.commit()

    # Subtest B: Stuck job that reached max_attempts transitions to FAILED
    doc_id_2 = uuid.uuid4()
    stuck_job_2 = queue.enqueue(
        db_session, "DOCUMENT_PROCESSING", document_id=doc_id_2
    )
    _track(db_session, stuck_job_2)

    stuck_job_2.status = "PROCESSING"
    stuck_job_2.attempt_count = 3
    stuck_job_2.locked_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.commit()

    recovered_count = queue.recover_stuck_jobs(
        db_session, timeout_seconds=300, max_attempts=3
    )
    assert recovered_count >= 2

    db_session.expire_all()
    refreshed_1 = db_session.get(ProcessingJob, stuck_job_1.id)
    refreshed_2 = db_session.get(ProcessingJob, stuck_job_2.id)

    assert refreshed_1 is not None
    assert refreshed_1.status == "PENDING"
    assert refreshed_1.locked_at is None

    assert refreshed_2 is not None
    assert refreshed_2.status == "FAILED"
    assert refreshed_2.completed_at is not None
    assert "timed out" in (refreshed_2.error_message or "").lower()


def test_active_job_uniqueness(db_session: Session) -> None:
    """Verify partial unique index prevents concurrent active jobs for the same doc and type."""
    doc_id = uuid.uuid4()
    job_1 = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job_1)
    assert job_1.status == "PENDING"

    # Attempting to enqueue a second active job for the same doc and type must violate the unique index
    dup_job = ProcessingJob(
        job_type="DOCUMENT_PROCESSING",
        document_id=doc_id,
        status="PENDING",
    )
    db_session.add(dup_job)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "uq_processing_jobs_active_document_job" in str(exc_info.value)
    db_session.rollback()

    # Once the first job is COMPLETED, inserting a new job for the same doc succeeds
    queue.complete_job(db_session, job_1.id)

    job_2 = queue.enqueue(db_session, "DOCUMENT_PROCESSING", document_id=doc_id)
    _track(db_session, job_2)
    assert job_2.id != job_1.id
    assert job_2.status == "PENDING"

