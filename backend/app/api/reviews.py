from __future__ import annotations

from typing import Any, Optional, Union
import uuid

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.review import (
    ApprovePayload,
    CorrectionItem,
    RejectPayload,
    ReviewDetailRead,
    ReviewQueuePage,
)
from app.services import review_service

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=APIResponse[ReviewQueuePage])
def list_reviews(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    review_status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[ReviewQueuePage]:
    """Retrieve documents in the human review queue (COMPLETED/parsed documents)."""
    return ok(
        review_service.list_reviews(
            db,
            current_user,
            limit=limit,
            offset=offset,
            review_status_filter=review_status,
        )
    )


@router.get("/{document_id}", response_model=APIResponse[ReviewDetailRead])
def get_review_detail(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
) -> APIResponse[ReviewDetailRead]:
    """Get review detail for a document without mutating state."""
    return ok(review_service.get_review_detail(db, document_id, current_user))


@router.patch("/{document_id}/corrections", response_model=APIResponse[ReviewDetailRead])
def submit_corrections(
    document_id: uuid.UUID,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.EXTRACTION_EDIT)),
) -> APIResponse[ReviewDetailRead]:
    """Apply manual field corrections to invoice header fields.

    Accepts a list of correction items or a wrapped object with a 'corrections' list.
    Immediately updates extracted values, sets review_status to CORRECTED, and re-validates.
    """
    raw_list: list[Any]
    if isinstance(payload, list):
        raw_list = payload
    elif isinstance(payload, dict) and "corrections" in payload and isinstance(payload["corrections"], list):
        raw_list = payload["corrections"]
    else:
        raw_list = [payload]

    correction_items = [
        item if isinstance(item, CorrectionItem) else CorrectionItem.model_validate(item)
        for item in raw_list
    ]

    updated_detail = review_service.submit_corrections(
        db,
        document_id,
        correction_items,
        actor=current_user,
    )
    return ok(updated_detail, "Corrections applied successfully")


@router.post("/{document_id}/approve", response_model=APIResponse[ReviewDetailRead])
def approve_document(
    document_id: uuid.UUID,
    payload: Optional[ApprovePayload] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CORRECTION_APPROVE)),
) -> APIResponse[ReviewDetailRead]:
    """Approve a reviewed/corrected document (Finance Manager or System Admin only)."""
    notes = payload.notes if payload is not None else None
    approved_detail = review_service.approve_document(
        db,
        document_id,
        actor=current_user,
        notes=notes,
    )
    return ok(approved_detail, "Document approved")


@router.post("/{document_id}/reject", response_model=APIResponse[ReviewDetailRead])
def reject_document(
    document_id: uuid.UUID,
    payload: RejectPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CORRECTION_APPROVE)),
) -> APIResponse[ReviewDetailRead]:
    """Reject a reviewed document with a required reason."""
    rejected_detail = review_service.reject_document(
        db,
        document_id,
        reason=payload.reason,
        actor=current_user,
    )
    return ok(rejected_detail, "Document rejected")

