"""
SQLAlchemy Models for Data Quality Engine (Roadmap §V1.3)
Defines metadata storage for 4D quality scores (dq.results), granular row defects (dq.issues),
cleaning transformation audit logs (dq.lineage), entity resolution (dq.entity_map),
and critical failure quarantine (dq.quarantine).
"""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from analytics.extract.models import Base


class DqResult(Base):
    """
    Summary score and rule evaluation outcomes for a dataset.
    Schema: dq.results
    """

    __tablename__ = "results"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "dq"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dataset: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Completeness, Validity, Uniqueness, Consistency
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    column: Mapped[str] = mapped_column(String(100), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    letter_grade: Mapped[str] = mapped_column(
        String(2), nullable=False
    )  # A, B, C, D, F
    severity: Mapped[str] = mapped_column(
        String(20), default="WARNING", nullable=False
    )  # CRITICAL, WARNING, INFO
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DqIssue(Base):
    """
    Row-level defect logging capturing failing row key, rule, observed and suggested values.
    Schema: dq.issues
    """

    __tablename__ = "issues"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "dq"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dataset: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    row_key: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    column: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DqLineage(Base):
    """
    Audit trail recording non-destructive cleaning transformations, cell mutations, and timings.
    Schema: dq.lineage
    """

    __tablename__ = "lineage"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "dq"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    transformation: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    cell_diff_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coerced_null_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DqEntityMap(Base):
    """
    Entity resolution linking historical legacy customer identifiers to master operational ERP customers.
    Schema: dq.entity_map
    """

    __tablename__ = "entity_map"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "dq"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    legacy_customer_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    erp_customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    match_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # tax_id_exact, email_exact, name_fuzzy
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DqQuarantine(Base):
    """
    Quarantine storage holding records that failed CRITICAL data quality checks,
    blocking their promotion into analytical data marts.
    Schema: dq.quarantine
    """

    __tablename__ = "quarantine"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "dq"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dataset: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    row_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # Serialized JSON of row
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
