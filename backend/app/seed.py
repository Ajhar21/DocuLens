from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import sys
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import RoleName, User
from app.repositories import user_repo

logger = logging.getLogger(__name__)


def seed_admin(db: Session, reset_password: bool = False) -> str:
    """Idempotently seed the 4 canonical roles and the .env SYSTEM_ADMIN user."""
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    password = (settings.ADMIN_PASSWORD or "").strip()
    name = (getattr(settings, "ADMIN_NAME", None) or "Admin").strip()

    if not email or not password:
        print(
            "Error: ADMIN_EMAIL and ADMIN_PASSWORD must be configured in settings / .env",
            file=sys.stderr,
        )
        sys.exit(1)

    roles_map = user_repo.ensure_roles_seeded(db)
    admin_role = roles_map[RoleName.SYSTEM_ADMIN.value]

    user = user_repo.get_user_by_email(db, email)

    if user is None:
        new_admin = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(new_admin)
        db.commit()
        logger.info("created: admin user %s created successfully with role SYSTEM_ADMIN", email)
        return "created"

    if reset_password:
        user.password_hash = hash_password(password)
        user.role_id = admin_role.id
        user.is_active = True
        if name:
            user.full_name = name
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("password reset: admin user %s password reset successfully", email)
        return "password reset"

    needs_update = False
    if user.role_id != admin_role.id:
        user.role_id = admin_role.id
        needs_update = True
    if not user.is_active:
        user.is_active = True
        needs_update = True

    if needs_update:
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("updated: admin user %s updated to active SYSTEM_ADMIN", email)
        return "updated"

    return "already existed"


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Seed initial roles and SYSTEM_ADMIN user")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset admin password to ADMIN_PASSWORD if user already exists",
    )
    args = parser.parse_args(argv)

    db: Session = SessionLocal()
    try:
        status_msg = seed_admin(db, reset_password=args.reset_password)
        print(f"{status_msg}: admin user {settings.ADMIN_EMAIL.strip().lower()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
