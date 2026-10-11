"""
ERP Data Extraction (Roadmap §V1.1)
Connects to the operational ERP database via read-only role (etl_reader)
and appends versioned snapshots to raw.<table_name> in the analytics database.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    select,
)


def get_timestamp_column(table: Table) -> Column | None:
    """Finds the timestamp column used for incremental change detection."""
    for col_name in ["updated_at", "occurred_at", "changed_at", "created_at"]:
        if col_name in table.c:
            return table.c[col_name]
    return None


def get_or_create_raw_table(
    source_table: Table,
    analytics_metadata: MetaData,
    schema: str | None = "raw",
) -> Table:
    """
    Constructs an append-only raw table mirroring source columns plus
    provenance columns (_raw_id, _extracted_at, _run_id, _source).
    Removes primary key and uniqueness constraints from business fields.
    """
    table_key = f"{schema}.{source_table.name}" if schema else source_table.name
    if table_key in analytics_metadata.tables:
        return analytics_metadata.tables[table_key]

    raw_columns = [
        Column("_raw_id", BigInteger, primary_key=True, autoincrement=True),
        Column("_extracted_at", DateTime(timezone=True), nullable=False),
        Column("_run_id", BigInteger, nullable=False),
        Column("_source", String(50), default="erp_crm", nullable=False),
    ]

    for col in source_table.columns:
        # Clone column name and type without primary_key / unique constraints
        raw_columns.append(Column(col.name, col.type, nullable=True))

    target_table = Table(
        source_table.name,
        analytics_metadata,
        *raw_columns,
        schema=schema,
    )
    return target_table


def extract_table(
    table_name: str,
    erp_engine: Engine,
    analytics_engine: Engine,
    run_id: int,
    extracted_at: datetime,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    strictly_greater: bool = False,
    full_refresh: bool = False,
    schema: str | None = "raw",
) -> tuple[int, datetime | None]:
    """
    Extracts rows from an ERP table and appends them to raw.<table_name>.
    Returns (rows_extracted, max_timestamp_observed).
    """
    erp_meta = MetaData()
    source_table = Table(table_name, erp_meta, autoload_with=erp_engine)

    effective_schema = schema if analytics_engine.dialect.name == "postgresql" else None
    analytics_meta = MetaData()
    target_table = get_or_create_raw_table(
        source_table=source_table,
        analytics_metadata=analytics_meta,
        schema=effective_schema,
    )

    analytics_meta.create_all(bind=analytics_engine, tables=[target_table])

    ts_col = get_timestamp_column(source_table)
    query = select(source_table)

    if not full_refresh and ts_col is not None and window_start is not None:
        if strictly_greater:
            query = query.where(ts_col > window_start)
        else:
            query = query.where(ts_col >= window_start)
        if window_end is not None:
            query = query.where(ts_col <= window_end)

    max_ts: datetime | None = None
    rows_to_insert: list[dict[str, Any]] = []

    with erp_engine.connect() as conn:
        result = conn.execute(query)
        col_names = [col.name for col in source_table.columns]

        for row in result:
            row_dict = dict(zip(col_names, row, strict=False))

            # Track max observed timestamp
            if ts_col is not None and row_dict.get(ts_col.name) is not None:
                row_ts = row_dict[ts_col.name]
                if isinstance(row_ts, datetime):
                    if max_ts is None or row_ts > max_ts:
                        max_ts = row_ts

            record = {
                "_extracted_at": extracted_at,
                "_run_id": run_id,
                "_source": "erp_crm",
                **row_dict,
            }
            rows_to_insert.append(record)

    if rows_to_insert:
        with analytics_engine.begin() as a_conn:
            a_conn.execute(target_table.insert(), rows_to_insert)

    return len(rows_to_insert), max_ts
