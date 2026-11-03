from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.errors import ConflictError, NotFoundError
from app.core.responses import APIResponse, ok
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("", response_model=APIResponse[list[UserRead]])
def list_users(db: Session = Depends(get_db)) -> APIResponse[list[UserRead]]:
    users = db.execute(select(User).order_by(User.created_at.asc())).scalars().all()
    return ok([UserRead.model_validate(u) for u in users])


@router.post("", response_model=APIResponse[UserRead], status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> APIResponse[UserRead]:
    existing = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok(UserRead.model_validate(user), "User created")


@router.patch("/{user_id}", response_model=APIResponse[UserRead])
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
) -> APIResponse[UserRead]:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role.value
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return ok(UserRead.model_validate(user), "User updated")
