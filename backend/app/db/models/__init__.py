"""ORM models package. Import all models here so Alembic metadata discovery works."""

from app.db.models.job import ProcessingJob

__all__ = ["ProcessingJob"]

