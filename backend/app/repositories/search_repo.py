from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.visibility import visible_documents_filter
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.extraction import ExtractedInvoice
from app.models.user import User
from app.search.rrf import RankedItem


@dataclass
class SearchCandidateFilter:
    supplier_name: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    review_status: Optional[str] = None

    def has_any_filter(self) -> bool:
        return any(
            [
                bool(self.supplier_name and self.supplier_name.strip()),
                self.date_from is not None,
                self.date_to is not None,
                self.amount_min is not None,
                self.amount_max is not None,
                bool(self.review_status and self.review_status.strip()),
            ]
        )


def get_candidate_ids_subquery(
    user: User,
    filters: SearchCandidateFilter,
) -> Any:
    """Pre-filters candidate documents based on metadata, invoice filters, and visibility.

    Applied in SQL BEFORE ranking/fusion so pagination and rank fusion operate
    strictly over visible, filtered candidates.
    """
    clauses = [
        visible_documents_filter(user),
    ]
    if filters.review_status:
        clauses.append(
            func.lower(Document.review_status) == filters.review_status.strip().lower()
        )
    if filters.supplier_name:
        clauses.append(
            ExtractedInvoice.supplier_name.ilike(f"%{filters.supplier_name.strip()}%")
        )
    if filters.date_from:
        clauses.append(ExtractedInvoice.invoice_date >= filters.date_from)
    if filters.date_to:
        clauses.append(ExtractedInvoice.invoice_date <= filters.date_to)
    if filters.amount_min is not None:
        clauses.append(ExtractedInvoice.total >= filters.amount_min)
    if filters.amount_max is not None:
        clauses.append(ExtractedInvoice.total <= filters.amount_max)

    return (
        select(Document.id.label("candidate_id"))
        .outerjoin(ExtractedInvoice, ExtractedInvoice.document_id == Document.id)
        .where(*clauses)
        .subquery()
    )


def keyword_search(
    db: Session,
    user: User,
    query_text: str,
    filters: SearchCandidateFilter,
    *,
    limit: int = 100,
) -> list[RankedItem[uuid.UUID]]:
    """Executes full-text tsvector search over document_chunks and trigram/ILIKE

    over extracted_invoices headers for all candidate documents.
    Groups results by document and returns 1-based ranked items.
    """
    candidates = get_candidate_ids_subquery(user, filters)
    ts_query = func.websearch_to_tsquery("english", query_text)
    rank_col = func.ts_rank(DocumentChunk.content_tsv, ts_query).label("rank_score")
    headline_col = func.ts_headline(
        "english",
        DocumentChunk.content,
        ts_query,
        "StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15",
    ).label("snippet")

    # Match chunks: pick best ranking chunk per document via DISTINCT ON
    chunk_stmt = (
        select(
            DocumentChunk.document_id,
            rank_col,
            headline_col,
        )
        .ext(distinct_on(DocumentChunk.document_id))
        .where(
            DocumentChunk.document_id.in_(select(candidates.c.candidate_id)),
            DocumentChunk.content_tsv.op("@@")(ts_query),
        )
        .order_by(DocumentChunk.document_id, rank_col.desc())
    )
    chunk_rows = db.execute(chunk_stmt).all()

    # Match invoice headers (supplier, customer, invoice_number)
    kw_pattern = f"%{query_text.strip()}%"
    inv_stmt = (
        select(
            ExtractedInvoice.document_id,
            ExtractedInvoice.invoice_number,
            ExtractedInvoice.supplier_name,
        )
        .where(
            ExtractedInvoice.document_id.in_(select(candidates.c.candidate_id)),
            or_(
                ExtractedInvoice.invoice_number.ilike(kw_pattern),
                ExtractedInvoice.supplier_name.ilike(kw_pattern),
                ExtractedInvoice.customer_name.ilike(kw_pattern),
            ),
        )
    )
    inv_rows = db.execute(inv_stmt).all()

    doc_scores: dict[uuid.UUID, float] = {}
    doc_snippets: dict[uuid.UUID, str] = {}

    for row in chunk_rows:
        doc_id = row.document_id
        score = float(row.rank_score or 0.0)
        doc_scores[doc_id] = score
        doc_snippets[doc_id] = row.snippet or ""

    for row in inv_rows:
        doc_id = row.document_id
        # Structured header matches receive a baseline boost
        inv_score = 0.5
        doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + inv_score
        if doc_id not in doc_snippets:
            doc_snippets[doc_id] = (
                f"Matched invoice #{row.invoice_number or ''} ({row.supplier_name or ''})"
            )

    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:limit]

    ranked_items: list[RankedItem[uuid.UUID]] = []
    for rank_idx, (doc_id, score) in enumerate(sorted_docs, start=1):
        ranked_items.append(
            RankedItem(
                item_id=doc_id,
                data=doc_id,
                rank=rank_idx,
                score=round(score, 4),
                snippet=doc_snippets.get(doc_id),
            )
        )
    return ranked_items


def semantic_search(
    db: Session,
    user: User,
    query_vector: list[float],
    filters: SearchCandidateFilter,
    *,
    min_score: float = 0.6,
    limit: int = 100,
) -> list[RankedItem[uuid.UUID]]:
    """Executes pgvector cosine distance search over document_chunks.

    Similarity = 1 - cosine_distance.
    Filters by min_score, groups by document (highest similarity chunk), and returns 1-based ranked items.
    """
    candidates = get_candidate_ids_subquery(user, filters)
    distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)
    similarity_expr = (1.0 - distance_expr).label("similarity")

    sem_stmt = (
        select(
            DocumentChunk.document_id,
            similarity_expr,
            DocumentChunk.content.label("content"),
        )
        .ext(distinct_on(DocumentChunk.document_id))
        .where(
            DocumentChunk.document_id.in_(select(candidates.c.candidate_id)),
            (1.0 - distance_expr) >= min_score,
        )
        .order_by(DocumentChunk.document_id, similarity_expr.desc())
    )
    rows = db.execute(sem_stmt).all()

    sorted_rows = sorted(rows, key=lambda r: float(r.similarity), reverse=True)[:limit]

    ranked_items: list[RankedItem[uuid.UUID]] = []
    for rank_idx, r in enumerate(sorted_rows, start=1):
        content = r.content or ""
        snippet = content[:200] + ("..." if len(content) > 200 else "")
        ranked_items.append(
            RankedItem(
                item_id=r.document_id,
                data=r.document_id,
                rank=rank_idx,
                score=round(float(r.similarity), 4),
                snippet=snippet,
            )
        )
    return ranked_items


def filter_only_search(
    db: Session,
    user: User,
    filters: SearchCandidateFilter,
    *,
    limit: int = 100,
) -> list[RankedItem[uuid.UUID]]:
    """Executes metadata-only filtering when no free-text query 'q' is provided.

    Orders matching visible documents by created_at DESC and attaches a preview snippet
    from the first document chunk when available.
    """
    candidates = get_candidate_ids_subquery(user, filters)

    docs_stmt = (
        select(Document.id)
        .where(Document.id.in_(select(candidates.c.candidate_id)))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
    )
    doc_ids = list(db.execute(docs_stmt).scalars().all())
    if not doc_ids:
        return []

    chunk_stmt = (
        select(DocumentChunk.document_id, DocumentChunk.content)
        .ext(distinct_on(DocumentChunk.document_id))
        .where(DocumentChunk.document_id.in_(doc_ids))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index.asc())
    )
    chunk_map: dict[uuid.UUID, str] = {}
    for row in db.execute(chunk_stmt).all():
        content = (row.content or "").strip()
        if content:
            chunk_map[row.document_id] = content[:200] + (
                "..." if len(content) > 200 else ""
            )

    ranked_items: list[RankedItem[uuid.UUID]] = []
    for rank_idx, doc_id in enumerate(doc_ids, start=1):
        ranked_items.append(
            RankedItem(
                item_id=doc_id,
                data=doc_id,
                rank=rank_idx,
                score=1.0,
                snippet=chunk_map.get(doc_id),
            )
        )
    return ranked_items


def fetch_documents_and_invoices(
    db: Session,
    document_ids: list[uuid.UUID],
) -> tuple[dict[uuid.UUID, Document], dict[uuid.UUID, ExtractedInvoice]]:
    """Fetches Document and ExtractedInvoice models for the given document IDs."""
    if not document_ids:
        return {}, {}

    docs = (
        db.execute(select(Document).where(Document.id.in_(document_ids)))
        .scalars()
        .all()
    )
    invoices = (
        db.execute(
            select(ExtractedInvoice).where(
                ExtractedInvoice.document_id.in_(document_ids)
            )
        )
        .scalars()
        .all()
    )

    doc_map = {d.id: d for d in docs}
    inv_map = {inv.document_id: inv for inv in invoices}
    return doc_map, inv_map
