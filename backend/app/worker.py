"""Background worker poll loop.

Usage::

    python -m app.worker              # continuous poll loop
    python -m app.worker --run-once   # process one job then exit

The worker is a thin driver around ``run_job(job_id)`` — it handles
only polling, signal handling, and stuck-job recovery. A message broker
can replace this module with zero changes to the runner or handlers.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from app.core.config import settings
from app.db.session import get_db_session
from app.modules.jobs import queue
from app.modules.jobs.runner import run_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

_shutdown_requested = False


def _handle_signal(signum: int, frame) -> None:  # noqa: ANN001
    """Set the shutdown flag on interrupt / break signals."""
    global _shutdown_requested  # noqa: PLW0603
    logger.info("Received signal %d, requesting graceful shutdown...", signum)
    _shutdown_requested = True


def _poll_once() -> bool:
    """Run one poll cycle: recover stuck jobs, then claim and run one job.

    Returns True if a job was claimed and processed.
    """
    # Phase 1: recover any stuck jobs
    with get_db_session() as session:
        recovered = queue.recover_stuck_jobs(
            session,
            timeout_seconds=settings.WORKER_STUCK_JOB_TIMEOUT_SECONDS,
            max_attempts=settings.WORKER_MAX_ATTEMPTS,
        )
        if recovered:
            logger.info("Recovered %d stuck job(s)", recovered)

    # Phase 2: claim and run the next job
    with get_db_session() as session:
        job = queue.claim(session)

    if job is None:
        return False

    run_job(job.id)
    return True


def main() -> None:
    """Entry point for the worker CLI."""
    parser = argparse.ArgumentParser(description="DocuLens background worker")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process at most one job, then exit",
    )
    args = parser.parse_args()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handle_signal)  # type: ignore[attr-defined]
    else:
        signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Worker starting (poll_interval=%.1fs, max_attempts=%d, "
        "backoff_base=%.1fs, stuck_timeout=%ds)",
        settings.WORKER_POLL_INTERVAL_SECONDS,
        settings.WORKER_MAX_ATTEMPTS,
        settings.WORKER_BACKOFF_BASE_SECONDS,
        settings.WORKER_STUCK_JOB_TIMEOUT_SECONDS,
    )

    if args.run_once:
        logger.info("Running in --run-once mode")
        processed = _poll_once()
        if processed:
            logger.info("Processed one job, exiting")
        else:
            logger.info("No jobs available, exiting")
        return

    # Continuous poll loop
    logger.info("Entering continuous poll loop (Ctrl+C to stop)")
    while not _shutdown_requested:
        try:
            processed = _poll_once()
            if not processed:
                time.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("Unexpected error in poll loop, sleeping before retry")
            time.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

    logger.info("Worker shut down gracefully")


if __name__ == "__main__":
    main()

