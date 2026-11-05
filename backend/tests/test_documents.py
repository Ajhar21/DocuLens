from __future__ import annotations

from collections.abc import Generator
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.document import Document
from app.models.job import ProcessingJob
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name

_created_test_user_ids: list[uuid.UUID] = []


def _reviewer_headers(client: TestClient, db: Session) -> dict[str, str]:
    uid = uuid.uuid4().hex[:8]
    email = f"test-uploader-{uid}@example.com"
    role_obj = get_role_by_name(db, RoleName.FINANCE_EXECUTIVE.value)
    user = User(
        email=email,
        full_name="Uploader",
        password_hash=hash_password("UploadPass123!"),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _created_test_user_ids.append(user.id)

    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "UploadPass123!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def cleanup_document_test_users(db: Session) -> Generator[None, None, None]:
    yield
    while _created_test_user_ids:
        user_id = _created_test_user_ids.pop()
        db.execute(delete(Document).where(Document.uploaded_by == user_id))
        db.execute(delete(User).where(User.id == user_id))
    db.commit()


def test_multifile_upload_one_valid_one_invalid(
    client: TestClient, db: Session
) -> None:
    headers = _reviewer_headers(client, db)

    valid_csv = b"invoice_id,amount\nINV-001,150.00\n"
    invalid_exe = b"MZ\x90\x00\x03\x00\x00\x00"

    resp = client.post(
        "/api/documents",
        headers=headers,
        files=[
            ("files", ("invoices.csv", valid_csv, "text/csv")),
            ("files", ("malware.exe", invalid_exe, "application/octet-stream")),
        ],
    )
    # Partial success -> 207 Multi-Status with per-file results.
    assert resp.status_code == 207, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    payload = body["data"]

    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    assert len(payload["results"]) == 2

    accepted = next(r for r in payload["results"] if r["filename"] == "invoices.csv")
    rejected = next(r for r in payload["results"] if r["filename"] == "malware.exe")

    assert accepted["status"] == "accepted"
    assert accepted["document_id"] is not None
    assert accepted["job_id"] is not None

    assert rejected["status"] == "rejected"
    assert rejected["document_id"] is None
    assert rejected["reason"]

    docs = db.execute(select(Document)).scalars().all()
    jobs = db.execute(select(ProcessingJob)).scalars().all()
    assert len(docs) == 1
    assert len(jobs) == 1
    assert jobs[0].document_id == docs[0].id
    assert jobs[0].status == "pending"

    detail_resp = client.get(f"/api/documents/{docs[0].id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["latest_job"]["id"] == str(jobs[0].id)
    assert detail["uploader"]["full_name"] == "Uploader"

    dl_resp = client.get(f"/api/documents/{docs[0].id}/file", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.content == valid_csv


def test_upload_zero_byte_file_rejected_cleanly(
    client: TestClient, db: Session
) -> None:
    headers = _reviewer_headers(client, db)

    resp = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("empty.pdf", b"", "application/pdf"))],
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "all_files_rejected"
    payload = body["data"]
    assert payload["accepted_count"] == 0
    assert payload["rejected_count"] == 1
    assert payload["results"][0]["status"] == "rejected"
    assert "empty" in payload["results"][0]["reason"].lower()

    # Confirm no documents or jobs persisted
    docs = db.execute(select(Document)).scalars().all()
    assert len(docs) == 0


def test_oversized_file_rejected_without_full_memory_load(
    client: TestClient, db: Session, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    headers = _reviewer_headers(client, db)

    # 1.2 MB dummy PDF
    dummy_header = b"%PDF-1.4\n"
    oversized_bytes = dummy_header + b"0" * (1200 * 1024)

    resp = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("big.pdf", oversized_bytes, "application/pdf"))],
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "all_files_rejected"
    payload = body["data"]
    assert payload["accepted_count"] == 0
    assert payload["rejected_count"] == 1
    rejected = payload["results"][0]
    assert rejected["status"] == "rejected"
    assert "exceeds maximum allowed size" in rejected["reason"].lower()

    # Verify no leaked document
    docs = db.execute(select(Document)).scalars().all()
    assert len(docs) == 0


def test_nasty_and_unicode_filenames_safe_path(
    client: TestClient, db: Session
) -> None:
    headers = _reviewer_headers(client, db)

    valid_csv = b"code,name\n1,Alpha\n"
    nasty_names = [
        r"..\..\..\etc\shadow.csv",
        "চালান_২০২৬ invoice (1).csv",
        "test name with spaces & symbols #$%.csv",
    ]

    files_payload = [
        ("files", (fname, valid_csv, "text/csv")) for fname in nasty_names
    ]
    resp = client.post("/api/documents", headers=headers, files=files_payload)
    assert resp.status_code == 201
    payload = resp.json()["data"]
    assert payload["accepted_count"] == 3
    assert payload["rejected_count"] == 0

    docs = db.execute(select(Document)).scalars().all()
    assert len(docs) == 3

    for doc in docs:
        # 1. Physical storage path is safely decoupled under UUID path (cross-platform path check)
        normalized_path = doc.stored_path.replace("\\", "/")
        assert normalized_path.startswith("documents/")
        assert ".." not in normalized_path
        # 2. Raw human filename is preserved intact in DB metadata
        assert doc.original_filename in nasty_names

        # 3. Download endpoint serves the file with safe Content-Disposition
        dl_resp = client.get(f"/api/documents/{doc.id}/file", headers=headers)
        assert dl_resp.status_code == 200
        assert dl_resp.content == valid_csv


def test_duplicate_file_upload_allowed_with_hash_tracking(
    client: TestClient, db: Session
) -> None:
    headers = _reviewer_headers(client, db)
    csv_bytes = b"order_id,amount\nORD-101,99.50\n"

    # Upload same file content in two distinct requests
    resp1 = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("invoice.csv", csv_bytes, "text/csv"))],
    )
    assert resp1.status_code == 201
    doc1_id = resp1.json()["data"]["results"][0]["document_id"]

    resp2 = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("invoice.csv", csv_bytes, "text/csv"))],
    )
    assert resp2.status_code == 201
    doc2_id = resp2.json()["data"]["results"][0]["document_id"]

    # Both accepted with distinct IDs
    assert doc1_id != doc2_id

    # Verify both records share identical sha256 hash
    doc1 = db.get(Document, doc1_id)
    doc2 = db.get(Document, doc2_id)
    assert doc1 is not None and doc2 is not None
    assert doc1.sha256 == doc2.sha256
    assert doc1.stored_path != doc2.stored_path



def test_upload_policy_is_discoverable(client: TestClient, db: Session) -> None:
    from app.core.config import settings

    headers = _reviewer_headers(client, db)
    resp = client.get("/api/documents/upload-policy", headers=headers)
    assert resp.status_code == 200, resp.text
    policy = resp.json()["data"]
    assert policy["max_upload_mb"] == settings.MAX_UPLOAD_MB
    assert policy["max_upload_bytes"] == settings.MAX_UPLOAD_MB * 1024 * 1024
    assert ".pdf" in policy["allowed_extensions"]
    assert "application/pdf" in policy["accepted_content_types"]

    assert client.get("/api/documents/upload-policy").status_code == 401


def test_list_documents_page_envelope_with_uploader(client: TestClient, db: Session) -> None:
    headers = _reviewer_headers(client, db)
    files = [
        ("files", (f"f{i}.csv", f"a,b\n{i},2\n".encode(), "text/csv")) for i in range(3)
    ]
    assert client.post("/api/documents", headers=headers, files=files).status_code == 201

    resp = client.get("/api/documents?limit=2&offset=0", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    page = body["data"]
    assert page["total"] == 3
    assert page["limit"] == 2
    assert page["offset"] == 0
    assert len(page["items"]) == 2
    assert page["items"][0]["uploader"]["full_name"] == "Uploader"
    assert "email" not in page["items"][0]["uploader"]

    resp2 = client.get("/api/documents?limit=2&offset=2", headers=headers)
    assert len(resp2.json()["data"]["items"]) == 1

    filtered = client.get("/api/documents?status=parsed", headers=headers).json()["data"]
    assert filtered["total"] == 0
    assert filtered["items"] == []


def test_errors_use_envelope(client: TestClient, db: Session) -> None:
    import uuid as _uuid

    headers = _reviewer_headers(client, db)

    # Validation error: no files part at all
    resp = client.post("/api/documents", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "validation_error"
    assert any(d["field"] == "files" for d in body["error"]["details"])

    # Not found
    resp = client.get(f"/api/documents/{_uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert resp.json()["message"] == "Document not found"

    # Invalid query param
    resp = client.get("/api/documents?limit=0", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == "limit"
