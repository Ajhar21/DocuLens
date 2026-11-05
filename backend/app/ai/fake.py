from __future__ import annotations

import hashlib
import json
import struct
from typing import Any, Optional, Union

from app.ai.base import (
    EmbeddingProvider,
    LLMProvider,
    LLMResult,
    parse_and_validate_invoice_json,
    validate_and_normalize_embeddings,
)
from app.core.config import settings


DEFAULT_CANNED_INVOICE: dict[str, Any] = {
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-01-15",
    "supplier_name": "Acme Industrial Supplies Ltd.",
    "customer_name": "DocuLens Corp",
    "subtotal": "1,000.00",
    "tax": "100.00",
    "total": "1,100.00",
    "currency": "USD",
    "discount": None,
    "shipping": None,
    "self_reported_confidence": 0.95,
    "line_items": [
        {
            "description": "Precision Widget Model A",
            "quantity": "4",
            "unit_price": "150.00",
            "amount": "600.00",
        },
        {
            "description": "Calibration Service",
            "quantity": "2",
            "unit_price": "200.00",
            "amount": "400.00",
        },
    ],
}


class FakeLLMProvider(LLMProvider):
    """Deterministic, zero-network LLM provider for automated tests."""

    def __init__(
        self,
        responses: Optional[list[Union[str, dict[str, Any], Exception]]] = None,
        model_name: str = "fake-gemini-flash",
    ) -> None:
        self._model_name = model_name
        self._responses: list[Union[str, dict[str, Any], Exception]] = (
            list(responses) if responses is not None else [DEFAULT_CANNED_INVOICE]
        )
        self.calls: list[dict[str, Optional[str]]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    def extract_invoice(
        self,
        document_text: str,
        *,
        repair_error: Optional[str] = None,
        previous_raw_output: Optional[str] = None,
    ) -> LLMResult:
        self.calls.append(
            {
                "document_text": document_text,
                "repair_error": repair_error,
                "previous_raw_output": previous_raw_output,
            }
        )
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        item = self._responses[idx]

        if isinstance(item, Exception):
            raise item

        if isinstance(item, dict):
            raw_text = json.dumps(item)
        else:
            raw_text = str(item)

        return parse_and_validate_invoice_json(
            raw_text=raw_text,
            model_name=self._model_name,
            token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic SHA-256 hash-based embedding provider producing normalized vectors of EMBEDDING_DIM."""

    def __init__(
        self,
        dimension: Optional[int] = None,
        model_name: str = "fake-embedding-001",
    ) -> None:
        self._dimension = dimension if dimension is not None else settings.EMBEDDING_DIM
        self._model_name = model_name
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _deterministic_vector(self, text: str, prefix: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self._dimension:
            digest = hashlib.sha256(f"{prefix}:{counter}:{text}".encode("utf-8")).digest()
            # Unpack 8 signed 32-bit integers per 32-byte SHA-256 digest and scale to [-1, 1]
            ints = struct.unpack(">8i", digest)
            for val in ints:
                if len(values) < self._dimension:
                    values.append((val / 2147483648.0) or 0.001)
            counter += 1
        return values

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        if not texts:
            return []
        raw_vectors = [self._deterministic_vector(t, prefix="doc") for t in texts]
        return validate_and_normalize_embeddings(
            raw_vectors=raw_vectors,
            expected_count=len(texts),
            expected_dim=self._dimension,
        )

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        raw_vectors = [self._deterministic_vector(text, prefix="query")]
        return validate_and_normalize_embeddings(
            raw_vectors=raw_vectors,
            expected_count=1,
            expected_dim=self._dimension,
        )[0]

