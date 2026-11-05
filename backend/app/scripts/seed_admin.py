from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.seed import seed_admin as _seed_admin, main


def seed_admin(db: Session, reset_password: bool = False) -> None:
    _seed_admin(db, reset_password=reset_password)


if __name__ == "__main__":
    main()
