from __future__ import annotations
import uuid
from datetime import datetime, timezone
import enum
from typing import Optional, TYPE_CHECKING
import sqlalchemy as sa
from sqlalchemy import CheckConstraint, String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class JobType(str, enum.Enum):
    PARSE = "parse"
    EXTRACTION = "extraction"
    EMBEDDING = "embedding"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_status_run_after", "status", "run_after"),
        Index(
            "uq_processing_jobs_active_doc_type",
            "document_id",
            "job_type",
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        ),
        CheckConstraint(
            "job_type IN ('parse', 'extraction', 'embedding')",
            name="ck_processing_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_processing_jobs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(50), default=JobType.PARSE.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def attempt_count(self) -> int:
        return self.attempts

    @property
    def error_message(self) -> Optional[str]:
        return self.last_error

    @property
    def completed_at(self) -> Optional[datetime]:
        return self.finished_at

    @completed_at.setter
    def completed_at(self, value: Optional[datetime]) -> None:
        self.finished_at = value

    document: Mapped[Document] = relationship("Document", back_populates="jobs")
