from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import SearchResponse
from app.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "",
    response_model=APIResponse[SearchResponse],
    summary="Execute keyword, semantic, or hybrid search across documents",
)
def search_documents(
    q: str = Query(..., min_length=1, description="Search query string"),
    mode: str = Query(
        "hybrid",
        description="Search mode: keyword | semantic | hybrid",
    ),
    supplier_name: Optional[str] = Query(
        None, description="Pre-filter by supplier name"
    ),
    date_from: Optional[date] = Query(
        None, description="Pre-filter by invoice date from (inclusive)"
    ),
    date_to: Optional[date] = Query(
        None, description="Pre-filter by invoice date to (inclusive)"
    ),
    amount_min: Optional[Decimal] = Query(
        None, description="Pre-filter by minimum invoice total"
    ),
    amount_max: Optional[Decimal] = Query(
        None, description="Pre-filter by maximum invoice total"
    ),
    review_status: Optional[str] = Query(
        None, description="Pre-filter by document review status"
    ),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.SEARCH_USE)),
) -> APIResponse[SearchResponse]:
    result = SearchService.execute_search(
        db,
        current_user,
        query=q,
        mode=mode,
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    return ok(result, "Search completed successfully")

