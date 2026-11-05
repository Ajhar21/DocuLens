from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.audit import AuditLog
from app.models.user import User


def insert_audit_log(db: Session, entry: AuditLog) -> AuditLog:
    """Persist an ``AuditLog`` row inside the caller's active transaction."""
    db.add(entry)
    db.flush()
    return entry


def query_audit_logs(
    db: Session,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    """Return paginated audit log entries matching filters along with total count."""
    filters = []

    if entity_type is not None and entity_type.strip():
        filters.append(AuditLog.entity_type == entity_type.strip())
    if entity_id is not None:
        filters.append(AuditLog.entity_id == entity_id)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action is not None and action.strip():
        filters.append(AuditLog.action == action.strip())
    if date_from is not None:
        filters.append(AuditLog.created_at >= date_from)
    if date_to is not None:
        filters.append(AuditLog.created_at <= date_to)

    count_stmt = select(func.count(AuditLog.id))
    if filters:
        count_stmt = count_stmt.where(sa.and_(*filters))
    total = db.scalar(count_stmt) or 0

    query_stmt = (
        select(AuditLog)
        .options(joinedload(AuditLog.user))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if filters:
        query_stmt = query_stmt.where(sa.and_(*filters))

    items = list(db.scalars(query_stmt).unique().all())
    return items, total


def get_audit_logs_for_document(
    db: Session,
    document_id: uuid.UUID,
) -> list[AuditLog]:
    """Retrieve all audit logs directly or indirectly referencing a document."""
    doc_id_str = str(document_id)
    stmt = (
        select(AuditLog)
        .options(joinedload(AuditLog.user))
        .where(
            or_(
                sa.and_(AuditLog.entity_type == "document", AuditLog.entity_id == document_id),
                AuditLog.new_values["document_id"].as_string() == doc_id_str,
                AuditLog.new_values["document_id_a"].as_string() == doc_id_str,
                AuditLog.new_values["document_id_b"].as_string() == doc_id_str,
            )
        )
        .order_by(AuditLog.created_at.desc())
    )
    return list(db.scalars(stmt).unique().all())
