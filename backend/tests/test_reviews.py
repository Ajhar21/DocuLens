from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.document import Document, DocumentStatus, ReviewStatus
from app.models.extraction import DocumentCorrection, ExtractedInvoice, InvoiceLineItem
from app.models.user import RoleName, User
from app.models.validation import ValidationResult, ValidationSeverity, ValidationStatus
from app.repositories.user_repo import get_role_by_name

_test_user_ids: list[uuid.UUID] = []


def _seed_user(db: Session, role: RoleName) -> tuple[User, str]:
    uid = uuid.uuid4().hex[:8]
    pwd = "Password123!"
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=f"review-{role.value.lower()}-{uid}@example.com",
        full_name=f"Reviewer {role.value}",
        password_hash=hash_password(pwd),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _test_user_ids.append(user.id)
    return user, pwd


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def cleanup_review_users(db: Session) -> Generator[None, None, None]:
    yield
    while _test_user_ids:
        uid = _test_user_ids.pop()
        db.execute(delete(Document).where(Document.uploaded_by == uid))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def _create_parsed_document_with_invoice(
    db: Session,
    uploader: User,
    *,
    review_status: str = "needs_review",
    subtotal: Decimal = Decimal("1000.0000"),
    tax: Decimal = Decimal("100.0000"),
    total: Decimal = Decimal("1100.0000"),
) -> tuple[Document, ExtractedInvoice]:
    doc = Document(
        original_filename="review_sample.pdf",
        stored_path=f"documents/{uuid.uuid4()}/original.pdf",
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=1024,
        sha256="e" * 64,
        status=DocumentStatus.PARSED.value,
        review_status=review_status,
        uploaded_by=uploader.id,
    )
    db.add(doc)
    db.flush()

    inv = ExtractedInvoice(
        document_id=doc.id,
        invoice_number="INV-REV-001",
        invoice_date=date(2026, 1, 15),
        supplier_name="Acme Corp Ltd",
        customer_name="Global Client Inc",
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency="USD",
        extraction_metadata={
            "raw_llm_output": {
                "invoice_number": "INV-REV-001",
                "total": "1100.00",
                "supplier_name": "Acme Corp Ltd",
            },
            "prompt_version": "invoice_v1",
        },
    )
    db.add(inv)
    db.flush()

    line = InvoiceLineItem(
        invoice_id=inv.id,
        line_no=1,
        description="Widget A",
        quantity=Decimal("10.000000"),
        unit_price=Decimal("100.0000"),
        amount=Decimal("1000.0000"),
    )
    db.add(line)

    val = ValidationResult(
        document_id=doc.id,
        validation_code="LINE_SUM_EQUAL",
        field_name="total",
        severity=ValidationSeverity.ERROR.value,
        message="Line items sum does not match subtotal",
        status=ValidationStatus.FAILED.value,
    )
    db.add(val)
    db.commit()
    db.refresh(doc)
    db.refresh(inv)
    return doc, inv


def test_review_queue_listing_and_filtering(client: TestClient, db: Session) -> None:
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc1, _ = _create_parsed_document_with_invoice(db, exec_user, review_status="needs_review")
    doc2, _ = _create_parsed_document_with_invoice(db, exec_user, review_status="corrected")
    doc3, _ = _create_parsed_document_with_invoice(db, exec_user, review_status="approved")

    # 1. Default review queue returns pending/needs_review/in_review/corrected (doc1 and doc2, not doc3)
    resp = client.get("/api/v1/reviews", headers=headers)
    assert resp.status_code == 200, resp.text
    page = resp.json()["data"]
    returned_ids = [item["id"] for item in page["items"]]
    assert str(doc1.id) in returned_ids
    assert str(doc2.id) in returned_ids
    assert str(doc3.id) not in returned_ids

    # 2. Case-insensitive filtering
    resp_filtered = client.get("/api/v1/reviews?review_status=CORRECTED", headers=headers)
    assert resp_filtered.status_code == 200
    filtered_items = resp_filtered.json()["data"]["items"]
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == str(doc2.id)
    assert filtered_items[0]["review_status"] == "corrected"


def test_review_detail_read_does_not_mutate_state(client: TestClient, db: Session) -> None:
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc, inv = _create_parsed_document_with_invoice(db, exec_user, review_status="needs_review")

    resp = client.get(f"/api/v1/reviews/{doc.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]

    assert detail["document_id"] == str(doc.id)
    assert detail["review_status"] == "needs_review"
    assert detail["extracted_invoice"]["invoice_number"] == "INV-REV-001"
    assert detail["original_llm_output"]["invoice_number"] == "INV-REV-001"
    assert len(detail["validation_results"]) >= 1

    # Verify no mutation in database
    db.expire_all()
    refreshed_doc = db.get(Document, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.review_status == "needs_review"


def test_submit_corrections_header_fields_only_and_revalidation(
    client: TestClient, db: Session
) -> None:
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc, inv = _create_parsed_document_with_invoice(
        db,
        exec_user,
        review_status="needs_review",
        subtotal=Decimal("1000.0000"),
        tax=Decimal("100.0000"),
        total=Decimal("1200.0000"),  # arithmetic mismatch: 1000 + 100 != 1200
    )

    # 1. Invalid field rejection (422)
    bad_field_resp = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=headers,
        json=[{"field_name": "non_existent_column", "corrected_value": "foo"}],
    )
    assert bad_field_resp.status_code == 422
    assert "non-editable" in bad_field_resp.json()["error"]["details"][0]["message"].lower()

    # 2. Line item editing rejection (422)
    line_item_resp = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=headers,
        json=[{"field_name": "line_items", "corrected_value": []}],
    )
    assert line_item_resp.status_code == 422
    assert "Line-item editing is out of scope" in line_item_resp.json()["message"]

    # 3. Malformed decimal value rejection (422)
    bad_decimal_resp = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=headers,
        json=[{"field_name": "total", "corrected_value": "not-a-number"}],
    )
    assert bad_decimal_resp.status_code == 422
    assert "Must be a valid decimal amount" in bad_decimal_resp.json()["error"]["details"][0]["message"]

    # 4. Valid corrections: fix total to 1100.00 (subtotal 1000 + tax 100 = 1100), change invoice_number
    ok_resp = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=headers,
        json=[
            {
                "field_name": "total",
                "corrected_value": "1100.00",
                "reason": "Fix OCR misread 1200 -> 1100",
            },
            {
                "field_name": "invoice_number",
                "corrected_value": "INV-CORRECTED-999",
                "reason": "Correct typo",
            },
        ],
    )
    assert ok_resp.status_code == 200, ok_resp.text
    detail = ok_resp.json()["data"]

    # Review status changed to corrected
    assert detail["review_status"] == "corrected"
    assert detail["extracted_invoice"]["total"] == "1100.0000"
    assert detail["extracted_invoice"]["invoice_number"] == "INV-CORRECTED-999"

    # Original LLM output remains intact
    assert detail["original_llm_output"]["invoice_number"] == "INV-REV-001"

    # Document corrections history tracked
    corrections = detail["corrections"]
    assert len(corrections) == 2
    fields_corrected = {c["field_name"] for c in corrections}
    assert fields_corrected == {"total", "invoice_number"}

    # Database verification
    db.expire_all()
    refreshed_doc = db.get(Document, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.review_status == "corrected"

    # Deterministic validation re-evaluated: ARITHMETIC_MATCH is now PASSED
    val_rows = (
        db.execute(
            select(ValidationResult).where(
                ValidationResult.document_id == doc.id,
                ValidationResult.validation_code == "TOTAL_MISMATCH",
            )
        )
        .scalars()
        .all()
    )
    assert len(val_rows) == 1
    assert val_rows[0].status == "PASSED"


def test_approve_workflow_and_reopen_via_reject(client: TestClient, db: Session) -> None:
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    audit_user, audit_pwd = _seed_user(db, RoleName.ACCOUNTS_AUDIT)

    exec_headers = _login_headers(client, exec_user.email, exec_pwd)
    mgr_headers = _login_headers(client, mgr_user.email, mgr_pwd)
    audit_headers = _login_headers(client, audit_user.email, audit_pwd)

    doc, _ = _create_parsed_document_with_invoice(db, exec_user, review_status="needs_review")

    # 1. Accounts/Audit cannot approve or edit (403)
    audit_edit = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=audit_headers,
        json=[{"field_name": "invoice_number", "corrected_value": "INV-AUDIT"}],
    )
    assert audit_edit.status_code == 403

    audit_approve = client.post(f"/api/v1/reviews/{doc.id}/approve", headers=audit_headers)
    assert audit_approve.status_code == 403

    # 2. Finance Executive cannot approve (403)
    exec_approve = client.post(f"/api/v1/reviews/{doc.id}/approve", headers=exec_headers)
    assert exec_approve.status_code == 403

    # 3. Finance Manager approves -> review_status = 'approved'
    mgr_approve = client.post(
        f"/api/v1/reviews/{doc.id}/approve",
        headers=mgr_headers,
        json={"notes": "All looks good"},
    )
    assert mgr_approve.status_code == 200
    approved_data = mgr_approve.json()["data"]
    assert approved_data["review_status"] == "approved"
    assert approved_data["reviewed_by"] == str(mgr_user.id)
    assert approved_data["reviewed_at"] is not None

    # 4. Editing an APPROVED document returns 409 for everyone
    edit_approved = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=mgr_headers,
        json=[{"field_name": "invoice_number", "corrected_value": "INV-AFTER-APPROVE"}],
    )
    assert edit_approved.status_code == 409
    assert "must reject it first to reopen" in edit_approved.json()["message"]

    # 5. Approving an already approved document returns 409
    double_approve = client.post(f"/api/v1/reviews/{doc.id}/approve", headers=mgr_headers)
    assert double_approve.status_code == 409

    # 6. Rejecting without reason fails (422)
    empty_reject = client.post(
        f"/api/v1/reviews/{doc.id}/reject",
        headers=mgr_headers,
        json={"reason": "   "},
    )
    assert empty_reject.status_code == 422

    # 7. Manager rejects the approved document to reopen it -> review_status = 'rejected'
    reject_resp = client.post(
        f"/api/v1/reviews/{doc.id}/reject",
        headers=mgr_headers,
        json={"reason": "Client requested change of supplier name"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["data"]["review_status"] == "rejected"

    # 8. Executive can now correct the reopened document -> transitions to 'corrected'
    reopen_edit = client.patch(
        f"/api/v1/reviews/{doc.id}/corrections",
        headers=exec_headers,
        json=[{"field_name": "supplier_name", "corrected_value": "Acme International Ltd"}],
    )
    assert reopen_edit.status_code == 200
    assert reopen_edit.json()["data"]["review_status"] == "corrected"
    assert reopen_edit.json()["data"]["extracted_invoice"]["supplier_name"] == "Acme International Ltd"

