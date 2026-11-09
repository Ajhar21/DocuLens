from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.models.user import RoleName


def _normalize_role_input(v: Any) -> Any:
    if v is None or isinstance(v, RoleName):
        return v
    if isinstance(v, str):
        cleaned = v.strip().upper()
        return RoleName(cleaned)
    return v


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("full_name", "name"),
    )
    password: str = Field(..., min_length=6, max_length=255)
    role: RoleName = Field(default=RoleName.ACCOUNTS_AUDIT)
    is_active: bool = Field(default=True)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("Invalid email address")
        return cleaned

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: Any) -> Any:
        return _normalize_role_input(v)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    full_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("full_name", "name"),
    )
    password: Optional[str] = Field(default=None, min_length=6, max_length=255)
    role: Optional[RoleName] = None
    is_active: Optional[bool] = None

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: Any) -> Any:
        return _normalize_role_input(v)


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleName

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: Any) -> Any:
        return _normalize_role_input(v)


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    email: str
    full_name: str
    role: RoleName
    is_active: bool
    status: str = "active"
    must_change_password: bool = False
    token_version: int = 0
    last_login_at: Optional[datetime] = None
    invited_by: Optional[uuid.UUID] = None
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class UserInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: str = Field(..., min_length=3, max_length=255)
    role: RoleName = Field(default=RoleName.ACCOUNTS_AUDIT)
    full_name: Optional[str] = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("full_name", "name"),
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("Invalid email address")
        return cleaned

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: Any) -> Any:
        return _normalize_role_input(v)


class UserInviteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRead
    invite_url: str
    invite_token: str
    expires_at: datetime


class PasswordResetLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRead
    reset_url: str
    reset_token: str
    expires_at: datetime


class UserSummary(BaseModel):
    """Minimal public identity embedded in other resources (no email/role)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    full_name: str
