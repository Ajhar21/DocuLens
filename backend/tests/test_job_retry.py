from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import io
import uuid

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.extraction import ExtractedInvoice
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name
from app.services.storage import storage_service
from app.worker.runner import process_one_job

_test_user_ids: list[uuid.UUID] = []


def _seed_user(db: Session, role_name: RoleName) -> tuple[User, str]:
    role_obj = get_role_by_name(db, role_name.value)
    assert role_obj is not None
    uid = uuid.uuid4().hex[:8]
    password = "TestPassword123!"
    user = User(
        email=f"job_{role_name.value.lower()}_{uid}@example.com",
        full_name=f"Job Tester {role_name.value}",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _test_user_ids.append(user.id)
    return user, password


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_test_document(db: Session, user: User, content: bytes = b"%PDF-1.4 test invoice") -> Document:
    doc_id = uuid.uuid4()
    stored = storage_service.save_stream(
        stream=io.BytesIO(content),
        document_id=doc_id,
        ext=".pdf",
        max_bytes=10 * 1024 * 1024,
    )
    doc = Document(
        id=doc_id,
        original_filename="sample_inv.pdf",
        stored_path=stored.stored_path,
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.FAILED.value,
        review_status="needs_review",
        uploaded_by=user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture(autouse=True)
def cleanup_job_test_data(db: Session) -> Generator[None, None, None]:
    yield
    db.rollback()
    while _test_user_ids:
        uid = _test_user_ids.pop()
        db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
        doc_ids = db.execute(select(Document.id).where(Document.uploaded_by == uid)).scalars().all()
        for did in doc_ids:
            db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == did))
            db.execute(delete(DocumentParseResult).where(DocumentParseResult.document_id == did))
            db.execute(delete(ExtractedInvoice).where(ExtractedInvoice.document_id == did))
            db.execute(delete(Document).where(Document.id == did))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def test_retry_failed_job_resets_in_place_and_records_audit(client: TestClient, db: Session) -> None:
    """Verify failed job retry resets fields in-place and writes audit log."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, admin_user.email, admin_pwd)

    doc = _seed_test_document(db, admin_user)

    # Create a failed job
    failed_job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.FAILED.value,
        attempts=3,
        max_attempts=3,
        last_error="Network timeout during LLM parse",
        current_stage="parsing",
    )
    db.add(failed_job)
    db.commit()
    db.refresh(failed_job)
    original_job_id = failed_job.id

    # Call retry
    resp = client.post(f"/api/v1/jobs/{original_job_id}/retry", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Verify response
    assert data["id"] == str(original_job_id)
    assert data["status"] == "pending"
    assert data["attempts"] == 0
    assert data["error_message"] is None

    # Verify DB state updated in-place (no new row created)
    db.expire_all()
    job_rows = db.scalars(
        select(ProcessingJob).where(ProcessingJob.document_id == doc.id)
    ).all()
    assert len(job_rows) == 1
    retried_job = job_rows[0]
    assert retried_job.id == original_job_id
    assert retried_job.status == JobStatus.PENDING.value
    assert retried_job.attempts == 0
    assert retried_job.last_error is None

    # Verify document was updated back to processing
    refreshed_doc = db.get(Document, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.status == DocumentStatus.PROCESSING.value

    # Verify audit log entry
    audit_entry = db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "processing_job",
            AuditLog.entity_id == original_job_id,
            AuditLog.action == "job:retry",
        )
    ).scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.user_id == admin_user.id
    assert audit_entry.old_values["status"] == JobStatus.FAILED.value
    assert audit_entry.old_values["attempts"] == 3
    assert audit_entry.old_values["last_error"] == "Network timeout during LLM parse"
    assert audit_entry.new_values["status"] == JobStatus.PENDING.value
    assert audit_entry.new_values["attempts"] == 0


def test_retry_non_failed_jobs_return_409(client: TestClient, db: Session) -> None:
    """Verify jobs in pending, running, or succeeded status reject retry with 409."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, admin_user.email, admin_pwd)

    doc = _seed_test_document(db, admin_user)

    for st in (JobStatus.PENDING.value, JobStatus.RUNNING.value, JobStatus.SUCCEEDED.value):
        job = ProcessingJob(
            document_id=doc.id,
            job_type=JobType.EXTRACTION.value,
            status=st,
            attempts=1,
        )
        db.add(job)
        db.commit()

        resp = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
        assert resp.status_code == 409, f"Status {st} should return 409 Conflict, got {resp.status_code}"
        assert "Only failed jobs can be retried" in resp.json()["message"]

        db.delete(job)
        db.commit()


def test_retry_active_job_conflict_returns_409(client: TestClient, db: Session) -> None:
    """Verify 409 if another active job for the same document and job_type exists."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, admin_user.email, admin_pwd)

    doc = _seed_test_document(db, admin_user)

    # 1. Existing active job (pending)
    active_job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.PENDING.value,
    )
    # 2. Failed job for same doc and type (from an earlier run)
    failed_job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.FAILED.value,
        attempts=3,
    )
    db.add_all([active_job, failed_job])
    db.commit()

    resp = client.post(f"/api/v1/jobs/{failed_job.id}/retry", headers=headers)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"]


def test_jobs_endpoints_rbac(client: TestClient, db: Session) -> None:
    """Verify non-admin roles get 403 on job endpoints while SYSTEM_ADMIN gets 200."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    audit_user, audit_pwd = _seed_user(db, RoleName.ACCOUNTS_AUDIT)

    admin_h = _login_headers(client, admin_user.email, admin_pwd)
    exec_h = _login_headers(client, exec_user.email, exec_pwd)
    mgr_h = _login_headers(client, mgr_user.email, mgr_pwd)
    audit_h = _login_headers(client, audit_user.email, audit_pwd)

    doc = _seed_test_document(db, admin_user)
    job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.FAILED.value,
    )
    db.add(job)
    db.commit()

    # GET /api/v1/jobs
    assert client.get("/api/v1/jobs").status_code == 401
    assert client.get("/api/v1/jobs", headers=exec_h).status_code == 403
    assert client.get("/api/v1/jobs", headers=mgr_h).status_code == 403
    assert client.get("/api/v1/jobs", headers=audit_h).status_code == 403
    assert client.get("/api/v1/jobs", headers=admin_h).status_code == 200

    # GET /api/v1/jobs/{id}
    assert client.get(f"/api/v1/jobs/{job.id}").status_code == 401
    assert client.get(f"/api/v1/jobs/{job.id}", headers=exec_h).status_code == 403
    assert client.get(f"/api/v1/jobs/{job.id}", headers=mgr_h).status_code == 403
    assert client.get(f"/api/v1/jobs/{job.id}", headers=audit_h).status_code == 403
    assert client.get(f"/api/v1/jobs/{job.id}", headers=admin_h).status_code == 200

    # POST /api/v1/jobs/{id}/retry
    assert client.post(f"/api/v1/jobs/{job.id}/retry").status_code == 401
    assert client.post(f"/api/v1/jobs/{job.id}/retry", headers=exec_h).status_code == 403
    assert client.post(f"/api/v1/jobs/{job.id}/retry", headers=mgr_h).status_code == 403
    assert client.post(f"/api/v1/jobs/{job.id}/retry", headers=audit_h).status_code == 403
    assert client.post(f"/api/v1/jobs/{job.id}/retry", headers=admin_h).status_code == 200


def test_job_retry_worker_pickup_integration(
    client: TestClient,
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    """End-to-end integration: failed parse job -> retry -> worker processes it to completion."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, admin_user.email, admin_pwd)

    # Create a real readable CSV document
    doc_id = uuid.uuid4()
    stored = storage_service.save_stream(
        stream=io.BytesIO(b"invoice_number,amount\nINV-RETRY-001,500.00\n"),
        document_id=doc_id,
        ext=".csv",
        max_bytes=10 * 1024 * 1024,
    )
    doc = Document(
        id=doc_id,
        original_filename="retry_test.csv",
        stored_path=stored.stored_path,
        content_type="text/csv",
        file_ext=".csv",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.FAILED.value,
        uploaded_by=admin_user.id,
    )
    db.add(doc)

    failed_job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.FAILED.value,
        attempts=3,
        last_error="Simulated network transient error",
    )
    db.add(failed_job)
    db.commit()

    # 1. Retry via API
    resp = client.post(f"/api/v1/jobs/{failed_job.id}/retry", headers=headers)
    assert resp.status_code == 200

    # 2. Worker executes the claimed job
    processed = process_one_job(test_sessionmaker, worker_id="test_worker_1")
    assert processed is True

    # 3. Verify job succeeded and document is parsed
    db.expire_all()
    job_db = db.get(ProcessingJob, failed_job.id)
    assert job_db is not None
    assert job_db.status == JobStatus.SUCCEEDED.value

    doc_db = db.get(Document, doc.id)
    assert doc_db is not None
    assert doc_db.status == DocumentStatus.PARSED.value

    # 4. Verify exactly one parse result row exists (no duplicate parse results)
    parse_results = db.scalars(
        select(DocumentParseResult).where(DocumentParseResult.document_id == doc.id)
    ).all()
    assert len(parse_results) == 1
    assert parse_results[0].tables is not None
