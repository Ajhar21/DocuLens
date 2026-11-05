from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import enum
from typing import Optional, TYPE_CHECKING
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class ReconciliationType(str, enum.Enum):
    PDF_PDF = "PDF_PDF"
    PDF_EXCEL = "PDF_EXCEL"


class ReconciliationOverallStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    ERROR = "ERROR"


class ReconciliationEntityType(str, enum.Enum):
    HEADER = "HEADER"
    LINE_ITEM = "LINE_ITEM"


class MatchStatus(str, enum.Enum):
    EXACT_MATCH = "EXACT_MATCH"
    TOLERANCE_MATCH = "TOLERANCE_MATCH"
    MISMATCH = "MISMATCH"
    MISSING_IN_A = "MISSING_IN_A"
    MISSING_IN_B = "MISSING_IN_B"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ReconciliationJob(Base):
    __tablename__ = "reconciliation_jobs"
    __table_args__ = (
        Index("ix_reconciliation_jobs_doc_a", "document_id_a"),
        Index("ix_reconciliation_jobs_doc_b", "document_id_b"),
        Index("ix_reconciliation_jobs_user_initiated", "initiated_by", "initiated_at"),
        Index("ix_reconciliation_jobs_status", "overall_status"),
        CheckConstraint(
            "reconciliation_type IN ('PDF_PDF', 'PDF_EXCEL')",
            name="ck_reconciliation_jobs_type",
        ),
        CheckConstraint(
            "overall_status IN ('MATCHED', 'MISMATCHED', 'ERROR')",
            name="ck_reconciliation_jobs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id_a: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id_b: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reconciliation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    discrepancy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    initiator: Mapped[User] = relationship("User", foreign_keys=[initiated_by], lazy="joined")
    document_a: Mapped[Document] = relationship("Document", foreign_keys=[document_id_a], lazy="joined")
    document_b: Mapped[Document] = relationship("Document", foreign_keys=[document_id_b], lazy="joined")
    results: Mapped[list[ReconciliationResult]] = relationship(
        "ReconciliationResult",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ReconciliationResult.created_at.asc()",
    )


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    __table_args__ = (
        Index("ix_reconciliation_results_job_id", "job_id"),
        Index("ix_reconciliation_results_match_status", "match_status"),
        CheckConstraint(
            "entity_type IN ('HEADER', 'LINE_ITEM')",
            name="ck_reconciliation_results_entity",
        ),
        CheckConstraint(
            "match_status IN ('EXACT_MATCH', 'TOLERANCE_MATCH', 'MISMATCH', 'MISSING_IN_A', 'MISSING_IN_B', 'NOT_COMPARABLE')",
            name="ck_reconciliation_results_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reconciliation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_a_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_b_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    absolute_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(19, 4), nullable=True)
    percentage_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    job: Mapped[ReconciliationJob] = relationship("ReconciliationJob", back_populates="results")

