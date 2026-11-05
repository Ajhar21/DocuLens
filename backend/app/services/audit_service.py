from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import enum
import math
from typing import Any, Literal, Optional, Union
import uuid

from fastapi import status
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.core.visibility import visible_documents_filter
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.extraction import DocumentCorrection
from app.models.job import ProcessingJob
from app.models.user import User
from app.models.validation import ValidationResult
from app.repositories import audit_repo
from app.schemas.audit import (
    ActorSummary,
    AuditLogItem,
    AuditLogPage,
    AuditLogPagination,
    DocumentHistoryResponse,
    TimelineEvent,
)


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (uuid.UUID, date, datetime)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, enum.Enum):
        return _to_json_safe(value.value)
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_json_safe(item) for item in value]
    return str(value)


def _build_actor_summary(user: Optional[User]) -> Union[ActorSummary, Literal["system"]]:
    if user is None:
        return "system"
    return ActorSummary(
        id=user.id,
        email=user.email,
        role=user.role_name,
    )


class AuditService:
    """Centralized audit recorder and query service."""

    @staticmethod
    def record(
        db: Session,
        *,
        user_id: Optional[uuid.UUID],
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=_to_json_safe(old_values) if old_values is not None else None,
            new_values=_to_json_safe(new_values) if new_values is not None else None,
        )
        return audit_repo.insert_audit_log(db, entry)

    @staticmethod
    def list_audit_logs(
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
    ) -> AuditLogPage:
        entries, total = audit_repo.query_audit_logs(
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

        items: list[AuditLogItem] = []
        for e in entries:
            items.append(
                AuditLogItem(
                    id=e.id,
                    user_id=e.user_id,
                    user_email=e.user.email if e.user else None,
                    user_role=e.user.role_name if e.user else None,
                    action=e.action,
                    entity_type=e.entity_type,
                    entity_id=e.entity_id,
                    old_values=e.old_values,
                    new_values=e.new_values,
                    created_at=e.created_at,
                )
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 0
        pagination = AuditLogPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )
        return AuditLogPage(items=items, pagination=pagination)

    @staticmethod
    def get_document_history(
        db: Session,
        document_id: uuid.UUID,
        current_user: User,
    ) -> DocumentHistoryResponse:
        # Enforce single visibility rule
        doc_stmt = (
            select(Document)
            .options(
                joinedload(Document.uploader),
                joinedload(Document.reviewer),
            )
            .where(
                Document.id == document_id,
                visible_documents_filter(current_user),
            )
        )
        doc = db.scalars(doc_stmt).unique().one_or_none()
        if not doc:
            raise AppError(status.HTTP_404_NOT_FOUND, "not_found", "Document not found")

        events: list[TimelineEvent] = []

        # 1. Document Upload Event
        events.append(
            TimelineEvent(
                timestamp=doc.created_at,
                event_type="document:uploaded",
                actor=_build_actor_summary(doc.uploader),
                details={
                    "original_filename": doc.original_filename,
                    "content_type": doc.content_type,
                    "size_bytes": doc.size_bytes,
                    "sha256": doc.sha256,
                    "status": doc.status,
                    "review_status": doc.review_status,
                },
            )
        )

        # 2. Processing Jobs (and retries)
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.created_at.asc(), ProcessingJob.id.asc())
            ).all()
        )
        for job in jobs:
            events.append(
                TimelineEvent(
                    timestamp=job.created_at,
                    event_type=f"job:{job.job_type}:queued",
                    actor="system",
                    details={
                        "job_id": str(job.id),
                        "job_type": job.job_type,
                        "status": job.status,
                        "attempts": job.attempts,
                        "max_attempts": job.max_attempts,
                    },
                )
            )
            if job.status in ("succeeded", "failed") and job.completed_at:
                events.append(
                    TimelineEvent(
                        timestamp=job.completed_at,
                        event_type=f"job:{job.job_type}:{job.status}",
                        actor="system",
                        details={
                            "job_id": str(job.id),
                            "job_type": job.job_type,
                            "status": job.status,
                            "attempts": job.attempts,
                            "error_message": job.error_message,
                        },
                    )
                )

        # 3. Deterministic Validations
        validations = list(
            db.scalars(
                select(ValidationResult)
                .where(ValidationResult.document_id == document_id)
                .order_by(ValidationResult.created_at.asc())
            ).all()
        )
        if validations:
            grouped_vals: dict[datetime, list[ValidationResult]] = defaultdict(list)
            for v in validations:
                # Group by minute to synthesize validation evaluation run
                group_key = v.created_at.replace(microsecond=0)
                grouped_vals[group_key].append(v)

            for group_ts, items in grouped_vals.items():
                failed = [i for i in items if i.status == "FAILED"]
                warnings = [i for i in items if i.status == "WARNING"]
                passed = [i for i in items if i.status == "PASSED"]
                events.append(
                    TimelineEvent(
                        timestamp=group_ts,
                        event_type="validation:evaluated",
                        actor="system",
                        details={
                            "total_rules": len(items),
                            "passed_count": len(passed),
                            "failed_count": len(failed),
                            "warning_count": len(warnings),
                            "issues": [
                                {
                                    "code": i.validation_code,
                                    "field": i.field_name,
                                    "severity": i.severity,
                                    "message": i.message,
                                }
                                for i in (failed + warnings)
                            ],
                        },
                    )
                )

        # 4. Human Corrections
        corrections = list(
            db.scalars(
                select(DocumentCorrection)
                .options(joinedload(DocumentCorrection.user))
                .where(DocumentCorrection.document_id == document_id)
                .order_by(DocumentCorrection.created_at.asc(), DocumentCorrection.id.asc())
            ).unique().all()
        )
        for corr in corrections:
            events.append(
                TimelineEvent(
                    timestamp=corr.created_at,
                    event_type="correction:submitted",
                    actor=_build_actor_summary(corr.user),
                    details={
                        "field_name": corr.field_name,
                        "original_value": corr.original_value,
                        "corrected_value": corr.corrected_value,
                        "reason": corr.correction_reason,
                    },
                )
            )

        # 5. Review & Reconciliation Audit Log Entries
        audit_entries = audit_repo.get_audit_logs_for_document(db, document_id)
        for log in audit_entries:
            # Avoid repeating document:uploaded which was synthesized above
            if log.action in ("document:uploaded",):
                continue
            events.append(
                TimelineEvent(
                    timestamp=log.created_at,
                    event_type=log.action,
                    actor=_build_actor_summary(log.user),
                    details={
                        "action": log.action,
                        "entity_type": log.entity_type,
                        "entity_id": str(log.entity_id),
                        "old_values": log.old_values or {},
                        "new_values": log.new_values or {},
                    },
                )
            )

        # Sort newest first
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return DocumentHistoryResponse(
            document_id=doc.id,
            events=events,
        )
