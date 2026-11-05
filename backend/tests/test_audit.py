from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
from typing import Generator
import uuid

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.extraction import DocumentCorrection, ExtractedInvoice
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import RoleName, User
from app.models.validation import ValidationResult, ValidationSeverity, ValidationStatus
from app.repositories.user_repo import get_role_by_name
from app.services.audit_service import AuditService
from app.services.storage import storage_service

_test_user_ids: list[uuid.UUID] = []


def _seed_user(db: Session, role_name: RoleName) -> tuple[User, str]:
    role_obj = get_role_by_name(db, role_name.value)
    assert role_obj is not None
    uid = uuid.uuid4().hex[:8]
    password = "TestPassword123!"
    user = User(
        email=f"audit_{role_name.value.lower()}_{uid}@example.com",
        full_name=f"Audit {role_name.value}",
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


@pytest.fixture(autouse=True)
def cleanup_audit_users(db: Session) -> Generator[None, None, None]:
    yield
    db.rollback()
    while _test_user_ids:
        uid = _test_user_ids.pop()
        db.execute(delete(DocumentCorrection).where(DocumentCorrection.corrected_by == uid))
        db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
        doc_ids = db.execute(select(Document.id).where(Document.uploaded_by == uid)).scalars().all()
        for did in doc_ids:
            db.execute(delete(DocumentCorrection).where(DocumentCorrection.document_id == did))
            db.execute(delete(DocumentParseResult).where(DocumentParseResult.document_id == did))
            db.execute(delete(ExtractedInvoice).where(ExtractedInvoice.document_id == did))
            db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == did))
            db.execute(delete(ValidationResult).where(ValidationResult.document_id == did))
            db.execute(delete(Document).where(Document.id == did))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def test_document_history_unified_timeline(client: TestClient, db: Session) -> None:
    """Verify GET /api/v1/documents/{id}/history synthesizes events across multiple tables."""
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)

    exec_headers = _login_headers(client, exec_user.email, exec_pwd)
    mgr_headers = _login_headers(client, mgr_user.email, mgr_pwd)

    # 1. Create document uploaded by executive
    doc_id = uuid.uuid4()
    stored = storage_service.save_stream(
        stream=io.BytesIO(b"%PDF-1.4 sample invoice content"),
        document_id=doc_id,
        ext=".pdf",
        max_bytes=10 * 1024 * 1024,
    )
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    doc = Document(
        id=doc_id,
        original_filename="sample_inv.pdf",
        stored_path=stored.stored_path,
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.PARSED.value,
        review_status="needs_review",
        uploaded_by=exec_user.id,
        created_at=t0,
    )
    db.add(doc)
    db.flush()

    # 2. Add processing jobs
    t1 = t0 + timedelta(minutes=1)
    t2 = t0 + timedelta(minutes=2)
    job1 = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.SUCCEEDED.value,
        attempts=1,
        created_at=t1,
        completed_at=t2,
    )
    db.add(job1)

    # 3. Add deterministic validation results
    t3 = t0 + timedelta(minutes=3)
    val1 = ValidationResult(
        document_id=doc.id,
        validation_code="TOTAL_MISMATCH",
        field_name="total",
        severity=ValidationSeverity.ERROR.value,
        status=ValidationStatus.FAILED.value,
        message="Total mismatch detected",
        expected_value="100.00",
        actual_value="120.00",
        created_at=t3,
    )
    val2 = ValidationResult(
        document_id=doc.id,
        validation_code="MISSING_REQUIRED_FIELD",
        field_name="invoice_number",
        severity=ValidationSeverity.ERROR.value,
        status=ValidationStatus.PASSED.value,
        message="Invoice number present",
        created_at=t3,
    )
    db.add_all([val1, val2])

    # 4. Add human correction by executive
    t4 = t0 + timedelta(minutes=4)
    corr = DocumentCorrection(
        document_id=doc.id,
        field_name="total",
        original_value="120.00",
        corrected_value="100.00",
        corrected_by=exec_user.id,
        correction_reason="Corrected OCR error",
        created_at=t4,
    )
    db.add(corr)

    # 5. Record approval audit log by manager
    t5 = t0 + timedelta(minutes=5)
    AuditService.record(
        db,
        user_id=mgr_user.id,
        action="document:review:approved",
        entity_type="document",
        entity_id=doc.id,
        old_values={"review_status": "corrected"},
        new_values={"review_status": "approved"},
    )
    db.commit()

    # Query document history as Finance Executive
    resp = client.get(f"/api/v1/documents/{doc.id}/history", headers=exec_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["document_id"] == str(doc.id)
    events = data["events"]
    assert len(events) >= 5

    # Verify chronological sorting: newest first
    event_timestamps = [e["timestamp"] for e in events]
    assert event_timestamps == sorted(event_timestamps, reverse=True)

    # Verify event types present
    event_types = {e["event_type"] for e in events}
    assert "document:uploaded" in event_types
    assert "job:parse:queued" in event_types
    assert "job:parse:succeeded" in event_types
    assert "validation:evaluated" in event_types
    assert "correction:submitted" in event_types
    assert "document:review:approved" in event_types

    # Verify actors
    upload_event = next(e for e in events if e["event_type"] == "document:uploaded")
    assert upload_event["actor"]["email"] == exec_user.email
    assert upload_event["actor"]["role"] == RoleName.FINANCE_EXECUTIVE.value

    corr_event = next(e for e in events if e["event_type"] == "correction:submitted")
    assert corr_event["actor"]["email"] == exec_user.email
    assert corr_event["details"]["field_name"] == "total"
    assert corr_event["details"]["corrected_value"] == "100.00"

    approve_event = next(e for e in events if e["event_type"] == "document:review:approved")
    assert approve_event["actor"]["email"] == mgr_user.email
    assert approve_event["actor"]["role"] == RoleName.FINANCE_MANAGER.value


def test_document_history_not_found(client: TestClient, db: Session) -> None:
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)
    resp = client.get(f"/api/v1/documents/{uuid.uuid4()}/history", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_global_audit_logs_pagination_and_filtering(client: TestClient, db: Session) -> None:
    """Verify GET /api/v1/audit-logs pagination and filtering."""
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    mgr_headers = _login_headers(client, mgr_user.email, mgr_pwd)

    # Insert test audit logs
    target_entity_id = uuid.uuid4()
    for i in range(5):
        AuditService.record(
            db,
            user_id=mgr_user.id,
            action=f"custom:test_action_{i}",
            entity_type="test_entity",
            entity_id=target_entity_id,
            new_values={"index": i},
        )
    db.commit()

    # 1. Unfiltered paginated list
    page1 = client.get("/api/v1/audit-logs?page=1&page_size=2", headers=mgr_headers)
    assert page1.status_code == 200
    data1 = page1.json()["data"]
    assert len(data1["items"]) == 2
    assert data1["pagination"]["page"] == 1
    assert data1["pagination"]["page_size"] == 2
    assert data1["pagination"]["total"] >= 5

    # 2. Filter by entity_type and entity_id
    filtered = client.get(
        f"/api/v1/audit-logs?entity_type=test_entity&entity_id={target_entity_id}",
        headers=mgr_headers,
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()["data"]
    assert filtered_data["pagination"]["total"] == 5
    for item in filtered_data["items"]:
        assert item["entity_type"] == "test_entity"
        assert item["entity_id"] == str(target_entity_id)

    # 3. Filter by specific action
    act_resp = client.get(
        f"/api/v1/audit-logs?action=custom:test_action_3",
        headers=mgr_headers,
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["data"]["pagination"]["total"] == 1
    assert act_resp.json()["data"]["items"][0]["action"] == "custom:test_action_3"


def test_audit_logs_role_permissions(client: TestClient, db: Session) -> None:
    """Verify Executive gets 403 on global audit-logs but Manager, Audit, Admin get 200."""
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    audit_user, audit_pwd = _seed_user(db, RoleName.ACCOUNTS_AUDIT)
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)

    exec_h = _login_headers(client, exec_user.email, exec_pwd)
    mgr_h = _login_headers(client, mgr_user.email, mgr_pwd)
    audit_h = _login_headers(client, audit_user.email, audit_pwd)
    admin_h = _login_headers(client, admin_user.email, admin_pwd)

    # Unauthenticated -> 401
    assert client.get("/api/v1/audit-logs").status_code == 401

    # Executive -> 403 Forbidden
    exec_resp = client.get("/api/v1/audit-logs", headers=exec_h)
    assert exec_resp.status_code == 403
    assert "audit:view" in exec_resp.json()["message"]

    # Manager -> 200 OK
    assert client.get("/api/v1/audit-logs", headers=mgr_h).status_code == 200

    # Accounts Audit -> 200 OK
    assert client.get("/api/v1/audit-logs", headers=audit_h).status_code == 200

    # System Admin -> 200 OK
    assert client.get("/api/v1/audit-logs", headers=admin_h).status_code == 200

