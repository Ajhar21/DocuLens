from __future__ import annotations

from typing import Optional

from app.ai.base import EmbeddingProvider, LLMProvider, PermanentAIError
from app.ai.fake import FakeEmbeddingProvider, FakeLLMProvider
from app.ai.gemini import GeminiEmbeddingProvider, GeminiLLMProvider
from app.core.config import settings

_llm_provider_override: Optional[LLMProvider] = None
_embedding_provider_override: Optional[EmbeddingProvider] = None


def set_llm_provider_override(provider: Optional[LLMProvider]) -> None:
    global _llm_provider_override
    _llm_provider_override = provider


def set_embedding_provider_override(provider: Optional[EmbeddingProvider]) -> None:
    global _embedding_provider_override
    _embedding_provider_override = provider


def get_llm_provider() -> LLMProvider:
    if _llm_provider_override is not None:
        return _llm_provider_override
    provider_name = (settings.LLM_PROVIDER or "gemini").strip().lower()
    if provider_name == "gemini":
        return GeminiLLMProvider()
    if provider_name == "fake":
        return FakeLLMProvider()
    raise PermanentAIError(f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'")


def get_embedding_provider() -> EmbeddingProvider:
    if _embedding_provider_override is not None:
        return _embedding_provider_override
    provider_name = (settings.EMBEDDING_PROVIDER or "gemini").strip().lower()
    if provider_name == "gemini":
        return GeminiEmbeddingProvider()
    if provider_name == "fake":
        return FakeEmbeddingProvider()
    raise PermanentAIError(f"Unsupported EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}'")

