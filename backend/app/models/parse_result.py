from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, List, Dict, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentParseResult(Base):
    __tablename__ = "document_parse_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    pages: Mapped[List[Any]] = mapped_column(JSONB, nullable=False, default=list)
    tables: Mapped[List[Any]] = mapped_column(JSONB, nullable=False, default=list)
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    document: Mapped[Document] = relationship("Document", back_populates="parse_result")

