from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RoleName(str, enum.Enum):
    FINANCE_EXECUTIVE = "FINANCE_EXECUTIVE"
    FINANCE_MANAGER = "FINANCE_MANAGER"
    ACCOUNTS_AUDIT = "ACCOUNTS_AUDIT"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


# Alias for backward-compatible imports across modules
UserRole = RoleName

ROLE_DESCRIPTIONS: dict[str, str] = {
    RoleName.FINANCE_EXECUTIVE.value: (
        "Upload and process financial documents, edit extractions, run reconciliation, and search."
    ),
    RoleName.FINANCE_MANAGER.value: (
        "Review and approve/reject manual corrections, view global audit logs, and all Finance Executive capabilities."
    ),
    RoleName.ACCOUNTS_AUDIT.value: (
        "View documents, run and view reconciliations, search documents, and view audit logs."
    ),
    RoleName.SYSTEM_ADMIN.value: (
        "Full system access including user and role management and failed job reprocessing."
    ),
}


class ActionTokenType(str, enum.Enum):
    INVITE = "INVITE"
    PASSWORD_RESET = "PASSWORD_RESET"


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "name IN ('FINANCE_EXECUTIVE', 'FINANCE_MANAGER', 'ACCOUNTS_AUDIT', 'SYSTEM_ADMIN')",
            name="ck_roles_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="role_rel")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
    )
    token_version: Mapped[int] = mapped_column(
        sa.Integer,
        default=0,
        server_default=sa.text("0"),
        nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    role_rel: Mapped[Role] = relationship("Role", back_populates="users", lazy="joined")
    documents = relationship(
        "Document",
        back_populates="uploader",
        foreign_keys="Document.uploaded_by",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    action_tokens: Mapped[list["UserActionToken"]] = relationship(
        "UserActionToken",
        back_populates="user",
        foreign_keys="UserActionToken.user_id",
        cascade="all, delete-orphan",
    )

    @property
    def role(self) -> str:
        if self.role_rel is not None:
            return self.role_rel.name
        return RoleName.ACCOUNTS_AUDIT.value

    @property
    def role_name(self) -> str:
        return self.role

    @property
    def name(self) -> str:
        return self.full_name

    @property
    def status(self) -> str:
        if self.is_active:
            return "active"
        if self.deactivated_at is None and self.last_login_at is None and self.invited_by is not None:
            return "invited"
        return "deactivated"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class UserActionToken(Base):
    __tablename__ = "user_action_tokens"
    __table_args__ = (
        CheckConstraint(
            "token_type IN ('INVITE', 'PASSWORD_RESET')",
            name="ck_user_action_tokens_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        "User",
        back_populates="action_tokens",
        foreign_keys=[user_id],
    )
