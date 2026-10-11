"""
Table Checksum Utility (Roadmap §V1.2)
Computes deterministic SHA-256 checksums of transformed staging tables
to prove transformation pipeline idempotency.
"""

import hashlib

from sqlalchemy import Engine, inspect, text


def compute_table_checksum(
    table_name: str,
    engine: Engine,
    schema: str | None = None,
) -> str:
    """
    Computes a deterministic SHA-256 checksum over the sorted rows of a table.
    Sorts by all columns (or primary key) to guarantee reproducibility.
    """
    effective_schema = schema if engine.dialect.name == "postgresql" else None
    inspector = inspect(engine)
    columns = [
        col["name"]
        for col in inspector.get_columns(table_name, schema=effective_schema)
    ]
    if not columns:
        return hashlib.sha256(b"empty").hexdigest()

    qualified_name = (
        f"{effective_schema}.{table_name}" if effective_schema else table_name
    )
    order_by_clause = ", ".join(f'"{col}"' for col in columns)

    query = text(f"SELECT * FROM {qualified_name} ORDER BY {order_by_clause}")

    hasher = hashlib.sha256()
    with engine.connect() as conn:
        result = conn.execute(query)
        for row in result:
            row_str = "|".join(str(val) if val is not None else "NULL" for val in row)
            hasher.update(row_str.encode("utf-8"))

    return hasher.hexdigest()
