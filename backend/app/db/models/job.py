"""ProcessingJob ORM model.

Maps the ``processing_jobs`` table from ERD.md.
Status and job_type are text + CHECK (easier to migrate than PG enums).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessingJob(Base):
    """Background processing job queue entry.

    Lifecycle: PENDING → PROCESSING → COMPLETED | FAILED
    """

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'PENDING'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        nullable=False,
        server_default=text("0"),
    )
    run_after: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    current_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "job_type IN ('DOCUMENT_PROCESSING', 'EMBEDDING')",
            name="ck_processing_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_processing_jobs_status",
        ),
        # Partial index: fast queue polling on PENDING jobs
        Index(
            "idx_processing_jobs_pending",
            "status",
            "run_after",
            postgresql_where=text("status = 'PENDING'"),
        ),
        # Partial unique index: at most one active job per (document_id, job_type)
        Index(
            "uq_processing_jobs_active_document_job",
            "document_id",
            "job_type",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'PROCESSING')"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingJob(id={self.id}, type={self.job_type}, "
            f"status={self.status}, attempt={self.attempt_count})>"
        )

