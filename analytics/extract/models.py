"""
SQLAlchemy Models for ETL Metadata & State Management (Roadmap §V1.1)
Tracks extraction run summaries (etl.runs) and high-watermarks (etl.watermarks).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EtlRun(Base):
    """
    Tracks state, metrics, and error outcomes for each extraction job.
    Schema: etl.runs
    """

    __tablename__ = "runs"
    __table_args__ = {"schema": "etl"}

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    rows_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EtlWatermark(Base):
    """
    Stores high-watermark timestamps for incremental source tables.
    Schema: etl.watermarks
    """

    __tablename__ = "watermarks"
    __table_args__ = {"schema": "etl"}

    source_table: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
