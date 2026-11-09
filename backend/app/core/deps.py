from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user_allow_password_change(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        sub: str | None = payload.get("sub")
        if not sub:
            raise credentials_exception
        user_id = uuid.UUID(str(sub))
        token_tv = int(payload.get("tv", 0))
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.execute(
            select(User)
            .options(joinedload(User.role_rel))
            .where(User.id == user_id)
        )
        .scalars()
        .first()
    )
    if user is None or not user.is_active:
        raise credentials_exception
    if int(user.token_version or 0) != token_tv:
        raise credentials_exception
    return user


def get_current_user(
    user: User = Depends(get_current_user_allow_password_change),
) -> User:
    if user.must_change_password:
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "PASSWORD_CHANGE_REQUIRED",
            "Password change required before accessing this resource",
            data={"code": "PASSWORD_CHANGE_REQUIRED"},
        )
    return user
