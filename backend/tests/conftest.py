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

_use_sqlite = False
try:
    _temp_engine = create_engine(
        DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 2}
    )
    with _temp_engine.connect() as _conn:
        pass
except Exception:
    _use_sqlite = True


def _seed_document_sequences(session: Session) -> None:
    from app.core.numbering import DocumentSequence

    existing = {s.doc_type for s in session.query(DocumentSequence).all()}
    defaults = [
        DocumentSequence(
            doc_type="customer", prefix="CUS", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(doc_type="quote", prefix="QT", include_year=True, padding=6, next_value=1),
        DocumentSequence(
            doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="invoice", prefix="INV", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="payment", prefix="PAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="credit_note", prefix="CN", include_year=True, padding=6, next_value=1
        ),
    ]
    for s in defaults:
        if s.doc_type not in existing:
            session.add(s)
    session.flush()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    if _use_sqlite:
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = session_factory()
        _seed_document_sequences(session)
        session.commit()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
    else:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = session_factory()
        _seed_document_sequences(session)
        session.commit()
        try:
            yield session
        finally:
            session.close()
            with engine.connect() as conn:
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())
                conn.commit()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
