from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import re
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
import app.models  # noqa: F401
from app.main import app
from app.repositories.user_repo import ensure_roles_seeded

FORBIDDEN_SCHEMAS = {
    "public",
    "extensions",
    "auth",
    "storage",
    "pg_catalog",
    "information_schema",
}


def validate_test_schema(schema_name: str) -> str:
    cleaned = (schema_name or "").strip()
    if not cleaned:
        raise RuntimeError("Refusing to run tests: TEST_SCHEMA is empty")
    if cleaned.lower() in FORBIDDEN_SCHEMAS:
        raise RuntimeError(
            f"Refusing to run tests against protected schema '{cleaned}'"
        )
    if "test" not in cleaned.lower():
        raise RuntimeError(
            f"Refusing to run tests: TEST_SCHEMA '{cleaned}' must contain 'test'"
        )
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cleaned):
        raise RuntimeError(
            f"Refusing to run tests: TEST_SCHEMA '{cleaned}' is not a valid SQL identifier"
        )
    return cleaned


TEST_SCHEMA = validate_test_schema(settings.TEST_SCHEMA)

test_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


@event.listens_for(test_engine, "connect")
def _set_search_path(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute(f'SET search_path TO "{TEST_SCHEMA}", extensions')
        dbapi_connection.commit()  # type: ignore[attr-defined]
    finally:
        cursor.close()


TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_schema() -> Generator[None, None, None]:
    with test_engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{TEST_SCHEMA}"'))

    Base.metadata.create_all(bind=test_engine)

    with TestingSessionLocal() as session:
        ensure_roles_seeded(session)
        session.commit()

    with test_engine.connect() as conn:
        current = conn.execute(select(func.current_schema())).scalar_one()
        assert current == TEST_SCHEMA, (
            f"Expected current_schema() == '{TEST_SCHEMA}', got '{current}'"
        )

    yield

    # Preserve schema and data after tests so developer can inspect DB state in Postgres/Supabase
    test_engine.dispose()


@pytest.fixture(autouse=True)
def truncate_tables(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    # Only truncate DB tables when the test actually uses a DB fixture.
    db_fixtures = {"db", "client", "test_sessionmaker"}
    if not (db_fixtures & set(request.fixturenames)):
        yield
        return

    # Truncate tables before the test starts so the test runs in isolation,
    # but do NOT truncate afterwards so the final DB state remains inspectable.
    # Exclude shared tables (users, roles) from unscoped truncate to preserve seeded data.
    table_names = [
        f'"{table.name}"'
        for table in reversed(Base.metadata.sorted_tables)
        if table.name not in ("users", "roles")
    ]
    if table_names:
        with test_engine.begin() as conn:
            conn.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"
                )
            )
    yield


@pytest.fixture()
def test_sessionmaker() -> sessionmaker[Session]:
    return TestingSessionLocal


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "STORAGE_DIR", str(storage_dir))

    def _override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
