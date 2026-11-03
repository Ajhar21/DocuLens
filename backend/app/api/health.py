from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.responses import APIResponse, ok
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    database: str


@router.get("/health", response_model=APIResponse[HealthStatus])
def health_check(db: Session = Depends(get_db)) -> APIResponse[HealthStatus]:
    try:
        db.execute(text("SELECT 1"))
        return ok(HealthStatus(status="ok", database="connected"))
    except Exception:
        logger.warning("Health check: database unreachable", exc_info=True)
        return ok(HealthStatus(status="degraded", database="disconnected"), "Degraded")
