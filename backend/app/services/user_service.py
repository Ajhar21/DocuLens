"""User and authentication domain service.

Enforces RBAC role assignment, refresh token rotation with reuse detection,
self-demotion / self-deactivation prevention, last-active-SYSTEM_ADMIN
protection (with row-level locking), and transactional audit logging.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RoleName, User
from app.repositories import user_repo
from app.schemas.auth import TokenResponse
from app.schemas.user import (
    UserCreate,
    UserRead,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.audit_service import AuditService

_BEARER = {"WWW-Authenticate": "Bearer"}


def _issue_token_pair(
    db: Session,
    user: User,
    *,
    family_id: Optional[uuid.UUID] = None,
) -> tuple[TokenResponse, uuid.UUID]:
    now = datetime.now(timezone.utc)
    access_token = create_access_token(subject=str(user.id), role=user.role_name)
    raw_refresh, refresh_hash = generate_refresh_token()
    token_family_id = family_id or uuid.uuid4()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_row = user_repo.create_refresh_token_row(
        db,
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=token_family_id,
        expires_at=expires_at,
    )
    response = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )
    return response, refresh_row.id


def authenticate_and_issue_tokens(
    db: Session,
    email: str,
    password: str,
) -> TokenResponse:
    cleaned_email = (email or "").strip().lower()
    user = user_repo.get_user_by_email(db, cleaned_email)

    if user is None or not verify_password(password, user.password_hash):
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

    token_resp, _ = _issue_token_pair(db, user)
    db.commit()
    return token_resp


def refresh_access_token(db: Session, raw_refresh_token: str) -> TokenResponse:
    now = datetime.now(timezone.utc)
    token_hash = hash_refresh_token(raw_refresh_token.strip())
    token_row = user_repo.get_refresh_token_for_update(db, token_hash)

    if token_row is None:
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_refresh_token",
            "Invalid refresh token",
            headers=_BEARER,
        )

    # Reuse detection: if a previously rotated/revoked token is replayed, revoke the entire family
    if token_row.revoked_at is not None:
        user_repo.revoke_refresh_token_family(db, token_row.family_id, now)
        db.commit()
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "refresh_token_reused",
            "Refresh token has already been used or revoked; session family invalidated",
            headers=_BEARER,
        )

    if token_row.expires_at <= now:
        token_row.revoked_at = now
        db.commit()
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "refresh_token_expired",
            "Refresh token has expired",
            headers=_BEARER,
        )

    user = user_repo.get_user_by_id(db, token_row.user_id)
    if user is None or not user.is_active:
        user_repo.revoke_refresh_token_family(db, token_row.family_id, now)
        db.commit()
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "account_inactive",
            "User account is inactive",
            headers=_BEARER,
        )

    token_resp, new_token_id = _issue_token_pair(db, user, family_id=token_row.family_id)
    token_row.revoked_at = now
    token_row.replaced_by_id = new_token_id
    db.commit()
    return token_resp


def logout_user(
    db: Session,
    current_user: User,
    raw_refresh_token: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc)
    if raw_refresh_token:
        token_hash = hash_refresh_token(raw_refresh_token.strip())
        token_row = user_repo.get_refresh_token_for_update(db, token_hash)
        if token_row is not None and token_row.user_id == current_user.id:
            user_repo.revoke_refresh_token_family(db, token_row.family_id, now)
        else:
            user_repo.revoke_user_refresh_tokens(db, current_user.id, now)
    else:
        user_repo.revoke_user_refresh_tokens(db, current_user.id, now)
    db.commit()


def list_users(
    db: Session,
    *,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[UserRead]:
    users = user_repo.list_users(db, role=role, is_active=is_active)
    return [UserRead.model_validate(u) for u in users]


def get_user(db: Session, user_id: uuid.UUID) -> UserRead:
    user = user_repo.get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserRead.model_validate(user)


def create_user(db: Session, payload: UserCreate, actor: User) -> UserRead:
    existing = user_repo.get_user_by_email(db, payload.email)
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    role_obj = user_repo.get_role_by_name(db, payload.role.value)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role_id=role_obj.id,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()

    AuditService.record(
        db,
        user_id=actor.id,
        action="USER_CREATED",
        entity_type="USER",
        entity_id=user.id,
        old_values=None,
        new_values={
            "email": user.email,
            "full_name": user.full_name,
            "role": role_obj.name,
            "is_active": user.is_active,
        },
    )
    db.commit()
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


def _enforce_admin_protection_guards(
    db: Session,
    *,
    target_user: User,
    actor: User,
    new_role: Optional[RoleName],
    new_is_active: Optional[bool],
) -> None:
    effective_role = new_role.value if new_role is not None else target_user.role_name
    effective_active = new_is_active if new_is_active is not None else target_user.is_active

    # 1. Self-demotion guard
    if (
        target_user.id == actor.id
        and new_role is not None
        and new_role != RoleName.SYSTEM_ADMIN
    ):
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "self_role_change_forbidden",
            "An administrator cannot demote themselves",
        )

    # 2. Self-deactivation guard
    if target_user.id == actor.id and new_is_active is False:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "self_deactivation_forbidden",
            "An administrator cannot deactivate their own account",
        )

    # 3. Last active SYSTEM_ADMIN guard (with FOR UPDATE lock on active admins)
    was_active_admin = (
        target_user.role_name == RoleName.SYSTEM_ADMIN.value and target_user.is_active
    )
    will_be_active_admin = (
        effective_role == RoleName.SYSTEM_ADMIN.value and effective_active
    )
    if was_active_admin and not will_be_active_admin:
        active_admin_ids = user_repo.lock_active_system_admin_ids(db)
        remaining_ids = [uid for uid in active_admin_ids if uid != target_user.id]
        if len(remaining_ids) == 0:
            raise ConflictError("Cannot remove or deactivate the last active SYSTEM_ADMIN")


def update_user(
    db: Session,
    user_id: uuid.UUID,
    payload: UserUpdate,
    actor: User,
) -> UserRead:
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    _enforce_admin_protection_guards(
        db,
        target_user=user,
        actor=actor,
        new_role=payload.role,
        new_is_active=payload.is_active,
    )

    old_role = user.role_name
    old_active = user.is_active
    old_name = user.full_name

    if payload.full_name is not None and payload.full_name != user.full_name:
        user.full_name = payload.full_name
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_UPDATED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"full_name": old_name},
            new_values={"full_name": user.full_name},
        )

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_PASSWORD_CHANGED",
            entity_type="USER",
            entity_id=user.id,
            old_values=None,
            new_values={"password_changed": True},
        )

    if payload.role is not None and payload.role.value != old_role:
        role_obj = user_repo.get_role_by_name(db, payload.role.value)
        user.role_id = role_obj.id
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_ROLE_CHANGED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"role": old_role},
            new_values={"role": role_obj.name},
        )

    if payload.is_active is not None and payload.is_active != old_active:
        user.is_active = payload.is_active
        if not user.is_active:
            user_repo.revoke_user_refresh_tokens(
                db, user.id, datetime.now(timezone.utc)
            )
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_STATUS_CHANGED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"is_active": old_active},
            new_values={"is_active": user.is_active},
        )

    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.expire(user)
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


def update_user_role(
    db: Session,
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    actor: User,
) -> UserRead:
    return update_user(
        db,
        user_id,
        UserUpdate(role=payload.role),
        actor,
    )


def update_user_status(
    db: Session,
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    actor: User,
) -> UserRead:
    return update_user(
        db,
        user_id,
        UserUpdate(is_active=payload.is_active),
        actor,
    )

