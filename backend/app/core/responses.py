"""Standard API response envelope.

Every JSON endpoint returns ``{success, message, data, error}`` for consistency.
The single exception is ``POST /api/auth/login``, which must return a raw
RFC 6749 token response so OAuth2 clients (including Swagger "Authorize") work.
Its *error* responses are still enveloped by the global exception handlers.
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """A single machine-readable problem, e.g. one invalid field."""

    model_config = ConfigDict(extra="forbid")

    field: Optional[str] = None
    message: str
    type: Optional[str] = None


class ErrorInfo(BaseModel):
    """Stable error ``code`` for clients to branch on, plus optional details."""

    model_config = ConfigDict(extra="forbid")

    code: str
    details: list[ErrorDetail] = Field(default_factory=list)


class APIResponse(BaseModel, Generic[T]):
    """Uniform response wrapper used by all API routes."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: Optional[T] = None
    error: Optional[ErrorInfo] = None


def ok(data: T, message: str = "OK") -> APIResponse[T]:
    """Build a successful envelope."""
    return APIResponse[T](success=True, message=message, data=data, error=None)
