from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai.registry import get_embedding_provider
from app.core.config import settings
from app.models.user import User
from app.repositories import search_repo
from app.repositories.search_repo import SearchCandidateFilter
from app.schemas.search import (
    SearchDocumentSummary,
    SearchHit,
    SearchInvoiceSummary,
    SearchResponse,
)
from app.search.rrf import HybridFusionHit, RankedItem, compute_rrf
from app.validation.service import sync_legacy_pending_review_statuses


class SearchService:
    @staticmethod
    def execute_search(
        db: Session,
        user: User,
        *,
        query: Optional[str] = None,
        mode: str = "hybrid",
        supplier_name: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        amount_min: Optional[Decimal] = None,
        amount_max: Optional[Decimal] = None,
        review_status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResponse:
        sync_legacy_pending_review_statuses(db)

        cleaned_query = (query or "").strip()
        filters = SearchCandidateFilter(
            supplier_name=supplier_name,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
            review_status=review_status,
        )

        if not cleaned_query and not filters.has_any_filter():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide a search query 'q' or at least one metadata filter",
            )

        norm_mode = (mode or "hybrid").strip().lower()
        if norm_mode not in ("keyword", "semantic", "hybrid"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid search mode '{mode}'. Must be one of: keyword, semantic, hybrid",
            )

        effective_limit = min(max(1, limit), settings.SEARCH_MAX_LIMIT)
        effective_offset = max(0, offset)

        target_items: list[tuple[uuid.UUID, float, str, Optional[str]]] = []
        # Each item is (doc_id, score, match_type, snippet)

        if not cleaned_query:
            flt_items = search_repo.filter_only_search(
                db, user, filters, limit=settings.SEARCH_MAX_LIMIT
            )
            for it in flt_items:
                target_items.append((it.item_id, it.score, "FILTER", it.snippet))
        elif norm_mode == "keyword":
            kw_items = search_repo.keyword_search(
                db, user, cleaned_query, filters, limit=settings.SEARCH_MAX_LIMIT
            )
            for it in kw_items:
                target_items.append((it.item_id, it.score, "KEYWORD", it.snippet))

        elif norm_mode == "semantic":
            provider = get_embedding_provider()
            query_vec = provider.embed_query(cleaned_query)
            sem_items = search_repo.semantic_search(
                db,
                user,
                query_vec,
                filters,
                min_score=settings.SEARCH_MIN_SEMANTIC_SCORE,
                limit=settings.SEARCH_MAX_LIMIT,
            )
            for it in sem_items:
                target_items.append((it.item_id, it.score, "SEMANTIC", it.snippet))

        else:  # hybrid
            provider = get_embedding_provider()
            query_vec = provider.embed_query(cleaned_query)
            kw_items = search_repo.keyword_search(
                db, user, cleaned_query, filters, limit=settings.SEARCH_MAX_LIMIT
            )
            sem_items = search_repo.semantic_search(
                db,
                user,
                query_vec,
                filters,
                min_score=settings.SEARCH_MIN_SEMANTIC_SCORE,
                limit=settings.SEARCH_MAX_LIMIT,
            )
            fused = compute_rrf(kw_items, sem_items, k=settings.SEARCH_RRF_K)
            for h in fused:
                target_items.append((h.item_id, h.score, h.match_type, h.snippet))

        total_hits = len(target_items)
        page_slice = target_items[effective_offset : effective_offset + effective_limit]

        page_doc_ids = [item[0] for item in page_slice]
        doc_map, inv_map = search_repo.fetch_documents_and_invoices(db, page_doc_ids)

        hits: list[SearchHit] = []
        for doc_id, score, match_type, snippet in page_slice:
            doc = doc_map.get(doc_id)
            if not doc:
                continue

            inv = inv_map.get(doc_id)
            inv_summary: Optional[SearchInvoiceSummary] = None
            if inv:
                inv_summary = SearchInvoiceSummary(
                    invoice_number=inv.invoice_number,
                    supplier_name=inv.supplier_name,
                    customer_name=inv.customer_name,
                    invoice_date=inv.invoice_date,
                    total=inv.total,
                    currency=inv.currency,
                )

            hits.append(
                SearchHit(
                    document=SearchDocumentSummary(
                        id=doc.id,
                        original_filename=doc.original_filename,
                        status=doc.status,
                        review_status=doc.review_status,
                        created_at=doc.created_at,
                        uploaded_by=doc.uploaded_by,
                    ),
                    invoice=inv_summary,
                    snippet=snippet,
                    score=score,
                    match_type=match_type,  # type: ignore[arg-type]
                )
            )

        return SearchResponse(
            query=cleaned_query,
            mode="FILTER" if not cleaned_query else norm_mode.upper(),
            total_hits=total_hits,
            hits=hits,
        )

