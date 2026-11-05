from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit import AuditLogPage
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get(
    "",
    response_model=APIResponse[AuditLogPage],
    summary="List paginated global audit logs",
)
def list_audit_logs(
    entity_type: Optional[str] = Query(None, description="Filter by target entity type"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by target entity UUID"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by actor user UUID"),
    action: Optional[str] = Query(None, description="Filter by action string"),
    date_from: Optional[datetime] = Query(None, description="Earliest timestamp (inclusive)"),
    date_to: Optional[datetime] = Query(None, description="Latest timestamp (inclusive)"),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AUDIT_VIEW)),
) -> APIResponse[AuditLogPage]:
    page_data = AuditService.list_audit_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return ok(page_data, "Audit logs retrieved successfully")

