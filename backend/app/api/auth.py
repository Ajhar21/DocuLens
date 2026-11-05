from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


async def _extract_login_credentials(request: Request) -> tuple[str, str]:
    """Parse either OAuth2 form-data (username/password) or JSON (email/password) in memory."""
    content_type = (request.headers.get("content-type") or "").lower()
    raw_email: Optional[str] = None
    raw_password: Optional[str] = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as exc:
            raise RequestValidationError(
                [{"loc": ("body",), "msg": "Invalid JSON payload", "type": "value_error.jsondecode"}]
            ) from exc
        if not isinstance(body, dict):
            raise RequestValidationError(
                [{"loc": ("body",), "msg": "Expected JSON object", "type": "type_error.dict"}]
            )
        parsed = LoginRequest.model_validate(body)
        raw_email = parsed.email or parsed.username
        raw_password = parsed.password
    else:
        form = await request.form()
        raw_email = str(form.get("username") or form.get("email") or "").strip() or None
        raw_password = str(form.get("password") or "") or None

    errors = []
    if not raw_email:
        errors.append({"loc": ("body", "username"), "msg": "Field required", "type": "missing"})
    if not raw_password:
        errors.append({"loc": ("body", "password"), "msg": "Field required", "type": "missing"})
    if errors:
        raise RequestValidationError(errors)

    assert raw_email is not None and raw_password is not None
    return raw_email, raw_password


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: tuple[str, str] = Depends(_extract_login_credentials),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate against the database users table and issue access + refresh tokens.

    Returns a raw RFC 6749 compatible token object (including ``access_token``,
    ``refresh_token``, ``token_type``, ``expires_in``, and ``user``) so OAuth2
    clients and Swagger Authorize work seamlessly.
    """
    email, password = credentials
    return user_service.authenticate_and_issue_tokens(db, email=email, password=password)


@router.post("/refresh", response_model=APIResponse[TokenResponse])
def refresh_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> APIResponse[TokenResponse]:
    """Rotate a valid refresh token and issue a fresh access + refresh token pair."""
    token_pair = user_service.refresh_access_token(db, payload.refresh_token)
    return ok(token_pair, "Token refreshed")


@router.post("/logout", response_model=APIResponse[dict[str, bool]])
def logout(
    payload: Optional[LogoutRequest] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[dict[str, bool]]:
    """Revoke active refresh tokens for the current user (or specific token family)."""
    raw_token = payload.refresh_token if payload is not None else None
    user_service.logout_user(db, current_user, raw_refresh_token=raw_token)
    return ok({"logged_out": True}, "Logged out successfully")


@router.get("/me", response_model=APIResponse[UserRead])
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserRead]:
    return ok(UserRead.model_validate(current_user))
