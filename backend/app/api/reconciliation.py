from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.reconciliation.service import ReconciliationService
from app.schemas.reconciliation import (
    ExcelSheetsResponse,
    ReconcilePdfExcelRequest,
    ReconcilePdfPdfRequest,
    ReconciliationJobDetail,
    ReconciliationJobPage,
)

router = APIRouter(prefix="/reconciliations", tags=["reconciliation"])


@router.get(
    "/excel/{document_id}/sheets",
    response_model=APIResponse[ExcelSheetsResponse],
    summary="List available worksheets in a parsed spreadsheet",
)
def get_excel_sheets(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.RECONCILIATION_VIEW)),
) -> APIResponse[ExcelSheetsResponse]:
    sheets = ReconciliationService.get_excel_sheets(db, document_id, current_user)
    return ok(sheets, "Worksheets retrieved successfully")


@router.post(
    "/pdf-pdf",
    response_model=APIResponse[ReconciliationJobDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Reconcile two extracted PDF invoices",
)
def reconcile_pdf_pdf(
    request: ReconcilePdfPdfRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.RECONCILIATION_RUN)),
) -> APIResponse[ReconciliationJobDetail]:
    result = ReconciliationService.reconcile_pdf_pdf(db, request, current_user)
    return ok(result, f"PDF reconciliation completed with status: {result.overall_status}")


@router.post(
    "/pdf-excel",
    response_model=APIResponse[ReconciliationJobDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Reconcile an extracted PDF invoice against an Excel spreadsheet",
)
def reconcile_pdf_excel(
    request: ReconcilePdfExcelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.RECONCILIATION_RUN)),
) -> APIResponse[ReconciliationJobDetail]:
    result = ReconciliationService.reconcile_pdf_excel(db, request, current_user)
    return ok(result, f"PDF-Excel reconciliation completed with status: {result.overall_status}")


@router.get(
    "",
    response_model=APIResponse[ReconciliationJobPage],
    summary="List reconciliation runs",
)
def list_reconciliations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    document_id: Optional[uuid.UUID] = Query(None, description="Filter runs involving this document"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.RECONCILIATION_VIEW)),
) -> APIResponse[ReconciliationJobPage]:
    page_data = ReconciliationService.list_reconciliations(
        db,
        current_user,
        page=page,
        page_size=page_size,
        document_id=document_id,
    )
    return ok(page_data, "Reconciliation runs retrieved successfully")


@router.get(
    "/{reconciliation_id}",
    response_model=APIResponse[ReconciliationJobDetail],
    summary="Get detailed reconciliation run results",
)
def get_reconciliation(
    reconciliation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.RECONCILIATION_VIEW)),
) -> APIResponse[ReconciliationJobDetail]:
    result = ReconciliationService.get_reconciliation(db, reconciliation_id, current_user)
    return ok(result, "Reconciliation run details retrieved successfully")

