from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar
import uuid

T = TypeVar("T")


@dataclass
class RankedItem(Generic[T]):
    item_id: uuid.UUID
    data: T
    rank: int  # 1-based rank
    score: float
    snippet: Optional[str] = None


@dataclass
class HybridFusionHit(Generic[T]):
    item_id: uuid.UUID
    data: T
    score: float
    match_type: str  # "KEYWORD" | "SEMANTIC" | "BOTH"
    keyword_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    snippet: Optional[str] = None


def compute_rrf(
    keyword_ranked: list[RankedItem[T]],
    semantic_ranked: list[RankedItem[T]],
    *,
    k: int = 60,
) -> list[HybridFusionHit[T]]:
    """Pure Reciprocal Rank Fusion (RRF) algorithm.

    Formula: RRF(d) = sum_{m} 1 / (k + rank_m(d))
    k default = 60 (standard TREC / information retrieval parameter).
    """
    keyword_map: dict[uuid.UUID, RankedItem[T]] = {item.item_id: item for item in keyword_ranked}
    semantic_map: dict[uuid.UUID, RankedItem[T]] = {item.item_id: item for item in semantic_ranked}

    all_ids = set(keyword_map.keys()) | set(semantic_map.keys())
    merged_hits: list[HybridFusionHit[T]] = []

    for item_id in all_ids:
        in_kw = item_id in keyword_map
        in_sem = item_id in semantic_map

        kw_rank = keyword_map[item_id].rank if in_kw else None
        sem_rank = semantic_map[item_id].rank if in_sem else None

        rrf_score = 0.0
        if in_kw and kw_rank is not None:
            rrf_score += 1.0 / (k + kw_rank)
        if in_sem and sem_rank is not None:
            rrf_score += 1.0 / (k + sem_rank)

        if in_kw and in_sem:
            match_type = "BOTH"
            # Prefer snippet from semantic if available, fallback to keyword
            snippet = semantic_map[item_id].snippet or keyword_map[item_id].snippet
            data = semantic_map[item_id].data
        elif in_kw:
            match_type = "KEYWORD"
            snippet = keyword_map[item_id].snippet
            data = keyword_map[item_id].data
        else:
            match_type = "SEMANTIC"
            snippet = semantic_map[item_id].snippet
            data = semantic_map[item_id].data

        merged_hits.append(
            HybridFusionHit(
                item_id=item_id,
                data=data,
                score=round(rrf_score, 6),
                match_type=match_type,
                keyword_rank=kw_rank,
                semantic_rank=sem_rank,
                snippet=snippet,
            )
        )

    # Sort descending by score; tie-break by lower rank sum
    merged_hits.sort(
        key=lambda h: (
            h.score,
            -( (h.keyword_rank or 9999) + (h.semantic_rank or 9999) ),
        ),
        reverse=True,
    )
    return merged_hits

