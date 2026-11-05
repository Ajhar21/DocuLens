from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, documents, health, jobs, reconciliation, reviews, search, users
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal, get_db
from app.seed import seed_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _bootstrap_roles_and_admin(application: FastAPI) -> None:
    """Seed canonical roles and the .env SYSTEM_ADMIN user at startup."""
    override_fn = application.dependency_overrides.get(get_db)
    if override_fn is not None:
        gen = override_fn()
        db = next(gen)
        try:
            seed_admin(db, reset_password=False)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass
        return

    db = SessionLocal()
    try:
        seed_admin(db, reset_password=False)
    except Exception:
        logger.warning(
            "Startup admin seed skipped or deferred (database schema may not be migrated yet).",
            exc_info=True,
        )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(application: FastAPI):
    await run_in_threadpool(_bootstrap_roles_and_admin, application)
    yield


app = FastAPI(
    title="DocuLens API",
    version="0.1.0",
    description="AI Document Intelligence System",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Canonical PRD v1.1 API v1 mounts
for _router in (health.router, auth.router, users.router, documents.router, jobs.router, reviews.router, audit.router, reconciliation.router, search.router):
    app.include_router(_router, prefix="/api/v1")

# Backward-compatible /api aliases
for _router in (health.router, auth.router, users.router, documents.router, jobs.router, reviews.router, audit.router, reconciliation.router, search.router):
    app.include_router(_router, prefix="/api", include_in_schema=False)
