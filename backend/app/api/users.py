from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.responses import APIResponse, ok
from app.db.session import get_db
from app.models.user import RoleName, User
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
from app.services import user_service


def _register_user_routes(target_router: APIRouter) -> None:
    @target_router.get("", response_model=APIResponse[list[UserRead]])
    def list_users(
        role: Optional[RoleName] = Query(default=None),
        is_active: Optional[bool] = Query(default=None),
        db: Session = Depends(get_db),
    ) -> APIResponse[list[UserRead]]:
        return ok(
            user_service.list_users(
                db,
                role=role.value if role is not None else None,
                is_active=is_active,
            )
        )

    @target_router.post("", response_model=APIResponse[UserRead], status_code=status.HTTP_201_CREATED)
    def create_user(
        payload: UserCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        created = user_service.create_user(db, payload, actor=current_user)
        return ok(created, "User created")

    @target_router.post(
        "/invite",
        response_model=APIResponse[UserInviteResponse],
        status_code=status.HTTP_201_CREATED,
    )
    def invite_user(
        payload: UserInviteRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserInviteResponse]:
        invited = user_service.invite_user(db, payload, actor=current_user)
        return ok(invited, "User invited")

    @target_router.get("/{user_id}", response_model=APIResponse[UserRead])
    def get_user(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
    ) -> APIResponse[UserRead]:
        return ok(user_service.get_user(db, user_id))

    @target_router.patch("/{user_id}", response_model=APIResponse[UserRead])
    def update_user(
        user_id: uuid.UUID,
        payload: UserUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        updated = user_service.update_user(db, user_id, payload, actor=current_user)
        return ok(updated, "User updated")

    @target_router.patch("/{user_id}/role", response_model=APIResponse[UserRead])
    def update_user_role(
        user_id: uuid.UUID,
        payload: UserRoleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        updated = user_service.update_user_role(db, user_id, payload, actor=current_user)
        return ok(updated, "User role updated")

    @target_router.patch("/{user_id}/status", response_model=APIResponse[UserRead])
    def update_user_status(
        user_id: uuid.UUID,
        payload: UserStatusUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        updated = user_service.update_user_status(db, user_id, payload, actor=current_user)
        return ok(updated, "User status updated")

    @target_router.post("/{user_id}/deactivate", response_model=APIResponse[UserRead])
    def deactivate_user(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        updated = user_service.deactivate_user(db, user_id, actor=current_user)
        return ok(updated, "User deactivated")

    @target_router.post("/{user_id}/reactivate", response_model=APIResponse[UserRead])
    def reactivate_user(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        updated = user_service.reactivate_user(db, user_id, actor=current_user)
        return ok(updated, "User reactivated")

    @target_router.post(
        "/{user_id}/resend-invite",
        response_model=APIResponse[UserInviteResponse],
    )
    def resend_invite(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserInviteResponse]:
        resent = user_service.resend_invite(db, user_id, actor=current_user)
        return ok(resent, "Invitation resent")

    @target_router.post("/{user_id}/revoke-invite", response_model=APIResponse[UserRead])
    def revoke_invite(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[UserRead]:
        revoked = user_service.revoke_invite(db, user_id, actor=current_user)
        return ok(revoked, "Invitation revoked")

    @target_router.post(
        "/{user_id}/reset-password",
        response_model=APIResponse[PasswordResetLinkResponse],
    )
    def request_password_reset(
        user_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
    ) -> APIResponse[PasswordResetLinkResponse]:
        reset_info = user_service.request_password_reset(db, user_id, actor=current_user)
        return ok(reset_info, "Password reset link generated")


router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_permission(Permission.USER_MANAGE))],
)
_register_user_routes(router)

admin_router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_permission(Permission.USER_MANAGE))],
)
_register_user_routes(admin_router)
