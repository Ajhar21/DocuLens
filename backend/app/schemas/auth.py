from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Optional[str] = None
    username: Optional[str] = None
    password: str = Field(..., min_length=1)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., min_length=10)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: Optional[str] = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=12, max_length=255)


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    token: str = Field(..., min_length=10, max_length=512)
    password: str = Field(..., min_length=12, max_length=255)
    full_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("full_name", "name"),
    )


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    token: str = Field(..., min_length=10, max_length=512)
    password: str = Field(
        ...,
        min_length=12,
        max_length=255,
        validation_alias=AliasChoices("password", "new_password"),
    )
