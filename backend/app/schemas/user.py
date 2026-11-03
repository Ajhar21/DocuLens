from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=255)
    role: UserRole = Field(default=UserRole.VIEWER)
    is_active: bool = Field(default=True)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("Invalid email address")
        return cleaned


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserSummary(BaseModel):
    """Minimal public identity embedded in other resources (no email/role)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    full_name: str
