from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from pathlib import Path
from typing import Any
import uuid

from fastapi.testclient import TestClient
import pymupdf as fitz
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.base import PermanentAIError
from app.ai.fake import DEFAULT_CANNED_INVOICE, FakeEmbeddingProvider, FakeLLMProvider
from app.ai.registry import (
    set_embedding_provider_override,
    set_llm_provider_override,
)
from app.core.config import settings
from app.core.security import hash_password
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus, ReviewStatus
from app.models.extraction import DocumentCorrection, ExtractedInvoice
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.parse_result import DocumentParseResult
from app.models.user import RoleName, User
from app.models.validation import ValidationResult
from app.repositories.user_repo import get_role_by_name
from app.services import job_queue
from app.worker.runner import process_one_job


@pytest.fixture(autouse=True)
def reset_ai_overrides():
    set_llm_provider_override(FakeLLMProvider())
    set_embedding_provider_override(FakeEmbeddingProvider())
    yield
    set_llm_provider_override(None)
    set_embedding_provider_override(None)


_day2_user_ids: list[uuid.UUID] = []


def _create_user(db: Session, role: RoleName = RoleName.FINANCE_EXECUTIVE) -> User:
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=f"test-{role.value.lower()}-{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"Test {role.value.title()}",
        password_hash=hash_password("Pass123!"),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _day2_user_ids.append(user.id)
    return user


@pytest.fixture(autouse=True)
def cleanup_day2_test_users(db: Session) -> Generator[None, None, None]:
    yield
    while _day2_user_ids:
        user_id = _day2_user_ids.pop()
        db.execute(delete(Document).where(Document.uploaded_by == user_id))
        db.execute(delete(User).where(User.id == user_id))
    db.commit()


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "Pass123!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_parse_complete_enqueues_both_extraction_and_embedding_once_and_runs_happy_path(
    client: TestClient,
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    user = _create_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _auth_headers(client, user)

    fake_llm = FakeLLMProvider([DEFAULT_CANNED_INVOICE])
    fake_emb = FakeEmbeddingProvider()
    set_llm_provider_override(fake_llm)
    set_embedding_provider_override(fake_emb)

    pdf_bytes = _make_pdf_bytes(
        "Acme Industrial Supplies Ltd. Invoice INV-2026-001 Date 2026-01-15 Total USD 1,100.00 "
        "Precision Widget Model A Qty 4 Unit Price 150.00 Amount 600.00"
    )
    resp = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("invoice_acme.pdf", pdf_bytes, "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    doc_id = uuid.UUID(resp.json()["data"]["results"][0]["document_id"])

    # 1. Process parse job -> must succeed and enqueue both extraction and embedding once
    assert process_one_job(test_sessionmaker) is True

    jobs_after_parse = (
        db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == doc_id)
            .order_by(ProcessingJob.created_at.asc())
        )
        .scalars()
        .all()
    )
    job_types = {j.job_type: j.status for j in jobs_after_parse}
    assert job_types == {
        JobType.PARSE.value: JobStatus.SUCCEEDED.value,
        JobType.EXTRACTION.value: JobStatus.PENDING.value,
        JobType.EMBEDDING.value: JobStatus.PENDING.value,
    }

    # Verify idempotent enqueue (partial unique index prevents duplicate pending jobs)
    dup_ext_job = job_queue.enqueue(db, document_id=doc_id, job_type=JobType.EXTRACTION.value)
    all_ext_jobs = (
        db.execute(
            select(ProcessingJob).where(
                ProcessingJob.document_id == doc_id,
                ProcessingJob.job_type == JobType.EXTRACTION.value,
            )
        )
        .scalars()
        .all()
    )
    assert len(all_ext_jobs) == 1
    assert dup_ext_job.id == all_ext_jobs[0].id

    # 2. Run remaining jobs (extraction + embedding)
    assert process_one_job(test_sessionmaker) is True
    assert process_one_job(test_sessionmaker) is True
    assert process_one_job(test_sessionmaker) is False

    # 3. Verify persisted ExtractedInvoice, LineItems, ValidationResults, and DocumentChunks
    db.expire_all()
    inv = db.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == doc_id)
    ).scalar_one()
    assert inv.invoice_number == "INV-2026-001"
    assert inv.total == Decimal("1100.0000")
    assert inv.currency == "USD"
    assert len(inv.line_items) == 2
    assert inv.extraction_metadata["prompt_version"] == "invoice_v1"
    assert inv.extraction_metadata["self_reported_uncalibrated"] == 0.95

    chunks = (
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    assert len(chunks) >= 1
    assert chunks[0].page_number == 1
    assert chunks[0].embedding_model == fake_emb.model_name
    assert len(chunks[0].embedding) == settings.EMBEDDING_DIM

    # 4. Verify GET /api/documents/{id} detail payload includes extracted_invoice, validation_results, processing_jobs
    detail_resp = client.get(f"/api/documents/{doc_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["status"] == DocumentStatus.PARSED.value
    assert detail["review_status"] == ReviewStatus.PENDING.value
    assert detail["extracted_invoice"]["invoice_number"] == "INV-2026-001"
    assert len(detail["extracted_invoice"]["line_items"]) == 2
    assert len(detail["validation_results"]) >= 10
    assert len(detail["processing_jobs"]) == 3
    for j in detail["processing_jobs"]:
        assert j["status"] == JobStatus.SUCCEEDED.value
        assert j["current_stage"] == "completed"
        assert j["attempt_count"] == 1


def test_malformed_json_triggers_one_repair_retry_then_fails_cleanly(
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    user = _create_user(db)
    doc = Document(
        original_filename="broken_json.pdf",
        stored_path="documents/test/broken_json.pdf",
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=200,
        sha256="b" * 64,
        status=DocumentStatus.PARSED.value,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()

    parse_res = DocumentParseResult(
        document_id=doc.id,
        pages=[
            {
                "page_number": 1,
                "text": "Invoice INV-900 Total $500.00",
                "source": "ocr",
                "ocr_confidence": 0.65,
            }
        ],
        tables=[],
        doc_metadata={"format": "pdf", "page_count": 1},
        ocr_used=True,
    )
    db.add(parse_res)
    db.commit()

    # Scenario A: 1st call returns invalid JSON, 2nd call (repair retry) returns valid JSON -> succeeds!
    repair_success_llm = FakeLLMProvider(
        responses=[
            "{not-valid-json-at-all",
            DEFAULT_CANNED_INVOICE,
        ]
    )
    set_llm_provider_override(repair_success_llm)

    job1 = job_queue.enqueue(db, document_id=doc.id, job_type=JobType.EXTRACTION.value)
    assert process_one_job(test_sessionmaker) is True
    assert len(repair_success_llm.calls) == 2
    assert repair_success_llm.calls[0]["repair_error"] is None
    assert repair_success_llm.calls[1]["repair_error"] is not None

    db.expire_all()
    job1_refreshed = db.get(ProcessingJob, job1.id)
    assert job1_refreshed is not None
    assert job1_refreshed.status == JobStatus.SUCCEEDED.value

    inv1 = db.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == doc.id)
    ).scalar_one()
    assert inv1.extraction_metadata["repair_retry_used"] is True
    assert inv1.extraction_metadata["ocr_confidence_avg"] == 0.65
    assert inv1.extraction_metadata["ocr_confidence_min"] == 0.65

    # Scenario B: Both initial call and repair retry return malformed JSON -> fails immediately on attempt 1
    doc2 = Document(
        original_filename="still_broken.pdf",
        stored_path="documents/test/still_broken.pdf",
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=200,
        sha256="c" * 64,
        status=DocumentStatus.PARSED.value,
        uploaded_by=user.id,
    )
    db.add(doc2)
    db.flush()
    db.add(
        DocumentParseResult(
            document_id=doc2.id,
            pages=[{"page_number": 1, "text": "Invoice text", "source": "text_layer", "ocr_confidence": None}],
            tables=[],
            doc_metadata={"format": "pdf"},
            ocr_used=False,
        )
    )
    db.commit()

    always_bad_llm = FakeLLMProvider(
        responses=[
            "{broken-attempt-1",
            "{broken-attempt-2-repair",
        ]
    )
    set_llm_provider_override(always_bad_llm)

    job2 = job_queue.enqueue(db, document_id=doc2.id, job_type=JobType.EXTRACTION.value, max_attempts=3)
    assert process_one_job(test_sessionmaker) is True
    assert len(always_bad_llm.calls) == 2

    db.expire_all()
    job2_refreshed = db.get(ProcessingJob, job2.id)
    assert job2_refreshed is not None
    assert job2_refreshed.status == JobStatus.FAILED.value
    assert job2_refreshed.attempts == 1
    assert "repair retry" in (job2_refreshed.last_error or "").lower()

    # Raw LLM output must still be persisted in extraction_metadata
    inv2 = db.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == doc2.id)
    ).scalar_one()
    assert inv2.extraction_metadata["raw_llm_output"] == "{broken-attempt-2-repair"
    assert inv2.extraction_metadata["initial_raw_llm_output"] == "{broken-attempt-1"


def test_permanent_auth_error_fails_immediately_without_infinite_retry(
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    user = _create_user(db)
    doc = Document(
        original_filename="auth_fail.pdf",
        stored_path="documents/test/auth_fail.pdf",
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=200,
        sha256="d" * 64,
        status=DocumentStatus.PARSED.value,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()
    db.add(
        DocumentParseResult(
            document_id=doc.id,
            pages=[{"page_number": 1, "text": "Invoice text", "source": "text_layer", "ocr_confidence": None}],
            tables=[],
            doc_metadata={"format": "pdf"},
            ocr_used=False,
        )
    )
    db.commit()

    bad_key_llm = FakeLLMProvider(
        responses=[PermanentAIError("Gemini authentication/key error (HTTP 400): API_KEY_INVALID")]
    )
    set_llm_provider_override(bad_key_llm)

    ext_job = job_queue.enqueue(db, document_id=doc.id, job_type=JobType.EXTRACTION.value, max_attempts=3)
    emb_job = job_queue.enqueue(db, document_id=doc.id, job_type=JobType.EMBEDDING.value, max_attempts=3)

    assert process_one_job(test_sessionmaker) is True
    assert process_one_job(test_sessionmaker) is True

    db.expire_all()
    ext_ref = db.get(ProcessingJob, ext_job.id)
    emb_ref = db.get(ProcessingJob, emb_job.id)
    doc_ref = db.get(Document, doc.id)

    assert ext_ref is not None and emb_ref is not None and doc_ref is not None
    # Permanent error failed on attempt 1 without re-queueing
    assert ext_ref.status == JobStatus.FAILED.value
    assert ext_ref.attempts == 1
    assert "API_KEY_INVALID" in (ext_ref.last_error or "")
    # Embedding still succeeded independently!
    assert emb_ref.status == JobStatus.SUCCEEDED.value
    # Document status remains failed from the extraction failure (not overwritten by embedding)
    assert doc_ref.status == DocumentStatus.FAILED.value


def test_duplicate_invoice_across_different_files_and_embedding_idempotency_and_reprocess_api(
    client: TestClient,
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    user = _create_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _auth_headers(client, user)

    # First invoice: "Acme, Industrial Supplies Ltd." / "inv-2026-001"
    # Second invoice: "acme industrial supplies ltd" / "INV2026001" (normalized exact match!)
    second_invoice_payload: dict[str, Any] = {
        **DEFAULT_CANNED_INVOICE,
        "supplier_name": "acme industrial supplies ltd",
        "invoice_number": "inv-2026/001",
    }
    fake_llm = FakeLLMProvider([DEFAULT_CANNED_INVOICE, second_invoice_payload])
    set_llm_provider_override(fake_llm)

    pdf1 = _make_pdf_bytes("First invoice upload content over fifty characters so text layer is used.")
    pdf2 = _make_pdf_bytes("Second invoice upload content over fifty characters under a different filename.")

    r1 = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("first_name.pdf", pdf1, "application/pdf"))],
    )
    r2 = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("second_name.pdf", pdf2, "application/pdf"))],
    )
    doc1_id = uuid.UUID(r1.json()["data"]["results"][0]["document_id"])
    doc2_id = uuid.UUID(r2.json()["data"]["results"][0]["document_id"])

    while process_one_job(test_sessionmaker):
        pass

    db.expire_all()
    dup_row = db.execute(
        select(ValidationResult).where(
            ValidationResult.document_id == doc2_id,
            ValidationResult.validation_code == "DUPLICATE_INVOICE",
        )
    ).scalar_one()
    assert dup_row.status == "FAILED"
    assert dup_row.severity == "WARNING"
    assert str(doc1_id) in (dup_row.actual_value or "")

    # Test POST /api/documents/{id}/reprocess?stage=embedding idempotency
    chunks_before = (
        db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc1_id))
        .scalars()
        .all()
    )
    assert len(chunks_before) >= 1

    reproc_resp = client.post(
        f"/api/documents/{doc1_id}/reprocess?stage=embedding",
        headers=headers,
    )
    assert reproc_resp.status_code == 202, reproc_resp.text
    assert reproc_resp.json()["data"]["job_type"] == "embedding"

    assert process_one_job(test_sessionmaker) is True
    db.expire_all()
    chunks_after = (
        db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc1_id))
        .scalars()
        .all()
    )
    assert len(chunks_after) == len(chunks_before)
    assert [c.chunk_index for c in chunks_after] == list(range(len(chunks_after)))

    # Test human corrections guard: if a DocumentCorrection row exists, extraction refuses to overwrite
    inv1 = db.execute(
        select(ExtractedInvoice).where(ExtractedInvoice.document_id == doc1_id)
    ).scalar_one()
    db.add(
        DocumentCorrection(
            document_id=doc1_id,
            invoice_id=inv1.id,
            field_name="total",
            original_value="1100.0000",
            corrected_value="1150.0000",
            corrected_by=user.id,
            correction_reason="Manual adjustment",
        )
    )
    db.commit()

    reproc_ext = client.post(
        f"/api/documents/{doc1_id}/reprocess?stage=extraction",
        headers=headers,
    )
    assert reproc_ext.status_code == 202
    reproc_job_id = uuid.UUID(reproc_ext.json()["data"]["id"])

    assert process_one_job(test_sessionmaker) is True
    db.expire_all()
    reproc_job = db.get(ProcessingJob, reproc_job_id)
    assert reproc_job is not None
    assert reproc_job.status == JobStatus.FAILED.value
    assert "corrections already exist" in (reproc_job.last_error or "").lower()


def test_spreadsheet_extraction_serialization_and_null_page_number_chunks(
    client: TestClient,
    db: Session,
    test_sessionmaker: sessionmaker[Session],
) -> None:
    from sqlalchemy import func

    user = _create_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _auth_headers(client, user)

    fake_llm = FakeLLMProvider([DEFAULT_CANNED_INVOICE])
    set_llm_provider_override(fake_llm)

    csv_content = b"item,qty,unit_price,amount\nWidget A,4,150.00,600.00\nCalibration,2,200.00,400.00\n"
    resp = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("sheet_invoice.csv", csv_content, "text/csv"))],
    )
    assert resp.status_code == 201
    doc_id = uuid.UUID(resp.json()["data"]["results"][0]["document_id"])

    while process_one_job(test_sessionmaker):
        pass

    # Verify the LLM received "Sheet: <name>" + header row + rows
    assert len(fake_llm.calls) == 1
    sent_doc_text = fake_llm.calls[0]["document_text"] or ""
    assert "Sheet: original" in sent_doc_text
    assert "item\tqty\tunit_price\tamount" in sent_doc_text
    assert "Widget A\t4\t150.00\t600.00" in sent_doc_text

    # Verify spreadsheet chunks have page_number = NULL and vector_dims = 768
    db.expire_all()
    chunks = (
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    assert len(chunks) == 1
    assert chunks[0].page_number is None
    assert chunks[0].content.startswith("Sheet: original\nitem\tqty\tunit_price\tamount\n")

    vec_dim = db.execute(
        select(func.vector_dims(DocumentChunk.embedding)).where(DocumentChunk.id == chunks[0].id)
    ).scalar_one()
    assert vec_dim == 768

