"""Application configuration via pydantic-settings.

All tunables live here. Environment variables override .env file values.
"""

from __future__ import annotations

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Worker tunables ───────────────────────────────────────────────
    WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    WORKER_MAX_ATTEMPTS: int = 3
    WORKER_BACKOFF_BASE_SECONDS: float = 5.0
    WORKER_STUCK_JOB_TIMEOUT_SECONDS: int = 300

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_url(self) -> str:
        """Normalize DATABASE_URL for SQLAlchemy 2 with the psycopg3 driver.

        Translates ``postgresql://`` → ``postgresql+psycopg://`` so that
        SQLAlchemy explicitly selects the psycopg (v3) driver instead of
        falling back to psycopg2.
        """
        url = str(self.DATABASE_URL)
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


settings = Settings()  # type: ignore[call-arg]

