"""User and authentication domain service.

Enforces RBAC role assignment, refresh token rotation with reuse detection,
token_version session invalidation, forced password change on first login,
single-use hashed invite & password-reset tokens, self-role/self-deactivation
prevention, last-active-SYSTEM_ADMIN protection (with row-level locking),
and transactional audit logging.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional
import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security import (
    create_access_token,
    generate_action_token,
    generate_refresh_token,
    hash_action_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import ActionTokenType, RoleName, User
from app.repositories import user_repo
from app.schemas.auth import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import (
    PasswordResetLinkResponse,
    UserCreate,
    UserInviteRequest,
    UserInviteResponse,
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
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role_name,
        token_version=int(user.token_version or 0),
    )
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

    now = datetime.now(timezone.utc)
    user.last_login_at = now
    user.updated_at = now
    db.flush()

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


def change_password(
    db: Session,
    current_user: User,
    payload: ChangePasswordRequest,
) -> UserRead:
    user = user_repo.get_user_by_id(db, current_user.id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    if not verify_password(payload.current_password, user.password_hash):
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_current_password",
            "Current password is incorrect",
        )

    if len(payload.new_password) < 12:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "password_too_short",
            "New password must be at least 12 characters long",
        )

    if payload.new_password == payload.current_password or verify_password(
        payload.new_password, user.password_hash
    ):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "password_unchanged",
            "New password must be different from the current password",
        )

    now = datetime.now(timezone.utc)
    old_must_change = bool(user.must_change_password)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.token_version = int(user.token_version or 0) + 1
    user.updated_at = now

    user_repo.revoke_user_refresh_tokens(db, user.id, now)

    AuditService.record(
        db,
        user_id=user.id,
        action="password.changed",
        entity_type="USER",
        entity_id=user.id,
        old_values={"must_change_password": old_must_change},
        new_values={
            "must_change_password": False,
            "target_user_id": str(user.id),
        },
    )
    db.commit()
    db.expire(user)
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


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
        must_change_password=False,
        token_version=0,
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
            "target_user_id": str(user.id),
        },
    )
    db.commit()
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


def invite_user(
    db: Session,
    payload: UserInviteRequest,
    actor: User,
) -> UserInviteResponse:
    now = datetime.now(timezone.utc)
    existing = user_repo.get_user_by_email(db, payload.email)
    if existing is not None:
        if existing.is_active:
            raise ConflictError("An active user with this email already exists")
        if existing.status != "invited":
            raise ConflictError(
                "A deactivated user with this email already exists; reactivate the account instead"
            )

    role_obj = user_repo.get_role_by_name(db, payload.role.value)
    default_name = (payload.full_name or payload.email.split("@")[0]).strip()

    if existing is None:
        user = User(
            email=payload.email,
            full_name=default_name,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role_id=role_obj.id,
            is_active=False,
            must_change_password=False,
            token_version=0,
            invited_by=actor.id,
            deactivated_at=None,
            last_login_at=None,
        )
        db.add(user)
        db.flush()
    else:
        user = existing
        user.role_id = role_obj.id
        if payload.full_name:
            user.full_name = payload.full_name.strip()
        user.invited_by = actor.id
        user.deactivated_at = None
        user.updated_at = now
        user_repo.revoke_unused_action_tokens(
            db,
            user_id=user.id,
            token_type=ActionTokenType.INVITE.value,
            now=now,
        )

    raw_token, token_hash = generate_action_token()
    expires_at = now + timedelta(hours=settings.INVITE_TTL_HOURS)
    user_repo.create_action_token(
        db,
        user_id=user.id,
        token_type=ActionTokenType.INVITE.value,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by=actor.id,
    )

    AuditService.record(
        db,
        user_id=actor.id,
        action="user.invited",
        entity_type="USER",
        entity_id=user.id,
        old_values=None,
        new_values={
            "email": user.email,
            "full_name": user.full_name,
            "role": role_obj.name,
            "status": "invited",
            "target_user_id": str(user.id),
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    invite_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/accept-invite?token={raw_token}"
    return UserInviteResponse(
        user=UserRead.model_validate(refreshed),
        invite_url=invite_url,
        invite_token=raw_token,
        expires_at=expires_at,
    )


def resend_invite(
    db: Session,
    user_id: uuid.UUID,
    actor: User,
) -> UserInviteResponse:
    now = datetime.now(timezone.utc)
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    if user.is_active or user.status != "invited":
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "user_not_invited",
            "User is not in invited state",
        )

    user_repo.revoke_unused_action_tokens(
        db,
        user_id=user.id,
        token_type=ActionTokenType.INVITE.value,
        now=now,
    )

    raw_token, token_hash = generate_action_token()
    expires_at = now + timedelta(hours=settings.INVITE_TTL_HOURS)
    user_repo.create_action_token(
        db,
        user_id=user.id,
        token_type=ActionTokenType.INVITE.value,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by=actor.id,
    )
    user.invited_by = actor.id
    user.updated_at = now

    AuditService.record(
        db,
        user_id=actor.id,
        action="user.invited",
        entity_type="USER",
        entity_id=user.id,
        old_values={"resent": True},
        new_values={
            "email": user.email,
            "role": user.role_name,
            "status": "invited",
            "target_user_id": str(user.id),
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    invite_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/accept-invite?token={raw_token}"
    return UserInviteResponse(
        user=UserRead.model_validate(refreshed),
        invite_url=invite_url,
        invite_token=raw_token,
        expires_at=expires_at,
    )


def revoke_invite(
    db: Session,
    user_id: uuid.UUID,
    actor: User,
) -> UserRead:
    now = datetime.now(timezone.utc)
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    if user.is_active or user.status != "invited":
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "user_not_invited",
            "User is not in invited state",
        )

    user_repo.revoke_unused_action_tokens(
        db,
        user_id=user.id,
        token_type=ActionTokenType.INVITE.value,
        now=now,
    )
    user.deactivated_at = now
    user.updated_at = now

    AuditService.record(
        db,
        user_id=actor.id,
        action="invite.revoked",
        entity_type="USER",
        entity_id=user.id,
        old_values={"status": "invited"},
        new_values={
            "status": "deactivated",
            "target_user_id": str(user.id),
        },
    )
    db.commit()
    db.expire(user)
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


def accept_invite(
    db: Session,
    payload: AcceptInviteRequest,
) -> TokenResponse:
    now = datetime.now(timezone.utc)
    if len(payload.password) < 12:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "password_too_short",
            "Password must be at least 12 characters long",
        )

    token_hash = hash_action_token(payload.token.strip())
    token_row = user_repo.get_action_token_for_update(
        db,
        token_hash=token_hash,
        token_type=ActionTokenType.INVITE.value,
    )
    if token_row is None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_invite_token",
            "Invalid invite token",
        )
    if token_row.used_at is not None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invite_token_used",
            "Invite token has already been used",
        )
    if token_row.revoked_at is not None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invite_token_revoked",
            "Invite token has been revoked",
        )
    if token_row.expires_at <= now:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invite_token_expired",
            "Invite token has expired",
        )

    user = user_repo.get_user_by_id(db, token_row.user_id, for_update=True)
    if user is None:
        raise NotFoundError("Invited user not found")

    user.password_hash = hash_password(payload.password)
    if payload.full_name and payload.full_name.strip():
        user.full_name = payload.full_name.strip()
    user.is_active = True
    user.deactivated_at = None
    user.must_change_password = False
    user.last_login_at = now
    user.token_version = int(user.token_version or 0) + 1
    user.updated_at = now
    token_row.used_at = now

    AuditService.record(
        db,
        user_id=user.id,
        action="invite.accepted",
        entity_type="USER",
        entity_id=user.id,
        old_values={"status": "invited", "is_active": False},
        new_values={
            "status": "active",
            "is_active": True,
            "target_user_id": str(user.id),
        },
    )

    token_resp, _ = _issue_token_pair(db, user)
    db.commit()
    return token_resp


def request_password_reset(
    db: Session,
    user_id: uuid.UUID,
    actor: User,
) -> PasswordResetLinkResponse:
    now = datetime.now(timezone.utc)
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    user_repo.revoke_unused_action_tokens(
        db,
        user_id=user.id,
        token_type=ActionTokenType.PASSWORD_RESET.value,
        now=now,
    )

    raw_token, token_hash = generate_action_token()
    expires_at = now + timedelta(hours=settings.INVITE_TTL_HOURS)
    user_repo.create_action_token(
        db,
        user_id=user.id,
        token_type=ActionTokenType.PASSWORD_RESET.value,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by=actor.id,
    )

    AuditService.record(
        db,
        user_id=actor.id,
        action="password.reset_requested",
        entity_type="USER",
        entity_id=user.id,
        old_values=None,
        new_values={
            "email": user.email,
            "target_user_id": str(user.id),
            "expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    reset_url = (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}/accept-invite?mode=reset&token={raw_token}"
    )
    return PasswordResetLinkResponse(
        user=UserRead.model_validate(refreshed),
        reset_url=reset_url,
        reset_token=raw_token,
        expires_at=expires_at,
    )


def complete_password_reset(
    db: Session,
    payload: ResetPasswordRequest,
) -> UserRead:
    now = datetime.now(timezone.utc)
    if len(payload.password) < 12:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "password_too_short",
            "Password must be at least 12 characters long",
        )

    token_hash = hash_action_token(payload.token.strip())
    token_row = user_repo.get_action_token_for_update(
        db,
        token_hash=token_hash,
        token_type=ActionTokenType.PASSWORD_RESET.value,
    )
    if token_row is None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_reset_token",
            "Invalid password reset token",
        )
    if token_row.used_at is not None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "reset_token_used",
            "Password reset token has already been used",
        )
    if token_row.revoked_at is not None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "reset_token_revoked",
            "Password reset token has been revoked",
        )
    if token_row.expires_at <= now:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "reset_token_expired",
            "Password reset token has expired",
        )

    user = user_repo.get_user_by_id(db, token_row.user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    user.password_hash = hash_password(payload.password)
    user.must_change_password = False
    user.token_version = int(user.token_version or 0) + 1
    user.updated_at = now
    token_row.used_at = now

    user_repo.revoke_user_refresh_tokens(db, user.id, now)

    AuditService.record(
        db,
        user_id=user.id,
        action="password.changed",
        entity_type="USER",
        entity_id=user.id,
        old_values=None,
        new_values={
            "via": "password_reset",
            "must_change_password": False,
            "target_user_id": str(user.id),
        },
    )
    db.commit()
    db.expire(user)
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

    # 1. Self-role-change guard
    if target_user.id == actor.id and new_role is not None:
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            "self_role_change_forbidden",
            "An administrator cannot change their own role",
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
    now = datetime.now(timezone.utc)
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
    session_invalidated = False

    if payload.full_name is not None and payload.full_name != user.full_name:
        user.full_name = payload.full_name
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_UPDATED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"full_name": old_name},
            new_values={"full_name": user.full_name, "target_user_id": str(user.id)},
        )

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        session_invalidated = True
        AuditService.record(
            db,
            user_id=actor.id,
            action="password.changed",
            entity_type="USER",
            entity_id=user.id,
            old_values=None,
            new_values={"password_changed": True, "target_user_id": str(user.id)},
        )

    if payload.role is not None and payload.role.value != old_role:
        role_obj = user_repo.get_role_by_name(db, payload.role.value)
        user.role_id = role_obj.id
        session_invalidated = True
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_ROLE_CHANGED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"role": old_role},
            new_values={"role": role_obj.name, "target_user_id": str(user.id)},
        )
        AuditService.record(
            db,
            user_id=actor.id,
            action="user.role_changed",
            entity_type="USER",
            entity_id=user.id,
            old_values={"role": old_role},
            new_values={"role": role_obj.name, "target_user_id": str(user.id)},
        )

    if payload.is_active is not None and payload.is_active != old_active:
        user.is_active = payload.is_active
        user.deactivated_at = None if user.is_active else now
        session_invalidated = True
        AuditService.record(
            db,
            user_id=actor.id,
            action="USER_STATUS_CHANGED",
            entity_type="USER",
            entity_id=user.id,
            old_values={"is_active": old_active},
            new_values={"is_active": user.is_active, "target_user_id": str(user.id)},
        )
        AuditService.record(
            db,
            user_id=actor.id,
            action="user.reactivated" if user.is_active else "user.deactivated",
            entity_type="USER",
            entity_id=user.id,
            old_values={"is_active": old_active},
            new_values={"is_active": user.is_active, "target_user_id": str(user.id)},
        )

    if session_invalidated:
        user.token_version = int(user.token_version or 0) + 1
        user_repo.revoke_user_refresh_tokens(db, user.id, now)

    user.updated_at = now
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


def deactivate_user(
    db: Session,
    user_id: uuid.UUID,
    actor: User,
) -> UserRead:
    now = datetime.now(timezone.utc)
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    _enforce_admin_protection_guards(
        db,
        target_user=user,
        actor=actor,
        new_role=None,
        new_is_active=False,
    )

    old_active = user.is_active
    old_status = user.status
    user.is_active = False
    user.deactivated_at = now
    user.token_version = int(user.token_version or 0) + 1
    user.updated_at = now

    user_repo.revoke_user_refresh_tokens(db, user.id, now)
    user_repo.revoke_unused_action_tokens(
        db,
        user_id=user.id,
        token_type=ActionTokenType.INVITE.value,
        now=now,
    )

    AuditService.record(
        db,
        user_id=actor.id,
        action="USER_STATUS_CHANGED",
        entity_type="USER",
        entity_id=user.id,
        old_values={"is_active": old_active, "status": old_status},
        new_values={"is_active": False, "status": "deactivated", "target_user_id": str(user.id)},
    )
    AuditService.record(
        db,
        user_id=actor.id,
        action="user.deactivated",
        entity_type="USER",
        entity_id=user.id,
        old_values={"is_active": old_active, "status": old_status},
        new_values={"is_active": False, "status": "deactivated", "target_user_id": str(user.id)},
    )
    db.commit()
    db.expire(user)
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)


def reactivate_user(
    db: Session,
    user_id: uuid.UUID,
    actor: User,
) -> UserRead:
    now = datetime.now(timezone.utc)
    user = user_repo.get_user_by_id(db, user_id, for_update=True)
    if user is None:
        raise NotFoundError("User not found")

    old_active = user.is_active
    old_status = user.status
    user.is_active = True
    user.deactivated_at = None
    user.token_version = int(user.token_version or 0) + 1
    user.updated_at = now

    AuditService.record(
        db,
        user_id=actor.id,
        action="USER_STATUS_CHANGED",
        entity_type="USER",
        entity_id=user.id,
        old_values={"is_active": old_active, "status": old_status},
        new_values={"is_active": True, "status": "active", "target_user_id": str(user.id)},
    )
    AuditService.record(
        db,
        user_id=actor.id,
        action="user.reactivated",
        entity_type="USER",
        entity_id=user.id,
        old_values={"is_active": old_active, "status": old_status},
        new_values={"is_active": True, "status": "active", "target_user_id": str(user.id)},
    )
    db.commit()
    db.expire(user)
    refreshed = user_repo.get_user_by_id(db, user.id)
    assert refreshed is not None
    return UserRead.model_validate(refreshed)
