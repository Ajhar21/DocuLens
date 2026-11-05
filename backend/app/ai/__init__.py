from app.ai.base import (
    AIProviderError,
    EmbeddingProvider,
    LLMParseError,
    LLMProvider,
    LLMResult,
    PermanentAIError,
    TransientAIError,
    l2_normalize_vector,
    parse_and_validate_invoice_json,
    sanitize_error_message,
    validate_and_normalize_embeddings,
)
from app.ai.fake import DEFAULT_CANNED_INVOICE, FakeEmbeddingProvider, FakeLLMProvider
from app.ai.gemini import GeminiEmbeddingProvider, GeminiLLMProvider
from app.ai.registry import (
    get_embedding_provider,
    get_llm_provider,
    set_embedding_provider_override,
    set_llm_provider_override,
)

__all__ = [
    "AIProviderError",
    "TransientAIError",
    "PermanentAIError",
    "LLMParseError",
    "LLMResult",
    "LLMProvider",
    "EmbeddingProvider",
    "GeminiLLMProvider",
    "GeminiEmbeddingProvider",
    "FakeLLMProvider",
    "FakeEmbeddingProvider",
    "DEFAULT_CANNED_INVOICE",
    "get_llm_provider",
    "get_embedding_provider",
    "set_llm_provider_override",
    "set_embedding_provider_override",
    "l2_normalize_vector",
    "validate_and_normalize_embeddings",
    "parse_and_validate_invoice_json",
    "sanitize_error_message",
]

