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


def seed_admin(
    db: Session,
    reset_password: bool = False,
    *,
    must_change_password: bool = True,
) -> str:
    """Idempotently seed the 4 canonical roles and the .env SYSTEM_ADMIN user.

    By default (startup bootstrap, ``reset_password=False``):
    - Seeds ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` ONLY if NO ``SYSTEM_ADMIN``
      user exists anywhere in the database.
    - If any ``SYSTEM_ADMIN`` already exists, does nothing (never resets password,
      role, or status on boot).
    - Sets ``must_change_password=True`` on newly bootstrapped admins and logs a
      startup message without exposing the password.
    """
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

    if not reset_password:
        existing_admin_count = user_repo.count_system_admins(db)
        if existing_admin_count > 0:
            db.commit()
            logger.info(
                "already existed: %d SYSTEM_ADMIN user(s) present in database; skipping bootstrap",
                existing_admin_count,
            )
            return "already existed"

    user = user_repo.get_user_by_email(db, email)

    if user is None:
        new_admin = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role_id=admin_role.id,
            is_active=True,
            must_change_password=must_change_password,
            token_version=0,
        )
        db.add(new_admin)
        db.commit()
        logger.info(
            "created: bootstrap SYSTEM_ADMIN user %s created (must_change_password=%s)",
            email,
            must_change_password,
        )
        return "created"

    if reset_password:
        user.password_hash = hash_password(password)
        user.role_id = admin_role.id
        user.is_active = True
        user.must_change_password = must_change_password
        user.token_version = int(user.token_version or 0) + 1
        if name:
            user.full_name = name
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "password reset: admin user %s password reset (must_change_password=%s)",
            email,
            must_change_password,
        )
        return "password reset"

    # Fallback when email exists with a non-admin role and 0 SYSTEM_ADMINs exist:
    # do not overwrite their password on boot; only promote if explicitly requested via CLI.
    logger.warning(
        "skipped: user %s exists with non-admin role and reset_password=False; run python -m app.create_admin for manual recovery",
        email,
    )
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
