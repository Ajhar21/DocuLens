from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import math
import re
from typing import Any, Optional
import uuid

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.core.visibility import visible_documents_filter
from app.models.document import Document, DocumentStatus
from app.models.extraction import ExtractedInvoice
from app.models.parse_result import DocumentParseResult
from app.models.reconciliation import (
    MatchStatus,
    ReconciliationJob,
    ReconciliationOverallStatus,
    ReconciliationResult,
    ReconciliationType,
)
from app.models.user import User
from app.reconciliation.comparator import compare_invoices, to_decimal
from app.repositories import reconciliation_repo
from app.schemas.reconciliation import (
    ExcelSheetsResponse,
    ReconcilePdfExcelRequest,
    ReconcilePdfPdfRequest,
    ReconciliationJobDetail,
    ReconciliationJobPage,
    ReconciliationJobPagination,
    ReconciliationJobSummary,
    ReconciliationResultRead,
)
from app.services.audit_service import AuditService


def _invoice_to_dict(invoice: ExtractedInvoice) -> dict[str, Any]:
    lines = []
    if invoice.line_items:
        for li in invoice.line_items:
            lines.append(
                {
                    "line_no": li.line_no,
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "amount": li.amount,
                }
            )
    return {
        "invoice_number": invoice.invoice_number,
        "supplier_name": invoice.supplier_name,
        "customer_name": invoice.customer_name,
        "invoice_date": invoice.invoice_date,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "currency": invoice.currency,
        "line_items": lines,
    }


def _parse_excel_row_with_mapping(
    row: list[Any],
    col_idx_map: dict[str, int],
) -> dict[str, Any]:
    """Extract invoice dict from a specific sheet row using explicit column mapping."""
    header_vals: dict[str, Any] = {
        "invoice_number": None,
        "supplier_name": None,
        "customer_name": None,
        "invoice_date": None,
        "subtotal": None,
        "tax": None,
        "total": None,
        "currency": None,
        "line_items": [],
    }
    for field, idx in col_idx_map.items():
        if idx < len(row):
            val = row[idx]
            if val is not None:
                if field in ("subtotal", "tax", "total"):
                    header_vals[field] = to_decimal(val)
                elif field == "invoice_date":
                    header_vals[field] = val
                else:
                    header_vals[field] = str(val).strip()
    return header_vals


def _parse_excel_table_to_invoice_dict(table: dict[str, Any]) -> dict[str, Any]:
    """Map parsed spreadsheet sheet columns and rows to invoice comparison dict."""
    columns = [str(c).lower().strip() for c in table.get("columns", [])]
    rows = table.get("rows", [])

    col_map: dict[str, int] = {}
    for idx, col in enumerate(columns):
        norm = re.sub(r"[^\w]", "_", col).strip("_")
        if norm in ("invoice_number", "invoice_no", "inv_num", "inv_no", "invoice"):
            col_map["invoice_number"] = idx
        elif norm in ("supplier_name", "supplier", "vendor", "vendor_name"):
            col_map["supplier_name"] = idx
        elif norm in ("customer_name", "customer", "client", "buyer"):
            col_map["customer_name"] = idx
        elif norm in ("invoice_date", "date", "inv_date"):
            col_map["invoice_date"] = idx
        elif norm in ("subtotal", "sub_total", "net_amount"):
            col_map["subtotal"] = idx
        elif norm in ("tax", "vat", "tax_amount"):
            col_map["tax"] = idx
        elif norm in ("total", "total_amount", "gross_amount", "amount"):
            col_map["total"] = idx
        elif norm in ("currency", "curr"):
            col_map["currency"] = idx
        elif norm in ("description", "item_description", "item", "product", "details"):
            col_map["description"] = idx
        elif norm in ("quantity", "qty"):
            col_map["quantity"] = idx
        elif norm in ("unit_price", "rate", "price"):
            col_map["unit_price"] = idx

    header_vals: dict[str, Any] = {
        "invoice_number": None,
        "supplier_name": None,
        "customer_name": None,
        "invoice_date": None,
        "subtotal": None,
        "tax": None,
        "total": None,
        "currency": None,
    }

    line_items: list[dict[str, Any]] = []
    accumulated_amount = Decimal("0.0000")

    for r_idx, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            continue
        line_item: dict[str, Any] = {"line_no": r_idx}

        # Header fields from first row if present
        for h_key in ("invoice_number", "supplier_name", "customer_name", "invoice_date", "currency"):
            if header_vals[h_key] is None and h_key in col_map and col_map[h_key] < len(row):
                val = row[col_map[h_key]]
                if val is not None and str(val).strip():
                    header_vals[h_key] = str(val).strip()

        # Amounts
        for amt_key in ("subtotal", "tax", "total"):
            if header_vals[amt_key] is None and amt_key in col_map and col_map[amt_key] < len(row):
                dec = to_decimal(row[col_map[amt_key]])
                if dec is not None:
                    header_vals[amt_key] = dec

        # Line item details
        if "description" in col_map and col_map["description"] < len(row):
            line_item["description"] = str(row[col_map["description"]]).strip()
        if "quantity" in col_map and col_map["quantity"] < len(row):
            line_item["quantity"] = to_decimal(row[col_map["quantity"]])
        if "unit_price" in col_map and col_map["unit_price"] < len(row):
            line_item["unit_price"] = to_decimal(row[col_map["unit_price"]])
        if "total" in col_map and col_map["total"] < len(row):
            line_dec = to_decimal(row[col_map["total"]])
            line_item["amount"] = line_dec
            if line_dec is not None:
                accumulated_amount += line_dec

        has_line_item_cols = any(k in col_map for k in ("description", "quantity", "unit_price"))
        if has_line_item_cols and (line_item.get("description") or line_item.get("quantity") is not None or line_item.get("unit_price") is not None):
            line_items.append(line_item)

    if header_vals["total"] is None and accumulated_amount > Decimal("0.0000"):
        header_vals["total"] = accumulated_amount

    header_vals["line_items"] = line_items
    return header_vals


class ReconciliationService:
    @staticmethod
    def get_excel_sheets(
        db: Session,
        document_id: uuid.UUID,
        current_user: User,
    ) -> ExcelSheetsResponse:
        doc = db.scalars(
            select(Document).where(
                Document.id == document_id,
                visible_documents_filter(current_user),
            )
        ).one_or_none()
        if doc is None:
            raise NotFoundError("Document not found")

        if doc.status != DocumentStatus.PARSED.value:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "document_not_ready",
                f"Document processing status is '{doc.status}', expected 'parsed'",
            )

        if doc.file_ext.lower() not in (".xlsx", ".xls", ".csv"):
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "invalid_document_type",
                f"Document extension '{doc.file_ext}' is not a supported spreadsheet format (.xlsx, .xls, .csv)",
            )

        parse_result = db.scalars(
            select(DocumentParseResult).where(DocumentParseResult.document_id == document_id)
        ).one_or_none()

        sheet_names: list[str] = []
        if parse_result and parse_result.tables:
            for t in parse_result.tables:
                name = t.get("name")
                if name and name not in sheet_names:
                    sheet_names.append(name)

        if not sheet_names:
            sheet_names = ["Sheet1"]

        return ExcelSheetsResponse(document_id=document_id, sheet_names=sheet_names)

    @staticmethod
    def reconcile_pdf_pdf(
        db: Session,
        request: ReconcilePdfPdfRequest,
        current_user: User,
    ) -> ReconciliationJobDetail:
        doc_a = db.scalars(
            select(Document).where(
                Document.id == request.document_id_a,
                visible_documents_filter(current_user),
            )
        ).one_or_none()
        doc_b = db.scalars(
            select(Document).where(
                Document.id == request.document_id_b,
                visible_documents_filter(current_user),
            )
        ).one_or_none()

        if doc_a is None or doc_b is None:
            raise NotFoundError("One or both documents not found or not accessible")

        if doc_a.status != DocumentStatus.PARSED.value or doc_b.status != DocumentStatus.PARSED.value:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "document_not_ready",
                "Both documents must be completed and parsed before reconciliation",
            )

        inv_a = db.scalars(
            select(ExtractedInvoice)
            .options(selectinload(ExtractedInvoice.line_items))
            .where(ExtractedInvoice.document_id == doc_a.id)
        ).one_or_none()
        inv_b = db.scalars(
            select(ExtractedInvoice)
            .options(selectinload(ExtractedInvoice.line_items))
            .where(ExtractedInvoice.document_id == doc_b.id)
        ).one_or_none()

        if inv_a is None or inv_b is None:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "missing_extracted_invoice",
                "Extracted invoice data missing for one or both documents",
            )

        dict_a = _invoice_to_dict(inv_a)
        dict_b = _invoice_to_dict(inv_b)

        comparison = compare_invoices(
            dict_a,
            dict_b,
            amount_tolerance_abs=settings.RECONCILIATION_AMOUNT_TOLERANCE_ABSOLUTE,
            amount_tolerance_pct=settings.RECONCILIATION_AMOUNT_TOLERANCE_PERCENTAGE,
            date_tolerance_days=settings.RECONCILIATION_DATE_TOLERANCE_DAYS,
        )

        job = ReconciliationJob(
            initiated_by=current_user.id,
            document_id_a=doc_a.id,
            document_id_b=doc_b.id,
            reconciliation_type=ReconciliationType.PDF_PDF.value,
            overall_status=comparison.overall_status,
            discrepancy_count=comparison.discrepancy_count,
            notes=request.notes,
        )
        results = [
            ReconciliationResult(
                entity_type=r.entity_type,
                field_name=r.field_name,
                source_a_value=r.source_a_value,
                source_b_value=r.source_b_value,
                match_status=r.match_status,
                absolute_difference=r.absolute_difference,
                percentage_difference=r.percentage_difference,
            )
            for r in comparison.results
        ]
        reconciliation_repo.create_reconciliation_job(db, job, results)

        AuditService.record(
            db,
            user_id=current_user.id,
            action="reconciliation:run",
            entity_type="reconciliation_job",
            entity_id=job.id,
            new_values={
                "reconciliation_type": job.reconciliation_type,
                "document_id_a": str(doc_a.id),
                "document_id_b": str(doc_b.id),
                "overall_status": job.overall_status,
                "discrepancy_count": job.discrepancy_count,
            },
        )
        db.commit()

        return ReconciliationService.get_reconciliation(db, job.id, current_user)

    @staticmethod
    def reconcile_pdf_excel(
        db: Session,
        request: ReconcilePdfExcelRequest,
        current_user: User,
    ) -> ReconciliationJobDetail:
        doc_a = db.scalars(
            select(Document).where(
                Document.id == request.document_id_a,
                visible_documents_filter(current_user),
            )
        ).one_or_none()
        doc_b = db.scalars(
            select(Document).where(
                Document.id == request.document_id_b,
                visible_documents_filter(current_user),
            )
        ).one_or_none()

        if doc_a is None or doc_b is None:
            raise NotFoundError("One or both documents not found or not accessible")

        if doc_a.status != DocumentStatus.PARSED.value or doc_b.status != DocumentStatus.PARSED.value:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "document_not_ready",
                "Both documents must be completed and parsed before reconciliation",
            )

        if doc_b.file_ext.lower() not in (".xlsx", ".xls", ".csv"):
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "invalid_document_type",
                f"Document B extension '{doc_b.file_ext}' is not a supported spreadsheet format (.xlsx, .xls, .csv)",
            )

        inv_a = db.scalars(
            select(ExtractedInvoice)
            .options(selectinload(ExtractedInvoice.line_items))
            .where(ExtractedInvoice.document_id == doc_a.id)
        ).one_or_none()
        if inv_a is None:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "missing_extracted_invoice",
                "Extracted invoice data missing for document A (PDF)",
            )
        dict_a = _invoice_to_dict(inv_a)

        # For Excel document: check parsed worksheet tables first, then extracted invoice fallback
        parse_result = db.scalars(
            select(DocumentParseResult).where(DocumentParseResult.document_id == doc_b.id)
        ).one_or_none()

        inv_b: Optional[ExtractedInvoice] = None
        if not (parse_result and parse_result.tables):
            inv_b = db.scalars(
                select(ExtractedInvoice)
                .options(selectinload(ExtractedInvoice.line_items))
                .where(ExtractedInvoice.document_id == doc_b.id)
            ).one_or_none()

        meta_notes: Optional[str] = None
        audit_extra_values: dict[str, Any] = {}

        if parse_result and parse_result.tables:
            target_table: Optional[dict[str, Any]] = None
            if request.excel_sheet_name:
                for t in parse_result.tables:
                    if t.get("name") == request.excel_sheet_name:
                        target_table = t
                        break
            if target_table is None:
                target_table = parse_result.tables[0]

            sheet_name = str(target_table.get("name") or request.excel_sheet_name or "Sheet1")

            if request.column_mapping is not None:
                # 1. Require 'invoice_number' in column_mapping
                norm_mapping = {
                    str(k).strip(): str(v).strip()
                    for k, v in request.column_mapping.items()
                    if v and str(v).strip()
                }
                if "invoice_number" not in norm_mapping or not norm_mapping["invoice_number"]:
                    raise AppError(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "missing_invoice_number_mapping",
                        "column_mapping must include a mapping for 'invoice_number'",
                    )

                # 2. Validate that mapped headers exist in the sheet
                raw_columns = target_table.get("columns", [])
                sheet_col_lookup = {
                    str(c).strip().lower(): idx for idx, c in enumerate(raw_columns)
                }

                col_idx_map: dict[str, int] = {}
                for field, header_name in norm_mapping.items():
                    h_lower = header_name.lower()
                    if h_lower not in sheet_col_lookup:
                        raise AppError(
                            status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "invalid_column_mapping",
                            f"Mapped column '{header_name}' does not exist in sheet '{sheet_name}'",
                        )
                    col_idx_map[field] = sheet_col_lookup[h_lower]

                # 3. Match row using invoice_number
                source_inv_num = str(dict_a.get("invoice_number") or "").strip()
                norm_source_inv_num = re.sub(r"[^\w]", "", source_inv_num).lower()

                inv_col_idx = col_idx_map["invoice_number"]
                rows = target_table.get("rows", [])
                matched_rows: list[tuple[int, list[Any]]] = []

                for r_idx, r in enumerate(rows, start=2):  # 1-based row index (header assumed at row 1)
                    if not isinstance(r, list) or inv_col_idx >= len(r):
                        continue
                    cell_val = r[inv_col_idx]
                    if cell_val is None:
                        continue
                    norm_cell_val = re.sub(r"[^\w]", "", str(cell_val).strip()).lower()
                    if norm_cell_val and norm_cell_val == norm_source_inv_num:
                        matched_rows.append((r_idx, r))

                if len(matched_rows) == 0:
                    raise AppError(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "invoice_record_not_found",
                        f"No record found in sheet '{sheet_name}' with invoice number '{source_inv_num}'",
                    )
                if len(matched_rows) > 1:
                    row_nums = [str(r[0]) for r in matched_rows]
                    raise AppError(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "ambiguous_invoice_record",
                        f"Multiple records ({len(matched_rows)}) found in sheet '{sheet_name}' for invoice number '{source_inv_num}' at rows {', '.join(row_nums)}",
                    )

                matched_row_num, matched_row = matched_rows[0]
                dict_b = _parse_excel_row_with_mapping(matched_row, col_idx_map)
                meta_notes = f"Sheet: {sheet_name} | Row: {matched_row_num}"
                audit_extra_values = {
                    "sheet_name": sheet_name,
                    "matched_row": matched_row_num,
                    "column_mapping": norm_mapping,
                }
            else:
                dict_b = _parse_excel_table_to_invoice_dict(target_table)
        elif inv_b is not None:
            dict_b = _invoice_to_dict(inv_b)
        else:
            raise AppError(
                status.HTTP_400_BAD_REQUEST,
                "missing_parsed_tables",
                "Parsed table data missing for document B (Excel)",
            )

        comparison = compare_invoices(
            dict_a,
            dict_b,
            amount_tolerance_abs=settings.RECONCILIATION_AMOUNT_TOLERANCE_ABSOLUTE,
            amount_tolerance_pct=settings.RECONCILIATION_AMOUNT_TOLERANCE_PERCENTAGE,
            date_tolerance_days=settings.RECONCILIATION_DATE_TOLERANCE_DAYS,
        )

        final_notes: Optional[str]
        if request.notes and meta_notes:
            final_notes = f"{request.notes} ({meta_notes})"
        elif meta_notes:
            final_notes = meta_notes
        else:
            final_notes = request.notes

        job = ReconciliationJob(
            initiated_by=current_user.id,
            document_id_a=doc_a.id,
            document_id_b=doc_b.id,
            reconciliation_type=ReconciliationType.PDF_EXCEL.value,
            overall_status=comparison.overall_status,
            discrepancy_count=comparison.discrepancy_count,
            notes=final_notes,
        )
        results = [
            ReconciliationResult(
                entity_type=r.entity_type,
                field_name=r.field_name,
                source_a_value=r.source_a_value,
                source_b_value=r.source_b_value,
                match_status=r.match_status,
                absolute_difference=r.absolute_difference,
                percentage_difference=r.percentage_difference,
            )
            for r in comparison.results
        ]
        reconciliation_repo.create_reconciliation_job(db, job, results)

        audit_payload = {
            "reconciliation_type": job.reconciliation_type,
            "document_id_a": str(doc_a.id),
            "document_id_b": str(doc_b.id),
            "overall_status": job.overall_status,
            "discrepancy_count": job.discrepancy_count,
        }
        audit_payload.update(audit_extra_values)
        AuditService.record(
            db,
            user_id=current_user.id,
            action="reconciliation:run",
            entity_type="reconciliation_job",
            entity_id=job.id,
            new_values=audit_payload,
        )
        db.commit()

        return ReconciliationService.get_reconciliation(db, job.id, current_user)

    @staticmethod
    def get_reconciliation(
        db: Session,
        job_id: uuid.UUID,
        current_user: User,
    ) -> ReconciliationJobDetail:
        job = reconciliation_repo.get_reconciliation_job(db, job_id)
        if job is None:
            raise NotFoundError("Reconciliation job not found")

        # Verify visibility of both documents
        doc_a = db.scalars(
            select(Document.id).where(
                Document.id == job.document_id_a,
                visible_documents_filter(current_user),
            )
        ).one_or_none()
        doc_b = db.scalars(
            select(Document.id).where(
                Document.id == job.document_id_b,
                visible_documents_filter(current_user),
            )
        ).one_or_none()
        if doc_a is None or doc_b is None:
            raise NotFoundError("Reconciliation job not found or document not accessible")

        return ReconciliationJobDetail(
            id=job.id,
            initiated_by=job.initiated_by,
            document_id_a=job.document_id_a,
            document_id_b=job.document_id_b,
            reconciliation_type=job.reconciliation_type,
            overall_status=job.overall_status,
            discrepancy_count=job.discrepancy_count,
            initiated_at=job.initiated_at,
            completed_at=job.completed_at,
            notes=job.notes,
            results=[ReconciliationResultRead.model_validate(r) for r in job.results],
        )

    @staticmethod
    def list_reconciliations(
        db: Session,
        current_user: User,
        *,
        page: int = 1,
        page_size: int = 20,
        document_id: Optional[uuid.UUID] = None,
    ) -> ReconciliationJobPage:
        items, total = reconciliation_repo.list_reconciliation_jobs(
            db,
            page=page,
            page_size=page_size,
            document_id=document_id,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        pagination = ReconciliationJobPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )
        return ReconciliationJobPage(
            items=[ReconciliationJobSummary.model_validate(j) for j in items],
            pagination=pagination,
        )

