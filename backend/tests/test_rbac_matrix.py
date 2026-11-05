from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from typing import Optional
import uuid

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.extraction import DocumentCorrection, ExtractedInvoice
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.reconciliation import ReconciliationJob, ReconciliationResult
from app.models.user import RoleName, User
from app.models.validation import ValidationResult
from app.repositories.user_repo import get_role_by_name
from app.services import document_service
from app.services.storage import storage_service

_rbac_user_ids: list[uuid.UUID] = []


def _seed_role_user(
    db: Session,
    role: RoleName,
    *,
    is_active: bool = True,
) -> tuple[User, str]:
    uid = uuid.uuid4().hex[:8]
    password = "TestPassword123!"
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=f"rbac-{role.value.lower()}-{uid}@example.com",
        full_name=f"RBAC {role.value}",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _rbac_user_ids.append(user.id)
    return user, password


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def cleanup_rbac_test_users(db: Session) -> Generator[None, None, None]:
    yield
    db.rollback()
    while _rbac_user_ids:
        uid = _rbac_user_ids.pop()
        db.execute(delete(DocumentCorrection).where(DocumentCorrection.corrected_by == uid))
        db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
        doc_ids = db.execute(select(Document.id).where(Document.uploaded_by == uid)).scalars().all()
        for did in doc_ids:
            recon_job_ids = db.execute(
                select(ReconciliationJob.id).where(
                    (ReconciliationJob.document_id_a == did) | (ReconciliationJob.document_id_b == did)
                )
            ).scalars().all()
            for rjid in recon_job_ids:
                db.execute(delete(ReconciliationResult).where(ReconciliationResult.job_id == rjid))
                db.execute(delete(ReconciliationJob).where(ReconciliationJob.id == rjid))

            db.execute(delete(DocumentCorrection).where(DocumentCorrection.document_id == did))
            db.execute(delete(DocumentParseResult).where(DocumentParseResult.document_id == did))
            db.execute(delete(ExtractedInvoice).where(ExtractedInvoice.document_id == did))
            db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == did))
            db.execute(delete(ValidationResult).where(ValidationResult.document_id == did))
            db.execute(delete(Document).where(Document.id == did))
        recon_user_jobs = db.execute(select(ReconciliationJob.id).where(ReconciliationJob.initiated_by == uid)).scalars().all()
        for rjid in recon_user_jobs:
            db.execute(delete(ReconciliationResult).where(ReconciliationResult.job_id == rjid))
            db.execute(delete(ReconciliationJob).where(ReconciliationJob.id == rjid))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def test_startup_seeds_env_admin_idempotently(client: TestClient, db: Session) -> None:
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    seeded_admin = db.execute(
        select(User).where(User.email == admin_email)
    ).scalar_one_or_none()
    assert seeded_admin is not None
    assert seeded_admin.role_name == RoleName.SYSTEM_ADMIN.value
    assert seeded_admin.is_active is True

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["user"]["role"] == RoleName.SYSTEM_ADMIN.value


@pytest.mark.parametrize(
    "endpoint_key,expected_by_role",
    [
        (
            "GET /api/v1/auth/me",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/auth/logout",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/users",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/users",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 201,
            },
        ),
        (
            "GET /api/v1/users/{id}",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "PATCH /api/v1/users/{id}",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "PATCH /api/v1/users/{id}/role",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "PATCH /api/v1/users/{id}/status",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/documents/upload",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 201,
                RoleName.FINANCE_MANAGER: 201,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 201,
            },
        ),
        (
            "GET /api/v1/documents",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}/status",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}/extraction",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}/validation",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}/file",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/documents/{id}/reprocess",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 202,
                RoleName.FINANCE_MANAGER: 202,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 202,
            },
        ),
        (
            "GET /api/v1/jobs",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/jobs/{id}",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/jobs/{id}/retry",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/reviews",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/reviews/{id}",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "PATCH /api/v1/reviews/{id}/corrections",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/reviews/{id}/approve",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/reviews/{id}/reject",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/documents/{id}/history",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/audit-logs",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/reconciliations/pdf-pdf",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 201,
                RoleName.FINANCE_MANAGER: 201,
                RoleName.ACCOUNTS_AUDIT: 201,
                RoleName.SYSTEM_ADMIN: 201,
            },
        ),
        (
            "GET /api/v1/reconciliations",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "GET /api/v1/search",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 200,
                RoleName.FINANCE_MANAGER: 200,
                RoleName.ACCOUNTS_AUDIT: 200,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
    ],
)
def test_rbac_permission_matrix(
    client: TestClient,
    db: Session,
    endpoint_key: str,
    expected_by_role: dict[Optional[RoleName], int],
) -> None:
    target_user, _ = _seed_role_user(db, RoleName.FINANCE_EXECUTIVE)
    uploader, _ = _seed_role_user(db, RoleName.FINANCE_EXECUTIVE)

    import io

    doc_id = uuid.uuid4()
    stored = storage_service.save_stream(
        stream=io.BytesIO(b"col1,col2\n1,2\n"),
        document_id=doc_id,
        ext=".csv",
        max_bytes=10 * 1024 * 1024,
    )
    doc = Document(
        id=doc_id,
        original_filename="matrix.csv",
        stored_path=stored.stored_path,
        content_type="text/csv",
        file_ext=".csv",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.PARSED.value,
        uploaded_by=uploader.id,
    )
    db.add(doc)
    db.flush()
    db.add(
        DocumentParseResult(
            document_id=doc.id,
            pages=[],
            tables=[{"name": "original", "columns": ["col1", "col2"], "rows": [["1", "2"]]}],
            doc_metadata={"format": "csv"},
            ocr_used=False,
        )
    )
    inv = ExtractedInvoice(
        document_id=doc.id,
        invoice_number="INV-MAT-1",
        total=Decimal("100.0000"),
        extraction_metadata={"raw_llm_output": {"invoice_number": "INV-MAT-1"}},
    )
    db.add(inv)
    job = ProcessingJob(
        document_id=doc.id,
        job_type=JobType.PARSE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job)
    db.commit()

    for role, expected_status in expected_by_role.items():
        db.execute(
            sa.update(Document).where(Document.id == doc.id).values(review_status="pending")
        )
        db.commit()

        if role is None:
            headers: dict[str, str] = {}
        else:
            actor, pwd = _seed_role_user(db, role)
            headers = _login(client, actor.email, pwd)

        if endpoint_key == "GET /api/v1/auth/me":
            resp = client.get("/api/v1/auth/me", headers=headers)
        elif endpoint_key == "POST /api/v1/auth/logout":
            resp = client.post("/api/v1/auth/logout", headers=headers)
        elif endpoint_key == "GET /api/v1/users":
            resp = client.get("/api/v1/users", headers=headers)
        elif endpoint_key == "POST /api/v1/users":
            new_email = f"created-{uuid.uuid4().hex[:8]}@example.com"
            resp = client.post(
                "/api/v1/users",
                headers=headers,
                json={
                    "email": new_email,
                    "full_name": "Created User",
                    "password": "Password123!",
                    "role": "ACCOUNTS_AUDIT",
                },
            )
            if resp.status_code == 201:
                _rbac_user_ids.append(uuid.UUID(resp.json()["data"]["id"]))
        elif endpoint_key == "GET /api/v1/users/{id}":
            resp = client.get(f"/api/v1/users/{target_user.id}", headers=headers)
        elif endpoint_key == "PATCH /api/v1/users/{id}":
            resp = client.patch(
                f"/api/v1/users/{target_user.id}",
                headers=headers,
                json={"full_name": "Patched Name"},
            )
        elif endpoint_key == "PATCH /api/v1/users/{id}/role":
            resp = client.patch(
                f"/api/v1/users/{target_user.id}/role",
                headers=headers,
                json={"role": "FINANCE_MANAGER"},
            )
        elif endpoint_key == "PATCH /api/v1/users/{id}/status":
            resp = client.patch(
                f"/api/v1/users/{target_user.id}/status",
                headers=headers,
                json={"is_active": True},
            )
        elif endpoint_key == "POST /api/v1/documents/upload":
            resp = client.post(
                "/api/v1/documents/upload",
                headers=headers,
                files=[("files", ("up.csv", b"a,b\n1,2\n", "text/csv"))],
            )
        elif endpoint_key == "GET /api/v1/documents":
            resp = client.get("/api/v1/documents", headers=headers)
        elif endpoint_key == "GET /api/v1/documents/{id}":
            resp = client.get(f"/api/v1/documents/{doc.id}", headers=headers)
        elif endpoint_key == "GET /api/v1/documents/{id}/status":
            resp = client.get(f"/api/v1/documents/{doc.id}/status", headers=headers)
        elif endpoint_key == "GET /api/v1/documents/{id}/extraction":
            resp = client.get(f"/api/v1/documents/{doc.id}/extraction", headers=headers)
        elif endpoint_key == "GET /api/v1/documents/{id}/validation":
            resp = client.get(f"/api/v1/documents/{doc.id}/validation", headers=headers)
        elif endpoint_key == "GET /api/v1/documents/{id}/file":
            resp = client.get(f"/api/v1/documents/{doc.id}/file", headers=headers)
        elif endpoint_key == "POST /api/v1/documents/{id}/reprocess":
            resp = client.post(
                f"/api/v1/documents/{doc.id}/reprocess?stage=extraction",
                headers=headers,
            )
        elif endpoint_key == "GET /api/v1/jobs":
            resp = client.get("/api/v1/jobs", headers=headers)
        elif endpoint_key == "GET /api/v1/jobs/{id}":
            resp = client.get(f"/api/v1/jobs/{job.id}", headers=headers)
        elif endpoint_key == "POST /api/v1/jobs/{id}/retry":
            db.execute(
                sa.update(ProcessingJob)
                .where(ProcessingJob.id == job.id)
                .values(status="failed")
            )
            db.commit()
            resp = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
        elif endpoint_key == "GET /api/v1/reviews":
            resp = client.get("/api/v1/reviews", headers=headers)
        elif endpoint_key == "GET /api/v1/reviews/{id}":
            resp = client.get(f"/api/v1/reviews/{doc.id}", headers=headers)
        elif endpoint_key == "PATCH /api/v1/reviews/{id}/corrections":
            resp = client.patch(
                f"/api/v1/reviews/{doc.id}/corrections",
                headers=headers,
                json=[{"field_name": "supplier_name", "corrected_value": "Supplier Matrix"}],
            )
        elif endpoint_key == "POST /api/v1/reviews/{id}/approve":
            resp = client.post(f"/api/v1/reviews/{doc.id}/approve", headers=headers)
        elif endpoint_key == "POST /api/v1/reviews/{id}/reject":
            resp = client.post(
                f"/api/v1/reviews/{doc.id}/reject",
                headers=headers,
                json={"reason": "Matrix test rejection"},
            )
        elif endpoint_key == "GET /api/v1/documents/{id}/history":
            resp = client.get(f"/api/v1/documents/{doc.id}/history", headers=headers)
        elif endpoint_key == "GET /api/v1/audit-logs":
            resp = client.get("/api/v1/audit-logs", headers=headers)
        elif endpoint_key == "POST /api/v1/reconciliations/pdf-pdf":
            resp = client.post(
                "/api/v1/reconciliations/pdf-pdf",
                headers=headers,
                json={"document_id_a": str(doc.id), "document_id_b": str(doc.id)},
            )
        elif endpoint_key == "GET /api/v1/reconciliations":
            resp = client.get("/api/v1/reconciliations", headers=headers)
        elif endpoint_key == "GET /api/v1/search":
            resp = client.get("/api/v1/search?q=invoice", headers=headers)
        else:
            raise AssertionError(f"Unhandled endpoint_key: {endpoint_key}")

        assert resp.status_code == expected_status, (
            f"{endpoint_key} with role={role}: expected {expected_status}, "
            f"got {resp.status_code} ({resp.text})"
        )


def test_admin_guards_self_demote_self_deactivate_and_last_admin(
    client: TestClient,
    db: Session,
) -> None:
    admin1, pwd1 = _seed_role_user(db, RoleName.SYSTEM_ADMIN)
    headers1 = _login(client, admin1.email, pwd1)

    # 1. Self-demotion is blocked (400)
    self_demote = client.patch(
        f"/api/v1/users/{admin1.id}/role",
        headers=headers1,
        json={"role": "FINANCE_MANAGER"},
    )
    assert self_demote.status_code == 400
    assert self_demote.json()["error"]["code"] == "self_role_change_forbidden"

    # 2. Self-deactivation is blocked (400)
    self_deact = client.patch(
        f"/api/v1/users/{admin1.id}/status",
        headers=headers1,
        json={"is_active": False},
    )
    assert self_deact.status_code == 400
    assert self_deact.json()["error"]["code"] == "self_deactivation_forbidden"

    # 3. Last active SYSTEM_ADMIN protection:
    # Temporarily deactivate all other SYSTEM_ADMIN accounts (including the .env bootstrap admin)
    # so admin1 and admin2 are the only active admins, then admin1 deactivates admin2 (allowed),
    # leaving only 1 active admin. Verify _enforce_admin_protection_guards blocks removing the last one.
    role_admin = get_role_by_name(db, RoleName.SYSTEM_ADMIN.value)
    other_admins = (
        db.execute(
            select(User).where(
                User.role_id == role_admin.id,
                User.id != admin1.id,
                User.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    for oa in other_admins:
        oa.is_active = False
    db.commit()

    try:
        from app.schemas.user import UserUpdate
        from app.services import user_service

        # Create a non-self actor simulation to test the last-admin DB lock guard directly
        fake_actor, _ = _seed_role_user(db, RoleName.FINANCE_MANAGER)
        with pytest.raises(Exception) as exc_info:
            user_service.update_user(
                db,
                admin1.id,
                UserUpdate(is_active=False),
                actor=fake_actor,
            )
        assert "last active SYSTEM_ADMIN" in str(exc_info.value)
    finally:
        for oa in other_admins:
            oa.is_active = True
        db.commit()


def test_audit_logs_recorded_for_user_changes_and_upload(
    client: TestClient,
    db: Session,
) -> None:
    admin, pwd = _seed_role_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login(client, admin.email, pwd)

    # 1. Create user -> USER_CREATED audit log
    new_email = f"audit-target-{uuid.uuid4().hex[:8]}@example.com"
    c_resp = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": new_email,
            "full_name": "Audit Target",
            "password": "TargetPass123!",
            "role": "FINANCE_EXECUTIVE",
        },
    )
    assert c_resp.status_code == 201
    target_id = uuid.UUID(c_resp.json()["data"]["id"])
    _rbac_user_ids.append(target_id)

    # 2. Change role -> USER_ROLE_CHANGED audit log
    r_resp = client.patch(
        f"/api/v1/users/{target_id}/role",
        headers=headers,
        json={"role": "FINANCE_MANAGER"},
    )
    assert r_resp.status_code == 200

    # 3. Change status -> USER_STATUS_CHANGED audit log
    s_resp = client.patch(
        f"/api/v1/users/{target_id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert s_resp.status_code == 200

    # 4. Upload document -> DOCUMENT_UPLOADED audit log
    u_resp = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files=[("files", ("audited.csv", b"h1,h2\n10,20\n", "text/csv"))],
    )
    assert u_resp.status_code == 201
    doc_id = uuid.UUID(u_resp.json()["data"]["results"][0]["document_id"])

    user_logs = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "USER", AuditLog.entity_id == target_id)
            .order_by(AuditLog.created_at.asc())
        )
        .scalars()
        .all()
    )
    actions = [log.action for log in user_logs]
    assert "USER_CREATED" in actions
    assert "USER_ROLE_CHANGED" in actions
    assert "USER_STATUS_CHANGED" in actions

    doc_logs = (
        db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "DOCUMENT",
                AuditLog.entity_id == doc_id,
            )
        )
        .scalars()
        .all()
    )
    assert len(doc_logs) == 1
    assert doc_logs[0].action == "DOCUMENT_UPLOADED"
    assert doc_logs[0].user_id == admin.id


def test_single_visibility_filter_enforced_across_document_endpoints(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exec1, pwd1 = _seed_role_user(db, RoleName.FINANCE_EXECUTIVE)
    exec2, pwd2 = _seed_role_user(db, RoleName.FINANCE_EXECUTIVE)
    headers1 = _login(client, exec1.email, pwd1)
    headers2 = _login(client, exec2.email, pwd2)

    up1 = client.post(
        "/api/v1/documents/upload",
        headers=headers1,
        files=[("files", ("exec1.csv", b"a,b\n1,2\n", "text/csv"))],
    )
    doc1_id = uuid.UUID(up1.json()["data"]["results"][0]["document_id"])

    # Tighten the single visibility function to uploader-only and verify all endpoints obey it
    monkeypatch.setattr(
        document_service.document_repo,
        "visible_documents_filter",
        lambda user: Document.uploaded_by == user.id,
    )

    # exec1 sees doc1
    assert client.get("/api/v1/documents", headers=headers1).json()["data"]["total"] == 1
    assert client.get(f"/api/v1/documents/{doc1_id}", headers=headers1).status_code == 200
    assert client.get(f"/api/v1/documents/{doc1_id}/status", headers=headers1).status_code == 200
    assert client.get(f"/api/v1/documents/{doc1_id}/extraction", headers=headers1).status_code == 200
    assert client.get(f"/api/v1/documents/{doc1_id}/validation", headers=headers1).status_code == 200
    assert client.get(f"/api/v1/documents/{doc1_id}/file", headers=headers1).status_code == 200

    # exec2 is blocked from seeing doc1 everywhere
    assert client.get("/api/v1/documents", headers=headers2).json()["data"]["total"] == 0
    assert client.get(f"/api/v1/documents/{doc1_id}", headers=headers2).status_code == 404
    assert client.get(f"/api/v1/documents/{doc1_id}/status", headers=headers2).status_code == 404
    assert client.get(f"/api/v1/documents/{doc1_id}/extraction", headers=headers2).status_code == 404
    assert client.get(f"/api/v1/documents/{doc1_id}/validation", headers=headers2).status_code == 404
    assert client.get(f"/api/v1/documents/{doc1_id}/file", headers=headers2).status_code == 404

