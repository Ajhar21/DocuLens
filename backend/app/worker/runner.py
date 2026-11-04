from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import time
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.base import PermanentAIError, TransientAIError
from app.core.config import settings
from app.embeddings.service import run_document_embedding
from app.extraction.service import run_invoice_extraction
from app.models.document import Document
from app.models.job import JobType, ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.processing.base import DocumentParseError
from app.processing.registry import parse_document
from app.services import job_queue
from app.services.storage import storage_service
from app.validation.service import run_invoice_validation

logger = logging.getLogger(__name__)

JobHandler = Callable[[Session, ProcessingJob], None]


def handle_parse_job(session: Session, job: ProcessingJob) -> None:
    job_queue.update_stage(session, job.id, "parsing")

    doc = session.get(Document, job.document_id)
    if doc is None:
        raise DocumentParseError(f"Document {job.document_id} not found")

    try:
        file_path = storage_service.resolve_path(doc.stored_path)
    except ValueError as exc:
        raise DocumentParseError(f"Invalid stored file path: {exc}") from exc

    parsed = parse_document(file_path=file_path, file_ext=doc.file_ext)

    existing_result = session.execute(
        select(DocumentParseResult).where(DocumentParseResult.document_id == doc.id)
    ).scalar_one_or_none()

    pages_payload = [p.model_dump() for p in parsed.pages]
    tables_payload = [t.model_dump() for t in parsed.tables]

    if existing_result is not None:
        existing_result.pages = pages_payload
        existing_result.tables = tables_payload
        existing_result.doc_metadata = parsed.metadata
        existing_result.ocr_used = parsed.ocr_used
    else:
        parse_result = DocumentParseResult(
            document_id=doc.id,
            pages=pages_payload,
            tables=tables_payload,
            doc_metadata=parsed.metadata,
            ocr_used=parsed.ocr_used,
        )
        session.add(parse_result)

    session.flush()

    # Independently enqueue EXTRACTION and EMBEDDING jobs once parsing succeeds
    job_queue.enqueue(
        session=session,
        document_id=doc.id,
        job_type=JobType.EXTRACTION.value,
        commit=False,
    )
    job_queue.enqueue(
        session=session,
        document_id=doc.id,
        job_type=JobType.EMBEDDING.value,
        commit=False,
    )


def handle_extraction_job(session: Session, job: ProcessingJob) -> None:
    def _stage_cb(stage_name: str) -> None:
        job_queue.update_stage(session, job.id, stage_name)

    run_invoice_extraction(
        session=session,
        document_id=job.document_id,
        stage_callback=_stage_cb,
    )
    _stage_cb("validating")
    run_invoice_validation(
        session=session,
        document_id=job.document_id,
    )


def handle_embedding_job(session: Session, job: ProcessingJob) -> None:
    def _stage_cb(stage_name: str) -> None:
        job_queue.update_stage(session, job.id, stage_name)

    run_document_embedding(
        session=session,
        document_id=job.document_id,
        stage_callback=_stage_cb,
    )


JOB_HANDLERS: dict[str, JobHandler] = {
    JobType.PARSE.value: handle_parse_job,
    JobType.EXTRACTION.value: handle_extraction_job,
    JobType.EMBEDDING.value: handle_embedding_job,
}


def register_job_handler(job_type: str, handler: JobHandler) -> None:
    JOB_HANDLERS[job_queue.normalize_job_type(job_type)] = handler


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def process_one_job(
    session_factory: sessionmaker[Session],
    worker_id: Optional[str] = None,
    backoff_base_seconds: float = 5.0,
) -> bool:
    wid = worker_id or default_worker_id()

    with session_factory() as session:
        try:
            requeued = job_queue.requeue_stale(
                session, stale_minutes=settings.JOB_STALE_MINUTES
            )
            if requeued:
                logger.info(
                    "Requeued %d stale job(s) | worker_id=%s job_id=none document_id=none",
                    requeued,
                    wid,
                )
        except Exception as exc:
            session.rollback()
            logger.warning(
                "Error requeueing stale jobs: %s | worker_id=%s job_id=none document_id=none",
                exc,
                wid,
            )

        job = job_queue.claim_next(session, worker_id=wid)
        if job is None:
            return False

        job_id = job.id
        doc_id = job.document_id
        job_type = job_queue.normalize_job_type(job.job_type)
        attempt = job.attempts

    logger.info(
        "Claimed job | worker_id=%s job_id=%s document_id=%s job_type=%s attempt=%d",
        wid,
        job_id,
        doc_id,
        job_type,
        attempt,
    )

    handler = JOB_HANDLERS.get(job_type)
    if handler is None:
        with session_factory() as session:
            readable_err = f"Unsupported job_type '{job.job_type}'"
            job_queue.mark_failed(
                session,
                job_id=job_id,
                error=readable_err,
                backoff_base_seconds=backoff_base_seconds,
                permanent=True,
            )
        logger.error(
            "No handler for job | worker_id=%s job_id=%s document_id=%s error=%s",
            wid,
            job_id,
            doc_id,
            readable_err,
        )
        return True

    with session_factory() as session:
        job_obj = session.get(ProcessingJob, job_id)
        if job_obj is None:
            return False

        try:
            handler(session, job_obj)
            job_queue.mark_succeeded(session, job_id=job_id)
            logger.info(
                "Job succeeded | worker_id=%s job_id=%s document_id=%s job_type=%s",
                wid,
                job_id,
                doc_id,
                job_type,
            )
        except PermanentAIError as exc:
            session.rollback()
            readable_err = str(exc) or "Permanent AI provider or schema error"
            updated = job_queue.mark_failed(
                session,
                job_id=job_id,
                error=readable_err,
                backoff_base_seconds=backoff_base_seconds,
                permanent=True,
            )
            logger.warning(
                "Job failed permanently | worker_id=%s job_id=%s document_id=%s job_type=%s status=%s error=%s",
                wid,
                job_id,
                doc_id,
                job_type,
                updated.status if updated else "unknown",
                readable_err,
            )
        except TransientAIError as exc:
            session.rollback()
            readable_err = str(exc) or "Transient AI provider error"
            updated = job_queue.mark_failed(
                session,
                job_id=job_id,
                error=readable_err,
                backoff_base_seconds=backoff_base_seconds,
                permanent=False,
            )
            logger.warning(
                "Job failed with transient AI error | worker_id=%s job_id=%s document_id=%s job_type=%s status=%s error=%s",
                wid,
                job_id,
                doc_id,
                job_type,
                updated.status if updated else "unknown",
                readable_err,
            )
        except DocumentParseError as exc:
            session.rollback()
            readable_err = str(exc) or "Document parsing failed"
            updated = job_queue.mark_failed(
                session,
                job_id=job_id,
                error=readable_err,
                backoff_base_seconds=backoff_base_seconds,
                permanent=False,
            )
            logger.warning(
                "Job failed with parse error | worker_id=%s job_id=%s document_id=%s status=%s error=%s",
                wid,
                job_id,
                doc_id,
                updated.status if updated else "unknown",
                readable_err,
            )
        except Exception as exc:
            session.rollback()
            readable_err = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
            updated = job_queue.mark_failed(
                session,
                job_id=job_id,
                error=readable_err,
                backoff_base_seconds=backoff_base_seconds,
                permanent=False,
            )
            logger.error(
                "Job failed with unexpected error | worker_id=%s job_id=%s document_id=%s status=%s error=%s",
                wid,
                job_id,
                doc_id,
                updated.status if updated else "unknown",
                readable_err,
            )

    return True


def run_worker(
    session_factory: sessionmaker[Session],
    poll_seconds: Optional[float] = None,
    run_once: bool = False,
    worker_id: Optional[str] = None,
) -> None:
    interval = poll_seconds if poll_seconds is not None else settings.WORKER_POLL_SECONDS
    wid = worker_id or default_worker_id()
    shutdown_requested = False

    def _on_signal(signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        logger.info(
            "Shutdown signal %d received | worker_id=%s job_id=none document_id=none",
            signum,
            wid,
        )
        shutdown_requested = True

    signal.signal(signal.SIGINT, _on_signal)
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _on_signal)
    else:
        signal.signal(signal.SIGTERM, _on_signal)

    logger.info(
        "Worker started | worker_id=%s job_id=none document_id=none poll_seconds=%.2f",
        wid,
        interval,
    )

    if run_once:
        process_one_job(session_factory=session_factory, worker_id=wid)
        return

    while not shutdown_requested:
        try:
            processed = process_one_job(session_factory=session_factory, worker_id=wid)
            if not processed and not shutdown_requested:
                time.sleep(interval)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.error(
                "Worker loop error: %s | worker_id=%s job_id=none document_id=none",
                exc,
                wid,
            )
            if not shutdown_requested:
                time.sleep(interval)

    logger.info(
        "Worker stopped cleanly | worker_id=%s job_id=none document_id=none",
        wid,
    )
