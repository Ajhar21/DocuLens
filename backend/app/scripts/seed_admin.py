from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def seed_admin(db: Session) -> User:
    email = settings.ADMIN_EMAIL.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        logger.info("Admin user already exists: %s (id=%s)", email, existing.id)
        return existing

    admin = User(
        email=email,
        full_name="System Administrator",
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Created admin user: %s (id=%s)", email, admin.id)
    return admin


def main() -> None:
    db = SessionLocal()
    try:
        seed_admin(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
