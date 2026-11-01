"""SQLAlchemy declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models.

    All models inherit from this so that ``Base.metadata`` contains
    every table — required for Alembic autogenerate discovery.
    """

    pass

