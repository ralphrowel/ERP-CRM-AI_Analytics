import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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

CLEANUP_DATABASE_URL = (
    os.getenv("TEST_CLEANUP_DATABASE_URL")
    or os.getenv("MIGRATION_DATABASE_URL")
    or getattr(settings, "MIGRATION_DATABASE_URL", None)
    or DATABASE_URL
)

_use_sqlite = False
_cleanup_engine = None
try:
    _temp_engine = create_engine(
        DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 2}
    )
    with _temp_engine.connect() as _conn:
        pass
    if CLEANUP_DATABASE_URL:
        _cleanup_engine = create_engine(
            CLEANUP_DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 2}
        )
except Exception:
    _use_sqlite = True


def _clean_tables(app_engine) -> None:
    eng = _cleanup_engine or app_engine
    with eng.connect() as conn:
        if eng.dialect.name == "postgresql":
            try:
                table_names = [f'"{table.name}"' for table in Base.metadata.sorted_tables]
                if table_names:
                    conn.execute(
                        text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE")
                    )
                    conn.commit()
                    return
            except Exception:
                pass
        # Break cyclic foreign keys between leads and opportunities before delete
        try:
            with conn.begin_nested():
                conn.execute(
                    text(
                        "UPDATE leads SET converted_opportunity_id = NULL, converted_customer_id = NULL, converted_contact_id = NULL"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE opportunities SET source_lead_id = NULL, primary_contact_id = NULL"
                    )
                )
        except Exception:
            pass
        for table in reversed(Base.metadata.sorted_tables):
            try:
                with conn.begin_nested():
                    conn.execute(table.delete())
            except Exception:
                pass
        conn.commit()


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
        DocumentSequence(
            doc_type="shipment", prefix="SHP", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="stock_adjustment", prefix="ADJ", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="stock_transfer", prefix="TRF", include_year=True, padding=6, next_value=1
        ),
    ]
    for s in defaults:
        if s.doc_type not in existing:
            session.add(s)
    session.flush()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    from app.modules.audit.context import clear_audit_context

    clear_audit_context()
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
            clear_audit_context()
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
            clear_audit_context()
            session.close()
            _clean_tables(engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
