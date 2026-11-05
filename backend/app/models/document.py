from __future__ import annotations
import uuid
from datetime import datetime, timezone
import enum
from typing import Optional, List, TYPE_CHECKING
import sqlalchemy as sa
from sqlalchemy import CheckConstraint, String, BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import ProcessingJob
    from app.models.parse_result import DocumentParseResult
    from app.models.extraction import DocumentCorrection, ExtractedInvoice
    from app.models.validation import ValidationResult
    from app.models.chunk import DocumentChunk


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    NEEDS_REVIEW = "needs_review"
    IN_REVIEW = "in_review"
    CORRECTED = "corrected"
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'parsed', 'failed')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'needs_review', 'in_review', 'corrected', 'approved', 'rejected', 'not_required')",
            name="ck_documents_review_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_ext: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.UPLOADED.value, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32),
        default=ReviewStatus.PENDING.value,
        server_default=sa.text("'pending'"),
        nullable=False,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @property
    def processing_status(self) -> str:
        return self.status

    @processing_status.setter
    def processing_status(self, value: str) -> None:
        self.status = value

    uploader: Mapped[User] = relationship(
        "User",
        back_populates="documents",
        foreign_keys=[uploaded_by],
    )
    reviewer: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[reviewed_by],
    )
    jobs: Mapped[List[ProcessingJob]] = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan")
    parse_result: Mapped[Optional[DocumentParseResult]] = relationship("DocumentParseResult", back_populates="document", uselist=False, cascade="all, delete-orphan")
    extracted_invoice: Mapped[Optional[ExtractedInvoice]] = relationship("ExtractedInvoice", back_populates="document", uselist=False, cascade="all, delete-orphan")
    validation_results: Mapped[List[ValidationResult]] = relationship("ValidationResult", back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[List[DocumentChunk]] = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    corrections: Mapped[List[DocumentCorrection]] = relationship("DocumentCorrection", back_populates="document", cascade="all, delete-orphan")
