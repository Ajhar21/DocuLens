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
    UserCreate,
    UserRead,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_permission(Permission.USER_MANAGE))],
)


@router.get("", response_model=APIResponse[list[UserRead]])
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


@router.post("", response_model=APIResponse[UserRead], status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
) -> APIResponse[UserRead]:
    created = user_service.create_user(db, payload, actor=current_user)
    return ok(created, "User created")


@router.get("/{user_id}", response_model=APIResponse[UserRead])
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> APIResponse[UserRead]:
    return ok(user_service.get_user(db, user_id))


@router.patch("/{user_id}", response_model=APIResponse[UserRead])
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
) -> APIResponse[UserRead]:
    updated = user_service.update_user(db, user_id, payload, actor=current_user)
    return ok(updated, "User updated")


@router.patch("/{user_id}/role", response_model=APIResponse[UserRead])
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
) -> APIResponse[UserRead]:
    updated = user_service.update_user_role(db, user_id, payload, actor=current_user)
    return ok(updated, "User role updated")


@router.patch("/{user_id}/status", response_model=APIResponse[UserRead])
def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.USER_MANAGE)),
) -> APIResponse[UserRead]:
    updated = user_service.update_user_status(db, user_id, payload, actor=current_user)
    return ok(updated, "User status updated")
