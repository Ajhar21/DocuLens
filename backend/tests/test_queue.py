from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import threading
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.document import Document, DocumentStatus
from app.models.job import JobStatus, ProcessingJob
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name
from app.services import job_queue

_created_queue_user_ids: list[uuid.UUID] = []


def _seed_doc(session: Session) -> Document:
    role_obj = get_role_by_name(session, RoleName.SYSTEM_ADMIN.value)
    user = User(
        email=f"test-queue-user-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Queue Tester",
        password_hash=hash_password("TestPass123!"),
        role_id=role_obj.id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    _created_queue_user_ids.append(user.id)

    doc = Document(
        original_filename="test.pdf",
        stored_path="documents/test/original.pdf",
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=128,
        sha256="a" * 64,
        status=DocumentStatus.UPLOADED.value,
        uploaded_by=user.id,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


@pytest.fixture(autouse=True)
def cleanup_queue_test_users(test_sessionmaker: sessionmaker[Session]) -> Generator[None, None, None]:
    yield
    with test_sessionmaker() as session:
        while _created_queue_user_ids:
            user_id = _created_queue_user_ids.pop()
            doc_ids_subq = select(Document.id).where(Document.uploaded_by == user_id)
            session.execute(delete(ProcessingJob).where(ProcessingJob.document_id.in_(doc_ids_subq)))
            session.execute(delete(Document).where(Document.uploaded_by == user_id))
            session.execute(delete(User).where(User.id == user_id))
        session.commit()


def test_claim_next_concurrent_single_winner(
    test_sessionmaker: sessionmaker[Session],
) -> None:
    with test_sessionmaker() as setup_session:
        doc = _seed_doc(setup_session)
        enqueued = job_queue.enqueue(setup_session, document_id=doc.id)
        job_id = enqueued.id

    barrier = threading.Barrier(2)
    claimed_ids: list[uuid.UUID | None] = []
    lock = threading.Lock()

    def _claimer(worker_name: str) -> None:
        with test_sessionmaker() as session:
            barrier.wait()
            claimed = job_queue.claim_next(session, worker_id=worker_name)
            with lock:
                claimed_ids.append(claimed.id if claimed is not None else None)

    t1 = threading.Thread(target=_claimer, args=("worker-1",))
    t2 = threading.Thread(target=_claimer, args=("worker-2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [cid for cid in claimed_ids if cid is not None]
    assert len(winners) == 1
    assert winners[0] == job_id
    assert claimed_ids.count(None) == 1


def test_retry_backoff_and_max_attempts(db: Session) -> None:
    doc = _seed_doc(db)
    job = job_queue.enqueue(db, document_id=doc.id, max_attempts=2)

    claimed_1 = job_queue.claim_next(db, worker_id="worker-a")
    assert claimed_1 is not None
    assert claimed_1.attempts == 1
    assert claimed_1.status == JobStatus.RUNNING.value

    before_fail = datetime.now(timezone.utc)
    after_fail_1 = job_queue.mark_failed(
        db,
        job_id=job.id,
        error="Transient parse error",
        backoff_base_seconds=10.0,
    )
    assert after_fail_1 is not None
    assert after_fail_1.status == JobStatus.PENDING.value
    assert after_fail_1.last_error == "Transient parse error"
    assert after_fail_1.run_after >= before_fail + timedelta(seconds=9)

    after_fail_1.run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    claimed_2 = job_queue.claim_next(db, worker_id="worker-a")
    assert claimed_2 is not None
    assert claimed_2.attempts == 2

    after_fail_2 = job_queue.mark_failed(
        db,
        job_id=job.id,
        error="Permanent failure on final attempt",
        backoff_base_seconds=10.0,
    )
    assert after_fail_2 is not None
    assert after_fail_2.status == JobStatus.FAILED.value
    assert after_fail_2.finished_at is not None

    db.refresh(doc)
    assert doc.status == DocumentStatus.FAILED.value
    assert doc.error == "Permanent failure on final attempt"


def test_requeue_stale_running_jobs(db: Session) -> None:
    doc = _seed_doc(db)
    job = job_queue.enqueue(db, document_id=doc.id)

    claimed = job_queue.claim_next(db, worker_id="stale-worker")
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING.value

    claimed.locked_at = datetime.now(timezone.utc) - timedelta(minutes=25)
    db.commit()

    requeued_count = job_queue.requeue_stale(db, stale_minutes=10)
    assert requeued_count == 1

    db.refresh(claimed)
    assert claimed.status == JobStatus.PENDING.value
    assert claimed.locked_by is None
    assert claimed.locked_at is None
