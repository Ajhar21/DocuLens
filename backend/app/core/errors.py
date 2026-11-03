"""Domain errors and global exception handlers.

All error responses use the ``APIResponse`` envelope with ``success=false`` and
a stable ``error.code`` so clients never need to parse human-readable text.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import APIResponse, ErrorDetail, ErrorInfo

logger = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


class AppError(Exception):
    """Raised by services for expected failures; mapped to an envelope response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[list[ErrorDetail]] = None,
        headers: Optional[dict[str, str]] = None,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers
        self.data = data


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "not_found", message)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, "conflict", message)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[list[ErrorDetail]] = None,
    headers: Optional[dict[str, str]] = None,
    data: Any = None,
) -> JSONResponse:
    body = APIResponse[Any](
        success=False,
        message=message,
        data=data,
        error=ErrorInfo(code=code, details=details or []),
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        headers=headers,
    )


def _format_loc(loc: tuple[Any, ...] | list[Any]) -> Optional[str]:
    # Drop the transport prefix ("body", "query", ...) so clients get the field name.
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts) or None


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(
        exc.status_code, exc.code, exc.message, exc.details, exc.headers, exc.data
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        ErrorDetail(
            field=_format_loc(err.get("loc", ())),
            message=str(err.get("msg", "Invalid value")),
            type=str(err.get("type")) if err.get("type") else None,
        )
        for err in exc.errors()
    ]
    return error_response(
        422,
        "validation_error",
        "Request validation failed",
        details,
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
