from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(..., description="PostgreSQL session pooler connection URL")
    TEST_SCHEMA: str = Field(default="doculens_test", description="Isolated test schema")
    JWT_SECRET: str = Field(..., description="Secret key for JWT generation and verification")
    JWT_EXPIRE_MINUTES: int = Field(default=60, description="JWT expiration in minutes")
    STORAGE_DIR: str = Field(default=str(BACKEND_DIR / "storage"), description="Base storage directory for uploaded files")
    MAX_UPLOAD_MB: int = Field(default=25, description="Maximum upload size in megabytes")
    WORKER_POLL_SECONDS: float = Field(default=2.0, description="Worker loop polling interval in seconds")
    JOB_STALE_MINUTES: int = Field(default=10, description="Minutes after which a running job is deemed stale")
    PDF_MIN_TEXT_CHARS: int = Field(default=50, description="Minimum characters for text layer before falling back to OCR")
    OCR_DPI: int = Field(default=300, description="Rasterization DPI for PDF OCR fallback")
    MAX_PREVIEW_ROWS: int = Field(default=100, description="Max preview rows stored in table parsing")
    CORS_ORIGINS: Union[str, List[str]] = Field(default=["http://localhost:5173"], description="Allowed CORS origins")
    ADMIN_EMAIL: str = Field(..., description="Initial admin email")
    ADMIN_PASSWORD: str = Field(..., description="Initial admin password")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
