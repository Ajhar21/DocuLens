from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.models.user import ROLE_DESCRIPTIONS, RefreshToken, Role, RoleName, User


def ensure_roles_seeded(db: Session) -> dict[str, Role]:
    """Idempotently ensure the 4 canonical roles exist in the ``roles`` table."""
    values = [
        {"name": role.value, "description": ROLE_DESCRIPTIONS.get(role.value)}
        for role in RoleName
    ]
    stmt = pg_insert(Role).values(values).on_conflict_do_nothing(index_elements=["name"])
    db.execute(stmt)
    db.flush()

    rows = db.execute(select(Role)).scalars().all()
    return {r.name: r for r in rows}


def get_role_by_name(db: Session, role_name: str) -> Role:
    role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
    if role is None:
        roles_map = ensure_roles_seeded(db)
        role = roles_map.get(role_name)
    if role is None:
        raise ValueError(f"Unknown role '{role_name}'")
    return role


def get_user_by_id(
    db: Session,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Optional[User]:
    stmt = select(User).options(joinedload(User.role_rel)).where(User.id == user_id)
    if for_update:
        stmt = stmt.with_for_update(of=User)
    return db.execute(stmt).scalars().first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    stmt = (
        select(User)
        .options(joinedload(User.role_rel))
        .where(User.email == email.strip().lower())
    )
    return db.execute(stmt).scalars().first()


def list_users(
    db: Session,
    *,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[User]:
    stmt = select(User).join(Role, User.role_id == Role.id).options(joinedload(User.role_rel))
    if role is not None:
        stmt = stmt.where(Role.name == role.strip().upper())
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    stmt = stmt.order_by(User.created_at.asc(), User.id.asc())
    return list(db.execute(stmt).scalars().all())


def lock_active_system_admin_ids(db: Session) -> list[uuid.UUID]:
    """Row-lock all active SYSTEM_ADMIN users to prevent concurrent removal of the last admin."""
    stmt = (
        select(User.id)
        .join(Role, User.role_id == Role.id)
        .where(
            Role.name == RoleName.SYSTEM_ADMIN.value,
            User.is_active.is_(True),
        )
        .with_for_update(of=User)
    )
    return list(db.execute(stmt).scalars().all())


def create_refresh_token_row(
    db: Session,
    *,
    user_id: uuid.UUID,
    token_hash: str,
    family_id: uuid.UUID,
    expires_at: datetime,
) -> RefreshToken:
    row = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return row


def get_refresh_token_for_update(
    db: Session,
    token_hash: str,
) -> Optional[RefreshToken]:
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update(of=RefreshToken)
    )
    return db.execute(stmt).scalar_one_or_none()


def revoke_refresh_token_family(
    db: Session,
    family_id: uuid.UUID,
    now: datetime,
) -> int:
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = db.execute(stmt)
    return int(result.rowcount or 0)


def revoke_user_refresh_tokens(
    db: Session,
    user_id: uuid.UUID,
    now: datetime,
) -> int:
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = db.execute(stmt)
    return int(result.rowcount or 0)

