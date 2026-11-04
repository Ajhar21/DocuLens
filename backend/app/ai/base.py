from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import math
import re
from typing import Any, Optional

from pydantic import ValidationError

from app.extraction.schemas import RawInvoiceLLM


class AIProviderError(Exception):
    """Base error for AI provider operations."""


class TransientAIError(AIProviderError):
    """Retryable error (HTTP 429 rate limit, 5xx server error, network timeout)."""


class PermanentAIError(AIProviderError):
    """Non-retryable error (auth/401/403, invalid API key, 400 bad request, dimension/count mismatch)."""


class LLMParseError(PermanentAIError):
    """Raised when LLM output is not valid JSON or violates the extraction response schema."""

    def __init__(
        self,
        message: str,
        raw_text: str,
        model_name: str,
        token_usage: Optional[dict[str, int]] = None,
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.model_name = model_name
        self.token_usage = token_usage


@dataclass(frozen=True)
class LLMResult:
    raw_text: str
    parsed: dict[str, Any]
    model_name: str
    token_usage: Optional[dict[str, int]] = None


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured LLM model identifier."""

    @abstractmethod
    def extract_invoice(
        self,
        document_text: str,
        *,
        repair_error: Optional[str] = None,
        previous_raw_output: Optional[str] = None,
    ) -> LLMResult:
        """Extract structured invoice data from untrusted document text."""


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured embedding model identifier."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Configured embedding vector dimensionality."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document chunks (RETRIEVAL_DOCUMENT) and return L2-normalized vectors."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (RETRIEVAL_QUERY) and return an L2-normalized vector."""


def sanitize_error_message(message: str, secrets: Optional[list[str]] = None) -> str:
    """Scrub API keys, query-param keys, and excessive payloads from error messages."""
    cleaned = (message or "AI provider error").strip()
    if secrets:
        for secret in secrets:
            if secret and len(secret) >= 4 and secret in cleaned:
                cleaned = cleaned.replace(secret, "[REDACTED]")
    cleaned = re.sub(r"([?&]key=)[^&\s\"']+", r"\1[REDACTED]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(AIza[0-9A-Za-z\-_]{15,})", "[REDACTED_API_KEY]", cleaned)
    if len(cleaned) > 600:
        cleaned = cleaned[:597] + "..."
    return cleaned


def l2_normalize_vector(vec: list[float]) -> list[float]:
    """L2-normalize a single embedding vector so its Euclidean norm is 1.0."""
    if not vec:
        raise PermanentAIError("Cannot L2-normalize an empty embedding vector")

    sum_sq = 0.0
    for val in vec:
        fval = float(val)
        if not math.isfinite(fval):
            raise PermanentAIError("Embedding vector contains non-finite value (NaN or Inf)")
        sum_sq += fval * fval

    norm = math.sqrt(sum_sq)
    if norm <= 0.0:
        raise PermanentAIError("Embedding vector has zero L2 norm and cannot be normalized")

    return [float(val) / norm for val in vec]


def validate_and_normalize_embeddings(
    raw_vectors: list[list[float]],
    expected_count: int,
    expected_dim: int,
) -> list[list[float]]:
    """Assert batch count and per-vector dimensionality, then L2-normalize every vector."""
    if not isinstance(raw_vectors, list):
        raise PermanentAIError(
            f"Expected list of embedding vectors, got {type(raw_vectors).__name__}"
        )
    if len(raw_vectors) != expected_count:
        raise PermanentAIError(
            f"Embedding count mismatch: sent {expected_count} input(s), received {len(raw_vectors)} vector(s)"
        )

    normalized_batch: list[list[float]] = []
    for idx, vec in enumerate(raw_vectors):
        if vec is None or len(vec) != expected_dim:
            actual_len = len(vec) if vec is not None else 0
            raise PermanentAIError(
                f"Embedding dimension mismatch at index {idx}: expected {expected_dim}, got {actual_len}"
            )
        normalized_batch.append(l2_normalize_vector(vec))

    return normalized_batch


def parse_and_validate_invoice_json(
    raw_text: str,
    model_name: str,
    token_usage: Optional[dict[str, int]] = None,
) -> LLMResult:
    """Parse raw JSON string and validate against RawInvoiceLLM schema."""
    text = (raw_text or "").strip()
    if not text:
        raise LLMParseError(
            "LLM returned empty response text",
            raw_text=raw_text or "",
            model_name=model_name,
            token_usage=token_usage,
        )

    # Strip optional markdown code fences if a provider wrapped JSON
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMParseError(
            f"Invalid JSON from LLM: {exc.msg} at line {exc.lineno} column {exc.colno}",
            raw_text=raw_text,
            model_name=model_name,
            token_usage=token_usage,
        ) from exc

    if not isinstance(loaded, dict):
        raise LLMParseError(
            f"Expected JSON object from LLM, got {type(loaded).__name__}",
            raw_text=raw_text,
            model_name=model_name,
            token_usage=token_usage,
        )

    try:
        validated = RawInvoiceLLM.model_validate(loaded)
    except ValidationError as exc:
        compact_errors = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"
            for err in exc.errors()[:5]
        )
        raise LLMParseError(
            f"LLM JSON failed schema validation: {compact_errors}",
            raw_text=raw_text,
            model_name=model_name,
            token_usage=token_usage,
        ) from exc

    return LLMResult(
        raw_text=raw_text,
        parsed=validated.model_dump(),
        model_name=model_name,
        token_usage=token_usage,
    )

