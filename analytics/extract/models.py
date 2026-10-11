"""
SQLAlchemy Models for ETL Metadata & State Management (Roadmap §V1.1)
Tracks extraction run summaries (etl.runs) and high-watermarks (etl.watermarks).
"""

from datetime import datetime
from typing import Any, ClassVar

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
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "etl"}

    run_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    job: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    rows_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EtlWatermark(Base):
    """
    Stores high-watermark timestamps for incremental source tables.
    Schema: etl.watermarks
    """

    __tablename__ = "watermarks"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "etl"}

    source_table: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EtlModelRun(Base):
    """
    Tracks execution metrics, row counts, duration, and checksums for individual SQL models.
    Schema: etl.model_runs
    """

    __tablename__ = "model_runs"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "etl"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, failed, skipped
    rows_affected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_freshness: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
