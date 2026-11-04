from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def _ensure_roles_if_table_exists(db: Session) -> None:
    inspector = inspect(db.bind)
    if not inspector.has_table("roles"):
        return

    columns = [col["name"] for col in inspector.get_columns("roles")]
    role_col = "name" if "name" in columns else ("role" if "role" in columns else columns[0])

    existing_rows = db.execute(text(f"SELECT {role_col} FROM roles")).fetchall()
    existing_roles = {str(r[0]).lower() for r in existing_rows}

    for role_name in ("admin", "reviewer", "viewer"):
        if role_name not in existing_roles:
            db.execute(
                text(f"INSERT INTO roles ({role_col}) VALUES (:val)"),
                {"val": role_name},
            )
    db.commit()


def seed_admin(db: Session, reset_password: bool = False) -> str:
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    password = (settings.ADMIN_PASSWORD or "").strip()
    name = (getattr(settings, "ADMIN_NAME", None) or "Admin").strip()

    if not email or not password:
        print("Error: ADMIN_EMAIL and ADMIN_PASSWORD must be configured in settings / .env", file=sys.stderr)
        sys.exit(1)

    _ensure_roles_if_table_exists(db)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None:
        new_admin = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(new_admin)
        db.commit()
        print(f"created: admin user {email} created successfully")
        return "created"

    if reset_password:
        user.password_hash = hash_password(password)
        user.role = UserRole.ADMIN.value
        user.is_active = True
        if name:
            user.full_name = name
        db.commit()
        print(f"password reset: admin user {email} password reset successfully")
        return "password reset"

    needs_update = False
    if user.role != UserRole.ADMIN.value:
        user.role = UserRole.ADMIN.value
        needs_update = True
    if not user.is_active:
        user.is_active = True
        needs_update = True

    if needs_update:
        db.commit()
        print(f"updated: admin user {email} updated to active admin")
        return "updated"

    print(f"already existed: admin user {email} already exists and is active")
    return "already existed"


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Seed initial admin user")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset admin password to ADMIN_PASSWORD if user already exists",
    )
    args = parser.parse_args(argv)

    db: Session = SessionLocal()
    try:
        seed_admin(db, reset_password=args.reset_password)
    finally:
        db.close()


if __name__ == "__main__":
    main()

