from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
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
    except (jwt.PyJWTError, ValueError):
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
    return user
