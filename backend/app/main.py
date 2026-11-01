"""FastAPI application entry point.

Mounts routers, configures error handlers, and exposes the /health
endpoint. This is the only file that knows about HTTP; business logic
lives in module services.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from app.core.responses import APIResponse
from app.db.session import check_db_health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app = FastAPI(
    title="DocuLens API",
    version="0.1.0",
    description="Intelligent Document Processing Platform",
)


@app.get("/health", response_model=APIResponse)
def health_check() -> APIResponse:
    """Verify API and database connectivity.

    This is a sync ``def`` route — FastAPI dispatches it to a thread pool
    so the async event loop is never blocked by the synchronous DB call.
    """
    healthy = check_db_health()
    return APIResponse(
        success=healthy,
        message="DocuLens API is healthy" if healthy else "DocuLens API is degraded",
        data={
            "status": "healthy" if healthy else "degraded",
            "database": "connected" if healthy else "disconnected",
        },
        error=None if healthy else "Database connection failed",
    )

