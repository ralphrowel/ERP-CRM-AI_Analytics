"""
Analytics Database Connection and Schema Management (Roadmap §V1.1)
Handles engine creation, schema initialization (raw, staging, dq, mart, etl),
and multi-dialect support (PostgreSQL and SQLite).
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from analytics.config import analytics_settings


def get_erp_engine(url: str | None = None) -> Engine:
    """Creates a SQLAlchemy engine for the source operational ERP database."""
    target_url = url or analytics_settings.ETL_READER_DATABASE_URL
    return create_engine(target_url, pool_pre_ping=True)


def get_analytics_engine(url: str | None = None) -> Engine:
    """Creates a SQLAlchemy engine for the target analytics database."""
    target_url = url or analytics_settings.ANALYTICS_DATABASE_URL
    return create_engine(target_url, pool_pre_ping=True)


def init_analytics_db(engine: Engine) -> None:
    """
    Initializes required analytics schemas and etl tables.
    In PostgreSQL, creates schemas: raw, staging, dq, mart, etl.
    """
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for schema in analytics_settings.SCHEMAS:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
        import analytics.dq.models
        import analytics.mart.models
        from analytics.extract.models import Base

        Base.metadata.create_all(bind=engine)
    else:
        # SQLite schema emulation: map schemas to default
        import analytics.dq.models
        import analytics.mart.models  # noqa: F401
        from analytics.extract.models import Base

        with engine.connect().execution_options(
            schema_translate_map={
                "etl": None,
                "raw": None,
                "staging": None,
                "dq": None,
                "mart": None,
            }
        ) as conn:
            Base.metadata.create_all(bind=conn)
            conn.commit()


def get_analytics_session(engine: Engine) -> Generator[Session, None, None]:
    """Yields a database session bound to the analytics engine."""
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
