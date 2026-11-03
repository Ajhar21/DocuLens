from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.errors import AppError
from app.core.responses import APIResponse, ok
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import TokenResponse
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

_BEARER = {"WWW-Authenticate": "Bearer"}


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """OAuth2 password grant.

    The success body is a raw RFC 6749 token response (not enveloped) so standard
    OAuth2 clients and Swagger "Authorize" work. Errors are enveloped with a
    stable ``error.code``: ``invalid_credentials`` or ``account_inactive``.
    """
    email = form_data.username.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.password_hash):
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid email or password",
            headers=_BEARER,
        )

    if not user.is_active:
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "account_inactive",
            "User account is inactive",
            headers=_BEARER,
        )

    token = create_access_token(subject=str(user.id), role=user.role)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get(
    "/me",
    response_model=APIResponse[UserRead],
    dependencies=[Depends(require_role(UserRole.VIEWER, UserRole.REVIEWER, UserRole.ADMIN))],
)
def read_current_user(current_user: User = Depends(get_current_user)) -> APIResponse[UserRead]:
    return ok(UserRead.model_validate(current_user))
