from __future__ import annotations

from typing import Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
import httpx

from app.ai.base import (
    AIProviderError,
    EmbeddingProvider,
    LLMProvider,
    LLMResult,
    PermanentAIError,
    TransientAIError,
    parse_and_validate_invoice_json,
    sanitize_error_message,
    validate_and_normalize_embeddings,
)
from app.core.config import settings
from app.extraction.prompts import (
    SYSTEM_INSTRUCTION,
    build_extraction_prompt,
    build_repair_prompt,
)
from app.extraction.schemas import RawInvoiceLLM


def _classify_gemini_exception(exc: Exception, api_key: str) -> AIProviderError:
    if isinstance(exc, AIProviderError):
        return exc

    secrets = [api_key] if api_key else []
    raw_msg = sanitize_error_message(str(exc), secrets=secrets)

    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, TimeoutError, ConnectionError)):
        return TransientAIError(f"Gemini network/timeout error: {raw_msg}")

    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        upper_msg = raw_msg.upper()
        if (
            "API_KEY_INVALID" in upper_msg
            or "API KEY NOT VALID" in upper_msg
            or "PERMISSION_DENIED" in upper_msg
            or "UNAUTHENTICATED" in upper_msg
        ):
            return PermanentAIError(f"Gemini authentication/key error (HTTP {code or 400}): {raw_msg}")
        if code in (408, 429, 500, 502, 503, 504) or isinstance(exc, genai_errors.ServerError):
            return TransientAIError(f"Gemini transient error (HTTP {code}): {raw_msg}")
        if code in (400, 401, 403, 404, 422) or isinstance(exc, genai_errors.ClientError):
            return PermanentAIError(f"Gemini client error (HTTP {code}): {raw_msg}")
        return TransientAIError(f"Gemini API error (HTTP {code}): {raw_msg}")

    return PermanentAIError(f"Unexpected Gemini provider error ({exc.__class__.__name__}): {raw_msg}")


class GeminiLLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else settings.GEMINI_API_KEY).strip()
        self._model_name = (model_name or settings.LLM_MODEL).strip()
        self._temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self) -> genai.Client:
        if not self._api_key:
            raise PermanentAIError("GEMINI_API_KEY is missing or empty")
        return genai.Client(api_key=self._api_key)

    def extract_invoice(
        self,
        document_text: str,
        *,
        repair_error: Optional[str] = None,
        previous_raw_output: Optional[str] = None,
    ) -> LLMResult:
        client = self._get_client()

        if repair_error:
            prompt = build_repair_prompt(
                document_text=document_text,
                previous_output=previous_raw_output or "",
                validation_error=repair_error,
            )
        else:
            prompt = build_extraction_prompt(document_text=document_text)

        try:
            response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=self._temperature,
                    response_mime_type="application/json",
                    response_schema=RawInvoiceLLM,
                ),
            )
        except Exception as exc:
            raise _classify_gemini_exception(exc, self._api_key) from exc

        raw_text = getattr(response, "text", None) or ""
        token_usage: Optional[dict[str, int]] = None
        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            token_usage = {
                "prompt_tokens": int(getattr(usage_meta, "prompt_token_count", 0) or 0),
                "completion_tokens": int(getattr(usage_meta, "candidates_token_count", 0) or 0),
                "total_tokens": int(getattr(usage_meta, "total_token_count", 0) or 0),
            }

        return parse_and_validate_invoice_json(
            raw_text=raw_text,
            model_name=self._model_name,
            token_usage=token_usage,
        )


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else settings.GEMINI_API_KEY).strip()
        self._model_name = (model_name or settings.EMBEDDING_MODEL).strip()
        self._dimension = dimension if dimension is not None else settings.EMBEDDING_DIM
        self._batch_size = batch_size if batch_size is not None else settings.EMBEDDING_BATCH_SIZE

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_client(self) -> genai.Client:
        if not self._api_key:
            raise PermanentAIError("GEMINI_API_KEY is missing or empty")
        return genai.Client(api_key=self._api_key)

    def _embed_batch(self, batch: list[str], task_type: str) -> list[list[float]]:
        client = self._get_client()
        try:
            response = client.models.embed_content(
                model=self._model_name,
                contents=batch,
                config=genai_types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self._dimension,
                ),
            )
        except Exception as exc:
            raise _classify_gemini_exception(exc, self._api_key) from exc

        embeddings_list = getattr(response, "embeddings", None) or []
        raw_vectors: list[list[float]] = [
            list(item.values) if getattr(item, "values", None) is not None else []
            for item in embeddings_list
        ]

        return validate_and_normalize_embeddings(
            raw_vectors=raw_vectors,
            expected_count=len(batch),
            expected_dim=self._dimension,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            normalized_batch = self._embed_batch(batch, task_type="RETRIEVAL_DOCUMENT")
            all_vectors.extend(normalized_batch)

        if len(all_vectors) != len(texts):
            raise PermanentAIError(
                f"Total embedding count mismatch: expected {len(texts)}, got {len(all_vectors)}"
            )
        return all_vectors

    def embed_query(self, text: str) -> list[float]:
        if not (text or "").strip():
            raise PermanentAIError("Cannot embed an empty search query")
        batch_result = self._embed_batch([text], task_type="RETRIEVAL_QUERY")
        return batch_result[0]

