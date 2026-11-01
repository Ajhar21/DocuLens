"""Pytest fixtures for DocuLens tests.

Provides isolated database sessions and automatic cleanup of test-created jobs.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models.job import ProcessingJob
from app.db.session import SessionLocal


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a database session and clean up created test jobs afterwards."""
    session = SessionLocal()
    created_job_ids: list[uuid.UUID] = []

    # Helper monkeypatch or tracking can be done, but we can also track via an attached set
    session.info["test_job_ids"] = created_job_ids

    try:
        yield session
    finally:
        # Cleanup any jobs registered in session.info["test_job_ids"]
        if created_job_ids:
            try:
                session.rollback()
                session.execute(
                    delete(ProcessingJob).where(
                        ProcessingJob.id.in_(created_job_ids)
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
        session.close()

