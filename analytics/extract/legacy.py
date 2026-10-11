"""
Legacy Data Ingestion (Roadmap §V1.1)
Extracts legacy dirty CSV datasets into raw.legacy_* tables (all TEXT columns),
preserving original format, file provenance, and row numbers for downstream parsing.
"""

import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)


def get_raw_legacy_table(
    table_name: str,
    fieldnames: list[str],
    metadata: MetaData,
    schema: str | None = "raw",
) -> Table:
    """
    Constructs or retrieves a dynamic SQLAlchemy Table for raw.legacy_* with
    all payload columns typed as TEXT plus audit metadata columns.
    """
    columns = [
        Column("_raw_id", BigInteger, primary_key=True, autoincrement=True),
        Column("_file_name", String(255), nullable=False),
        Column("_row_number", Integer, nullable=False),
        Column("_extracted_at", DateTime(timezone=True), nullable=False),
        Column("_run_id", BigInteger, nullable=False),
        Column("_source", String(50), default="legacy_csv", nullable=False),
    ]

    for field in fieldnames:
        clean_field = field.strip()
        if clean_field:
            columns.append(Column(clean_field, Text, nullable=True))

    return Table(table_name, metadata, *columns, schema=schema)


def ingest_legacy_csv(
    file_path: Path,
    target_table_name: str,
    engine: Engine,
    run_id: int,
    extracted_at: datetime,
    schema: str | None = "raw",
) -> int:
    """
    Reads a legacy CSV file and appends every record into raw.<target_table_name>
    as raw TEXT data. Returns the total count of inserted rows.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Legacy file not found: {file_path}")

    # Determine schema according to database dialect
    effective_schema = schema if engine.dialect.name == "postgresql" else None
    metadata = MetaData()

    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0

        table = get_raw_legacy_table(
            table_name=target_table_name,
            fieldnames=reader.fieldnames,
            metadata=metadata,
            schema=effective_schema,
        )

        metadata.create_all(bind=engine, tables=[table])

        rows_to_insert: list[dict] = []
        for row_idx, row in enumerate(reader, start=1):
            record = {
                "_file_name": file_path.name,
                "_row_number": row_idx,
                "_extracted_at": extracted_at,
                "_run_id": run_id,
                "_source": "legacy_csv",
            }
            for k, v in row.items():
                if k:
                    record[k.strip()] = v
            rows_to_insert.append(record)

    if rows_to_insert:
        with engine.begin() as conn:
            conn.execute(table.insert(), rows_to_insert)

    return len(rows_to_insert)
