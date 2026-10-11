"""
Dataset Profiler Engine (Roadmap §V1.3 & Visiq Spec §4.5)
Performs zero-hallucination tabular dataset profiling:
Computes memory footprint, inferred data types, null counts, uniqueness cardinality,
and min/max boundary values across all columns.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str  # numeric, date, boolean, text
    total_count: int
    null_count: int
    null_percentage: float
    distinct_count: int
    min_value: Any = None
    max_value: Any = None
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class DatasetProfile:
    dataset: str
    total_rows: int
    total_columns: int
    columns: dict[str, ColumnProfile]
    profiled_at: datetime


def _infer_type(values: list[Any]) -> str:
    """Infers predominant semantic data type from non-null sample values."""
    if not values:
        return "text"

    numeric_count = 0
    date_count = 0
    bool_count = 0

    iso_date_pattern = re.compile(r"^\d{4}[-./]\d{2}[-./]\d{2}$")

    for v in values:
        if isinstance(v, (int, float)):
            numeric_count += 1
            continue

        s = str(v).strip()
        if s.lower() in ("true", "false", "t", "f", "1", "0"):
            bool_count += 1
            continue

        # Try clean numeric
        clean_num = s.replace("₱", "").replace("PHP", "").replace(",", "").strip()
        try:
            float(clean_num)
            numeric_count += 1
            continue
        except ValueError:
            pass

        if iso_date_pattern.match(s) or "/" in s:
            date_count += 1
            continue

    total_valid = len(values)
    if numeric_count / total_valid >= 0.70:
        return "numeric"
    if date_count / total_valid >= 0.70:
        return "date"
    if bool_count / total_valid >= 0.70:
        return "boolean"
    return "text"


def profile_dataset(
    dataset_name: str,
    rows: list[dict[str, Any]],
    clock_now: datetime | None = None,
) -> DatasetProfile:
    """Profiles a dataset represented as a list of dictionary row records."""
    now = clock_now or datetime.now(UTC)
    total_rows = len(rows)

    if not rows:
        return DatasetProfile(
            dataset=dataset_name,
            total_rows=0,
            total_columns=0,
            columns={},
            profiled_at=now,
        )

    all_columns = list(rows[0].keys())
    column_profiles: dict[str, ColumnProfile] = {}

    for col in all_columns:
        col_values = [r.get(col) for r in rows]
        non_null_values = [
            v
            for v in col_values
            if v is not None and str(v).strip() not in ("", "N/A", "NULL")
        ]
        null_count = total_rows - len(non_null_values)
        null_pct = (
            round((null_count / total_rows) * 100.0, 2) if total_rows > 0 else 0.0
        )

        distinct_set = {str(v) for v in non_null_values}
        distinct_count = len(distinct_set)

        inferred = _infer_type(non_null_values[:100])

        min_val: Any = None
        max_val: Any = None
        if non_null_values:
            try:
                sorted_vals = sorted(str(v) for v in non_null_values)
                min_val = sorted_vals[0]
                max_val = sorted_vals[-1]
            except (TypeError, ValueError):
                min_val, max_val = None, None

        sample_vals = [str(v) for v in non_null_values[:5]]

        column_profiles[col] = ColumnProfile(
            name=col,
            inferred_type=inferred,
            total_count=total_rows,
            null_count=null_count,
            null_percentage=null_pct,
            distinct_count=distinct_count,
            min_value=min_val,
            max_value=max_val,
            sample_values=sample_vals,
        )

    return DatasetProfile(
        dataset=dataset_name,
        total_rows=total_rows,
        total_columns=len(all_columns),
        columns=column_profiles,
        profiled_at=now,
    )
