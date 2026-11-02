"""Standard API response envelope.

Every endpoint returns ``{success, message, data, error}`` for consistency.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Uniform response wrapper used by all API routes."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: T | None = None
    error: str | None = None

