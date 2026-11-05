from decimal import Decimal
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
MIGRATION_EMBEDDING_DIM = 768


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
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90, description="Refresh token expiration in days")
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
    ADMIN_NAME: str = Field(default="Admin", description="Initial admin name")

    # Day 2 — AI Extraction, Validation & Embeddings
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    LLM_PROVIDER: str = Field(default="gemini", description="LLM provider identifier (gemini | fake)")
    LLM_MODEL: str = Field(default="gemini-2.5-flash", description="Pinned stable Gemini Flash model ID")
    LLM_TEMPERATURE: float = Field(default=0.0, description="LLM sampling temperature")
    LLM_MAX_INPUT_CHARS: int = Field(default=60000, description="Maximum input characters sent to LLM")
    EMBEDDING_PROVIDER: str = Field(default="gemini", description="Embedding provider identifier (gemini | fake)")
    EMBEDDING_MODEL: str = Field(default="gemini-embedding-001", description="Pinned embedding model ID")
    EMBEDDING_DIM: int = Field(default=MIGRATION_EMBEDDING_DIM, description="Vector embedding dimensionality")
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=100, description="Batch size for embedding API calls")
    VALIDATION_TOLERANCE: Decimal = Field(default=Decimal("0.01"), description="Monetary comparison tolerance in Decimal")
    RECONCILIATION_AMOUNT_TOLERANCE_ABSOLUTE: Decimal = Field(
        default=Decimal("0.05"),
        description="Absolute amount tolerance for reconciliation",
    )
    RECONCILIATION_AMOUNT_TOLERANCE_PERCENTAGE: Decimal = Field(
        default=Decimal("0.001"),
        description="Percentage amount tolerance for reconciliation (0.001 = 0.1%)",
    )
    RECONCILIATION_DATE_TOLERANCE_DAYS: int = Field(
        default=0,
        description="Allowed date difference in days for reconciliation",
    )
    # Day 3 — Search
    SEARCH_DEFAULT_LIMIT: int = Field(default=20, ge=1, le=100, description="Default search page limit")
    SEARCH_MAX_LIMIT: int = Field(default=100, ge=1, le=100, description="Max search page limit")
    SEARCH_MIN_SEMANTIC_SCORE: float = Field(default=0.6, ge=0.0, le=1.0, description="Default minimum cosine similarity score")
    SEARCH_RRF_K: int = Field(default=60, ge=1, description="Reciprocal Rank Fusion k constant")
    OCR_LOW_CONFIDENCE_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Threshold below which average OCR confidence triggers a LOW_OCR_CONFIDENCE INFO validation result",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("LLM_MODEL")
    @classmethod
    def reject_latest_alias(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.endswith("-latest"):
            raise ValueError(
                f"LLM_MODEL must be an explicit pinned model ID, not a '-latest' alias (got '{v}')"
            )
        return cleaned

    @model_validator(mode="after")
    def verify_embedding_dimension_matches_migration(self) -> "Settings":
        if self.EMBEDDING_DIM != MIGRATION_EMBEDDING_DIM:
            raise ValueError(
                f"Startup check failed: EMBEDDING_DIM={self.EMBEDDING_DIM} does not match "
                f"the document_chunks migration dimension ({MIGRATION_EMBEDDING_DIM})."
            )
        return self


settings = Settings()
