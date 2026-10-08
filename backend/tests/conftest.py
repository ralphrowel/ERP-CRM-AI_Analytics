import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import BigInteger

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app


@compiles(BigInteger, "sqlite")
def compile_big_int_sqlite(type_, compiler, **kw):
    return "INTEGER"


# Check if PostgreSQL is available via DATABASE_URL
DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or settings.DATABASE_URL

# For tests, we use the configured database or fallback
test_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def setup_test_db():
    """Initializes tables for test suite if connecting to accessible test database."""
    try:
        Base.metadata.create_all(bind=test_engine)
        yield
    except Exception:
        # If DB server isn't running locally yet, yield gracefully so unit tests can still run
        yield


@pytest.fixture
def db_session(setup_test_db) -> Generator[Session, None, None]:
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
