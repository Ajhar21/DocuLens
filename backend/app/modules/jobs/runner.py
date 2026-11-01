"""Job runner: the single entry point for executing a claimed job.

``run_job(job_id)`` knows nothing about polling; it is a pure execution
coordinator.  The worker loop is the thin driver, so a broker can replace
it later with zero changes here.
"""

from __future__ import annotations

import logging
import traceback
import uuid

from app.core.config import settings
from app.db.models.job import ProcessingJob
from app.db.session import get_db_session
from app.modules.jobs import queue
from app.modules.jobs.exceptions import NonRetryableError, RetryableError
from app.modules.jobs.handlers import JOB_HANDLERS

logger = logging.getLogger(__name__)


def run_job(job_id: uuid.UUID) -> bool:
    """Execute a single claimed job by ID.

    Opens its own DB session so the caller (worker loop) does not need
    to manage transaction scope.

    Returns:
        True if the job was handled (success, retry, or fail).
        False if skipped (not found or wrong status).
    """
    with get_db_session() as session:
        job = session.get(ProcessingJob, job_id)
        if job is None:
            logger.error("Job %s not found", job_id)
            return False

        if job.status != "PROCESSING":
            logger.warning(
                "Job %s has status %s (expected PROCESSING), skipping",
                job_id,
                job.status,
            )
            return False

        handler = JOB_HANDLERS.get(job.job_type)
        if handler is None:
            queue.fail_job(
                session,
                job_id,
                f"No handler registered for job_type={job.job_type!r}",
            )
            return True

        try:
            handler(job, session)
            queue.complete_job(session, job_id)
            return True

        except RetryableError as exc:
            _handle_retryable(session, job, exc)
            return True

        except NonRetryableError as exc:
            queue.fail_job(session, job_id, f"NonRetryableError: {exc}")
            return True

        except Exception as exc:
            # Unexpected errors are treated as non-retryable
            tb = traceback.format_exc()
            queue.fail_job(
                session,
                job_id,
                f"Unexpected error: {exc}\n{tb}",
            )
            return True


def _handle_retryable(
    session,
    job: ProcessingJob,
    exc: RetryableError,
) -> None:
    """Schedule retry with exponential backoff, or fail if exhausted.

    Backoff formula: ``base * 2^(attempt_count - 1)``
    Example (base=5s): attempt 1 → 5s, attempt 2 → 10s, attempt 3 → 20s
    """
    max_attempts = settings.WORKER_MAX_ATTEMPTS
    base = settings.WORKER_BACKOFF_BASE_SECONDS

    if job.attempt_count < max_attempts:
        delay = base * (2 ** (job.attempt_count - 1))
        queue.retry_job(
            session,
            job.id,
            delay_seconds=delay,
            error_message=(
                f"RetryableError (attempt {job.attempt_count}/{max_attempts}): {exc}"
            ),
        )
    else:
        queue.fail_job(
            session,
            job.id,
            (
                f"RetryableError after {job.attempt_count} attempts "
                f"(max {max_attempts}): {exc}"
            ),
        )

