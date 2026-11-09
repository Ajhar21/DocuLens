"""CLI utility to create or recover a SYSTEM_ADMIN user (`python -m app.create_admin`).

Accepts `--email`, `--password`, `--full-name`, and `--no-must-change-password`
via CLI arguments, or interactively prompts when omitted. Never logs passwords.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import logging
import sys
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import RoleName, User
from app.repositories import user_repo
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def create_or_recover_admin(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str = "System Administrator",
    must_change_password: bool = True,
) -> tuple[User, str]:
    cleaned_email = (email or "").strip().lower()
    cleaned_password = (password or "").strip()
    cleaned_name = (full_name or "System Administrator").strip()

    if not cleaned_email or "@" not in cleaned_email:
        raise ValueError("A valid email address is required")
    if len(cleaned_password) < 12:
        raise ValueError("Password must be at least 12 characters long")

    roles_map = user_repo.ensure_roles_seeded(db)
    admin_role = roles_map[RoleName.SYSTEM_ADMIN.value]

    user = user_repo.get_user_by_email(db, cleaned_email)
    now = datetime.now(timezone.utc)

    if user is None:
        user = User(
            email=cleaned_email,
            full_name=cleaned_name,
            password_hash=hash_password(cleaned_password),
            role_id=admin_role.id,
            is_active=True,
            must_change_password=must_change_password,
            token_version=0,
        )
        db.add(user)
        db.flush()
        AuditService.record(
            db,
            user_id=user.id,
            action="USER_CREATED",
            entity_type="USER",
            entity_id=user.id,
            old_values=None,
            new_values={
                "email": user.email,
                "role": RoleName.SYSTEM_ADMIN.value,
                "must_change_password": must_change_password,
                "source": "cli_create_admin",
            },
        )
        db.commit()
        db.refresh(user)
        logger.info("CLI created SYSTEM_ADMIN user %s", cleaned_email)
        return user, "created"

    old_role = user.role_name
    old_active = user.is_active
    user.password_hash = hash_password(cleaned_password)
    user.role_id = admin_role.id
    user.is_active = True
    user.deactivated_at = None
    user.must_change_password = must_change_password
    user.token_version = int(user.token_version or 0) + 1
    if cleaned_name:
        user.full_name = cleaned_name
    user.updated_at = now
    user_repo.revoke_user_refresh_tokens(db, user.id, now)

    AuditService.record(
        db,
        user_id=user.id,
        action="password.changed",
        entity_type="USER",
        entity_id=user.id,
        old_values={"role": old_role, "is_active": old_active},
        new_values={
            "role": RoleName.SYSTEM_ADMIN.value,
            "is_active": True,
            "must_change_password": must_change_password,
            "source": "cli_create_admin",
        },
    )
    db.commit()
    db.refresh(user)
    logger.info("CLI recovered/updated SYSTEM_ADMIN user %s", cleaned_email)
    return user, "recovered"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or recover a SYSTEM_ADMIN user in DocuLens."
    )
    parser.add_argument("--email", type=str, help="Admin email address")
    parser.add_argument("--password", type=str, help="Admin password (min 12 chars)")
    parser.add_argument(
        "--full-name",
        type=str,
        default="System Administrator",
        help="Full name for the admin user",
    )
    parser.add_argument(
        "--no-must-change-password",
        action="store_true",
        help="Do not require password change on next login",
    )
    args = parser.parse_args(argv)

    email = args.email
    if not email:
        email = input("Admin email: ").strip()

    password = args.password
    if not password:
        password = getpass.getpass("Admin password (min 12 chars): ").strip()

    db: Session = SessionLocal()
    try:
        user, action = create_or_recover_admin(
            db,
            email=email,
            password=password,
            full_name=args.full_name,
            must_change_password=not args.no_must_change_password,
        )
        print(
            f"{action}: SYSTEM_ADMIN user {user.email} "
            f"(id={user.id}, must_change_password={user.must_change_password})"
        )
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

