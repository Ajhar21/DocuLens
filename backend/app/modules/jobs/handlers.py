"""Job handler registry.

Each handler is a callable: ``handler(job, session) -> None``.
Raise ``RetryableError`` for transient failures, ``NonRetryableError``
for fatal ones. The runner handles all dispatch and error mapping.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.models.job import ProcessingJob
from app.modules.jobs import queue

logger = logging.getLogger(__name__)


def dummy_handler(job: ProcessingJob, session: Session) -> None:
    """Simulates successful document processing for spike validation.

    In production this will be replaced by the real DOCUMENT_PROCESSING
    pipeline (parse → extract → validate → decide).
    """
    logger.info(
        "[dummy_handler] Processing job %s (type=%s)", job.id, job.job_type
    )
    queue.heartbeat(session, job.id, current_stage="dummy_stage_1")
    logger.info("[dummy_handler] Job %s completed dummy work", job.id)


# ── Handler Registry ──────────────────────────────────────────────────
# Maps job_type string → handler callable.
# New job types register here; the runner dispatches automatically.
JOB_HANDLERS: dict[str, Callable[[ProcessingJob, Session], None]] = {
    "DOCUMENT_PROCESSING": dummy_handler,
    "EMBEDDING": dummy_handler,  # placeholder until real embedding handler
}

