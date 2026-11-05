from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import uuid

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.extraction import ExtractedInvoice, InvoiceLineItem
from app.models.parse_result import DocumentParseResult
from app.models.reconciliation import ReconciliationJob, ReconciliationResult
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name
from app.services.storage import storage_service

_reconcile_user_ids: list[uuid.UUID] = []


def _seed_user(db: Session, role_name: RoleName) -> tuple[User, str]:
    role_obj = get_role_by_name(db, role_name.value)
    assert role_obj is not None
    uid = uuid.uuid4().hex[:8]
    password = "TestPassword123!"
    user = User(
        email=f"recon_{role_name.value.lower()}_{uid}@example.com",
        full_name=f"Reconcile Tester {role_name.value}",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _reconcile_user_ids.append(user.id)
    return user, password


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_invoice_doc(
    db: Session,
    user: User,
    *,
    filename: str = "invoice.pdf",
    ext: str = ".pdf",
    content_type: str = "application/pdf",
    status: str = DocumentStatus.PARSED.value,
    invoice_number: str = "INV-001",
    supplier_name: str = "Supplier Inc",
    customer_name: str = "Customer Corp",
    invoice_date: date = date(2026, 3, 1),
    subtotal: Decimal = Decimal("1000.0000"),
    tax: Decimal = Decimal("100.0000"),
    total: Decimal = Decimal("1100.0000"),
    currency: str = "USD",
    line_items: list[dict] | None = None,
    parse_tables: list[dict] | None = None,
) -> Document:
    doc_id = uuid.uuid4()
    if ext == ".pdf":
        dummy_bytes = b"%PDF-1.4 test invoice"
    elif ext == ".xlsx":
        dummy_bytes = b"PK\x03\x04" + b"\x00" * 30
    else:
        dummy_bytes = b"col1,col2\n1,2\n"
    stored = storage_service.save_stream(
        stream=io.BytesIO(dummy_bytes),
        document_id=doc_id,
        ext=ext,
        max_bytes=10 * 1024 * 1024,
    )
    doc = Document(
        id=doc_id,
        original_filename=filename,
        stored_path=stored.stored_path,
        content_type=content_type,
        file_ext=ext,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=status,
        review_status="pending",
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()

    if status == DocumentStatus.PARSED.value:
        if parse_tables is None:
            inv = ExtractedInvoice(
                document_id=doc.id,
                invoice_number=invoice_number,
                supplier_name=supplier_name,
                customer_name=customer_name,
                invoice_date=invoice_date,
                subtotal=subtotal,
                tax=tax,
                total=total,
                currency=currency,
            )
            db.add(inv)
            db.flush()

            if line_items:
                for idx, li in enumerate(line_items, start=1):
                    db.add(
                        InvoiceLineItem(
                            invoice_id=inv.id,
                            line_no=idx,
                            description=li.get("description", "Item"),
                            quantity=li.get("quantity"),
                            unit_price=li.get("unit_price"),
                            amount=li.get("amount", Decimal("0.0000")),
                        )
                    )
        else:
            db.add(
                DocumentParseResult(
                    document_id=doc.id,
                    pages=[],
                    tables=parse_tables,
                    doc_metadata={"sheet_count": len(parse_tables)},
                    ocr_used=False,
                )
            )

    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture(autouse=True)
def cleanup_reconcile_test_data(db: Session) -> Generator[None, None, None]:
    yield
    db.rollback()
    while _reconcile_user_ids:
        uid = _reconcile_user_ids.pop()
        db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
        doc_ids = db.execute(select(Document.id).where(Document.uploaded_by == uid)).scalars().all()
        for did in doc_ids:
            # Delete reconciliation jobs referencing these documents
            recon_job_ids = db.execute(
                select(ReconciliationJob.id).where(
                    (ReconciliationJob.document_id_a == did) | (ReconciliationJob.document_id_b == did)
                )
            ).scalars().all()
            for rjid in recon_job_ids:
                db.execute(delete(ReconciliationResult).where(ReconciliationResult.job_id == rjid))
                db.execute(delete(ReconciliationJob).where(ReconciliationJob.id == rjid))

            inv_ids = db.execute(select(ExtractedInvoice.id).where(ExtractedInvoice.document_id == did)).scalars().all()
            for iid in inv_ids:
                db.execute(delete(InvoiceLineItem).where(InvoiceLineItem.invoice_id == iid))
            db.execute(delete(ExtractedInvoice).where(ExtractedInvoice.document_id == did))
            db.execute(delete(DocumentParseResult).where(DocumentParseResult.document_id == did))
            db.execute(delete(Document).where(Document.id == did))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def test_reconcile_pdf_pdf_matched_pair(client: TestClient, db: Session) -> None:
    """Verify PDF-PDF reconciliation of matching documents produces MATCHED."""
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc_a = _create_invoice_doc(
        db,
        exec_user,
        invoice_number="INV-2026-101",
        supplier_name="Wayne Enterprises Corp.",
        total=Decimal("1500.0000"),
        line_items=[{"description": "Batarangs", "amount": Decimal("1500.0000")}],
    )
    doc_b = _create_invoice_doc(
        db,
        exec_user,
        invoice_number="inv-2026-101",
        supplier_name="Wayne Enterprises LLC",  # Suffix difference
        total=Decimal("1500.0300"),  # Within $0.05 absolute tolerance
        line_items=[{"description": "Batarangs", "amount": Decimal("1500.0000")}],
    )

    resp = client.post(
        "/api/v1/reconciliations/pdf-pdf",
        headers=headers,
        json={"document_id_a": str(doc_a.id), "document_id_b": str(doc_b.id), "notes": "Test match"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["reconciliation_type"] == "PDF_PDF"
    assert data["overall_status"] == "MATCHED"
    assert data["discrepancy_count"] == 0
    assert len(data["results"]) >= 6

    # Verify audit log entry
    audit = db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "reconciliation_job",
            AuditLog.entity_id == uuid.UUID(data["id"]),
            AuditLog.action == "reconciliation:run",
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_reconcile_pdf_pdf_mismatched_pair(client: TestClient, db: Session) -> None:
    """Verify PDF-PDF reconciliation with amount/number mismatch produces MISMATCHED."""
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    headers = _login_headers(client, mgr_user.email, mgr_pwd)

    doc_a = _create_invoice_doc(
        db,
        mgr_user,
        invoice_number="INV-A",
        total=Decimal("500.0000"),
    )
    doc_b = _create_invoice_doc(
        db,
        mgr_user,
        invoice_number="INV-B",
        total=Decimal("700.0000"),
    )

    resp = client.post(
        "/api/v1/reconciliations/pdf-pdf",
        headers=headers,
        json={"document_id_a": str(doc_a.id), "document_id_b": str(doc_b.id)},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["overall_status"] == "MISMATCHED"
    assert data["discrepancy_count"] >= 2


def test_reconcile_pdf_excel_with_sheet_selection(client: TestClient, db: Session) -> None:
    """Verify PDF-Excel reconciliation using parsed sheet tables."""
    audit_user, audit_pwd = _seed_user(db, RoleName.ACCOUNTS_AUDIT)
    headers = _login_headers(client, audit_user.email, audit_pwd)

    doc_pdf = _create_invoice_doc(
        db,
        audit_user,
        filename="invoice.pdf",
        ext=".pdf",
        invoice_number="INV-EXCEL-001",
        supplier_name="Global Tech Ltd",
        total=Decimal("2500.0000"),
    )

    # Excel document with 2 sheets
    tables = [
        {
            "name": "Summary_Sheet",
            "columns": ["Invoice_Number", "Supplier_Name", "Invoice_Date", "Total_Amount", "Currency"],
            "rows": [["INV-EXCEL-001", "Global Tech Inc", "2026-03-01", "2500.00", "USD"]],
        },
        {
            "name": "Other_Sheet",
            "columns": ["Col1", "Col2"],
            "rows": [["1", "2"]],
        },
    ]
    doc_excel = _create_invoice_doc(
        db,
        audit_user,
        filename="ledger.xlsx",
        ext=".xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parse_tables=tables,
    )

    # 1. Test sheet discovery
    sheets_resp = client.get(f"/api/v1/reconciliations/excel/{doc_excel.id}/sheets", headers=headers)
    assert sheets_resp.status_code == 200
    assert sheets_resp.json()["data"]["sheet_names"] == ["Summary_Sheet", "Other_Sheet"]

    # 2. Reconcile targeting Summary_Sheet
    recon_resp = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "Summary_Sheet",
        },
    )
    assert recon_resp.status_code == 201, recon_resp.text
    data = recon_resp.json()["data"]
    discrepancies = [r for r in data["results"] if r["match_status"] not in ("EXACT_MATCH", "TOLERANCE_MATCH", "NOT_COMPARABLE")]
    assert not discrepancies, f"Discrepancies found: {discrepancies}"
    assert data["reconciliation_type"] == "PDF_EXCEL"
    assert data["overall_status"] == "MATCHED"


def test_reconciliation_precondition_validations(client: TestClient, db: Session) -> None:
    """Verify 404/400 validation on bad document states."""
    admin_user, admin_pwd = _seed_user(db, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, admin_user.email, admin_pwd)

    good_doc = _create_invoice_doc(db, admin_user)

    # 1. Non-existent document ID -> 404
    bad_id_resp = client.post(
        "/api/v1/reconciliations/pdf-pdf",
        headers=headers,
        json={"document_id_a": str(good_doc.id), "document_id_b": str(uuid.uuid4())},
    )
    assert bad_id_resp.status_code == 404

    # 2. Document not parsed (status == 'processing') -> 400
    unparsed_doc = _create_invoice_doc(
        db,
        admin_user,
        status=DocumentStatus.PROCESSING.value,
    )
    unparsed_resp = client.post(
        "/api/v1/reconciliations/pdf-pdf",
        headers=headers,
        json={"document_id_a": str(good_doc.id), "document_id_b": str(unparsed_doc.id)},
    )
    assert unparsed_resp.status_code == 400
    assert "document_not_ready" in unparsed_resp.json()["error"]["code"]

    # 3. PDF-Excel with non-Excel document for doc_b -> 400
    non_excel_resp = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={"document_id_a": str(good_doc.id), "document_id_b": str(good_doc.id)},
    )
    assert non_excel_resp.status_code == 400
    assert "invalid_document_type" in non_excel_resp.json()["error"]["code"]


def test_reconciliation_list_and_get_details(client: TestClient, db: Session) -> None:
    """Verify GET /reconciliations list and GET /reconciliations/{id}."""
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc_a = _create_invoice_doc(db, exec_user)
    doc_b = _create_invoice_doc(db, exec_user)

    post_resp = client.post(
        "/api/v1/reconciliations/pdf-pdf",
        headers=headers,
        json={"document_id_a": str(doc_a.id), "document_id_b": str(doc_b.id)},
    )
    assert post_resp.status_code == 201
    recon_id = post_resp.json()["data"]["id"]

    # List runs
    list_resp = client.get("/api/v1/reconciliations", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["pagination"]["total"] >= 1

    # Filter by document_id
    filtered_list = client.get(f"/api/v1/reconciliations?document_id={doc_a.id}", headers=headers)
    assert filtered_list.status_code == 200
    assert filtered_list.json()["data"]["pagination"]["total"] >= 1

    # Get single run detail
    detail_resp = client.get(f"/api/v1/reconciliations/{recon_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["id"] == recon_id
    assert len(detail_resp.json()["data"]["results"]) > 0


def test_reconcile_pdf_excel_with_column_mapping_success(client: TestClient, db: Session) -> None:
    """Verify PDF-Excel reconciliation using explicit column mapping and row matching."""
    exec_user, exec_pwd = _seed_user(db, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, exec_user.email, exec_pwd)

    doc_pdf = _create_invoice_doc(
        db,
        exec_user,
        invoice_number="INV-2026-X99",
        supplier_name="Acme Industrial Corp",
        total=Decimal("4500.0000"),
    )

    # Multi-row spreadsheet
    tables = [
        {
            "name": "General_Ledger",
            "columns": ["Doc_Ref", "Vendor_Title", "Booking_Date", "Gross_Total", "Curr"],
            "rows": [
                ["INV-OTHER-001", "Other Vendor", "2026-03-01", "100.00", "USD"],
                ["INV-2026-X99", "Acme Industrial LLC", "2026-03-01", "4500.00", "USD"],
                ["INV-OTHER-002", "Third Vendor", "2026-03-02", "200.00", "USD"],
            ],
        }
    ]
    doc_excel = _create_invoice_doc(
        db,
        exec_user,
        filename="ledger_multi.xlsx",
        ext=".xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parse_tables=tables,
    )

    resp = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "General_Ledger",
            "column_mapping": {
                "invoice_number": "Doc_Ref",
                "supplier_name": "Vendor_Title",
                "invoice_date": "Booking_Date",
                "total": "Gross_Total",
                "currency": "Curr",
            },
            "notes": "Verified ledger match",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["overall_status"] == "MATCHED"
    assert data["discrepancy_count"] == 0
    assert "Sheet: General_Ledger | Row: 3" in data["notes"]
    assert "Verified ledger match" in data["notes"]


def test_reconcile_pdf_excel_mapping_validations(client: TestClient, db: Session) -> None:
    """Verify 422 validations for missing invoice_number, unknown header, record not found, and ambiguous record."""
    mgr_user, mgr_pwd = _seed_user(db, RoleName.FINANCE_MANAGER)
    headers = _login_headers(client, mgr_user.email, mgr_pwd)

    doc_pdf = _create_invoice_doc(
        db,
        mgr_user,
        invoice_number="INV-TARGET-01",
        total=Decimal("1000.0000"),
    )

    tables = [
        {
            "name": "Sheet_A",
            "columns": ["Inv_Col", "Amt_Col"],
            "rows": [
                ["INV-TARGET-01", "1000.00"],
                ["INV-TARGET-01", "1000.00"],  # Duplicate row to test ambiguous
            ],
        }
    ]
    doc_excel = _create_invoice_doc(
        db,
        mgr_user,
        filename="test_recon.xlsx",
        ext=".xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parse_tables=tables,
    )

    # 1. Missing invoice_number in mapping -> 422
    resp_no_inv = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "Sheet_A",
            "column_mapping": {"total": "Amt_Col"},
        },
    )
    assert resp_no_inv.status_code == 422
    assert "missing_invoice_number_mapping" in resp_no_inv.json()["error"]["code"]

    # 2. Unknown header in mapping -> 422
    resp_unknown_hdr = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "Sheet_A",
            "column_mapping": {
                "invoice_number": "Inv_Col",
                "total": "NonExistentColumn",
            },
        },
    )
    assert resp_unknown_hdr.status_code == 422
    assert "invalid_column_mapping" in resp_unknown_hdr.json()["error"]["code"]

    # 3. Ambiguous record (multiple matching rows) -> 422
    resp_ambiguous = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "Sheet_A",
            "column_mapping": {
                "invoice_number": "Inv_Col",
                "total": "Amt_Col",
            },
        },
    )
    assert resp_ambiguous.status_code == 422
    assert "ambiguous_invoice_record" in resp_ambiguous.json()["error"]["code"]

    # 4. Record not found -> 422
    doc_pdf_missing = _create_invoice_doc(
        db,
        mgr_user,
        invoice_number="INV-NOT-IN-EXCEL",
        total=Decimal("1000.0000"),
    )
    resp_not_found = client.post(
        "/api/v1/reconciliations/pdf-excel",
        headers=headers,
        json={
            "document_id_a": str(doc_pdf_missing.id),
            "document_id_b": str(doc_excel.id),
            "excel_sheet_name": "Sheet_A",
            "column_mapping": {
                "invoice_number": "Inv_Col",
                "total": "Amt_Col",
            },
        },
    )
    assert resp_not_found.status_code == 422
    assert "invoice_record_not_found" in resp_not_found.json()["error"]["code"]

