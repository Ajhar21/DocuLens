from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.document import Document
from app.models.job import ProcessingJob
from app.models.user import User, UserRole


def _reviewer_headers(client: TestClient, db: Session) -> dict[str, str]:
    user = User(
        email="uploader@example.com",
        full_name="Uploader",
        password_hash=hash_password("UploadPass123!"),
        role=UserRole.REVIEWER.value,
        is_active=True,
    )
    db.add(user)
    db.commit()

    resp = client.post(
        "/api/auth/login",
        data={"username": "uploader@example.com", "password": "UploadPass123!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


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
    assert resp.status_code == 201, resp.text
    payload = resp.json()

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
    assert detail_resp.json()["latest_job"]["id"] == str(jobs[0].id)

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
    assert resp.status_code == 201
    payload = resp.json()
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
    assert resp.status_code == 201
    payload = resp.json()
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
    payload = resp.json()
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
    doc1_id = resp1.json()["results"][0]["document_id"]

    resp2 = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("invoice.csv", csv_bytes, "text/csv"))],
    )
    assert resp2.status_code == 201
    doc2_id = resp2.json()["results"][0]["document_id"]

    # Both accepted with distinct IDs
    assert doc1_id != doc2_id

    # Verify both records share identical sha256 hash
    doc1 = db.get(Document, doc1_id)
    doc2 = db.get(Document, doc2_id)
    assert doc1 is not None and doc2 is not None
    assert doc1.sha256 == doc2.sha256
    assert doc1.stored_path != doc2.stored_path

