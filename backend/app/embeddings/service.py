from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.base import EmbeddingProvider, PermanentAIError
from app.ai.registry import get_embedding_provider
from app.embeddings.chunker import ChunkSpec, chunk_parse_result
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.parse_result import DocumentParseResult


def run_document_embedding(
    session: Session,
    document_id: uuid.UUID,
    embedding_provider: Optional[EmbeddingProvider] = None,
    stage_callback: Optional[Callable[[str], None]] = None,
) -> list[DocumentChunk]:
    """Chunk parsed document text, generate normalized embeddings in batches,
    and atomically replace document_chunks in one transaction.
    """
    doc = session.get(Document, document_id)
    if doc is None:
        raise PermanentAIError(f"Document {document_id} not found")

    parse_result = session.execute(
        select(DocumentParseResult).where(DocumentParseResult.document_id == document_id)
    ).scalar_one_or_none()
    if parse_result is None:
        raise PermanentAIError(
            f"Cannot run embedding: no parse result found for document {document_id}"
        )

    if stage_callback:
        stage_callback("chunking")

    chunk_specs: list[ChunkSpec] = chunk_parse_result(parse_result)
    provider = embedding_provider or get_embedding_provider()

    if not chunk_specs:
        session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        session.flush()
        return []

    if stage_callback:
        stage_callback("embedding")

    texts = [spec.content for spec in chunk_specs]
    vectors = provider.embed_documents(texts)

    if len(vectors) != len(chunk_specs):
        raise PermanentAIError(
            f"Embedding alignment failure: {len(chunk_specs)} chunk(s) vs {len(vectors)} vector(s)"
        )

    if stage_callback:
        stage_callback("persisting")

    # Replace old chunks and insert new chunks inside one transaction
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )

    now = datetime.now(timezone.utc)
    persisted_chunks: list[DocumentChunk] = []
    for spec, vec in zip(chunk_specs, vectors):
        row = DocumentChunk(
            document_id=document_id,
            page_number=spec.page_number,
            chunk_index=spec.chunk_index,
            content=spec.content,
            embedding=vec,
            embedding_model=provider.model_name,
            created_at=now,
        )
        session.add(row)
        persisted_chunks.append(row)

    session.flush()
    return persisted_chunks

