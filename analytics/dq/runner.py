"""
Data Quality Pipeline Runner & Circuit Breaker (Roadmap §V1.3 & Visiq Spec §4.5)
Orchestrates the Visiq Data Quality engine as a pipeline stage between staging and mart:
1. Evaluates 4D quality rules (Completeness, Validity, Uniqueness, Consistency).
2. Calculates composite health score (0–100) and letter grades (A–F).
3. Persists dq.results, dq.issues, dq.lineage, dq.entity_map, and dq.quarantine.
4. Produces non-destructive staging.clean_* derived tables with formula injection sanitization.
5. Enforces critical failure circuit breaker blocking analytical mart promotion.
"""

import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text

from analytics.config import analytics_settings
from analytics.db import init_analytics_db
from analytics.dq.cleaner import clean_customer_row, clean_sales_row, preview_cleaning
from analytics.dq.resolution import persist_entity_matches, resolve_entities
from analytics.dq.rules import (
    RuleIssue,
    get_default_customer_rules,
    get_default_sales_rules,
)
from analytics.dq.scoring import QualityScorecard, calculate_quality_scorecard


class CircuitBreakerError(Exception):
    """Raised when critical data quality defects trip the circuit breaker and block mart load."""


class DqRunner:
    """Executes the data quality evaluation, entity resolution, and cleaning pipeline."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.is_postgres = engine.dialect.name == "postgresql"
        init_analytics_db(self.engine)

    def _get_target_table(self, schema: str, table_name: str) -> str:
        """Returns qualified table name based on engine dialect."""
        if self.is_postgres:
            return f"{schema}.{table_name}"
        return table_name

    def _fetch_rows(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Executes query and returns list of dictionaries."""
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return [dict(row._mapping) for row in result]

    def _persist_results_and_issues(
        self,
        run_id: int,
        dataset: str,
        scorecard: QualityScorecard,
        issues: list[RuleIssue],
        clock_now: datetime,
    ) -> None:
        """Persists rule summaries into dq.results and granular defects into dq.issues."""
        results_tbl = self._get_target_table("dq", "results")
        issues_tbl = self._get_target_table("dq", "issues")

        with self.engine.begin() as conn:
            # 1. dq.results
            for r in scorecard.rule_results:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {results_tbl} (
                            run_id, dataset, dimension, rule, "column", total_rows, failed_rows,
                            score, letter_grade, severity, created_at
                        ) VALUES (
                            :run_id, :dataset, :dim, :rule, :col, :tot, :fail,
                            :score, :grade, :sev, :created_at
                        )
                        """
                    ),
                    {
                        "run_id": run_id,
                        "dataset": dataset,
                        "dim": r.dimension,
                        "rule": r.rule_name,
                        "col": r.column,
                        "tot": r.total_rows,
                        "fail": r.failed_rows,
                        "score": r.pass_rate,
                        "grade": scorecard.letter_grade,
                        "sev": r.severity,
                        "created_at": clock_now,
                    },
                )

            # 2. dq.issues
            for issue in issues:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {issues_tbl} (
                            run_id, dataset, row_key, dimension, rule, "column",
                            observed_value, suggested_value, severity, created_at
                        ) VALUES (
                            :run_id, :dataset, :row_key, :dim, :rule, :col,
                            :obs, :sug, :sev, :created_at
                        )
                        """
                    ),
                    {
                        "run_id": run_id,
                        "dataset": dataset,
                        "row_key": issue.row_key,
                        "dim": issue.dimension,
                        "rule": issue.rule_name,
                        "col": issue.column,
                        "obs": str(issue.observed_value)
                        if issue.observed_value is not None
                        else None,
                        "sug": str(issue.suggested_value)
                        if issue.suggested_value is not None
                        else None,
                        "sev": issue.severity,
                        "created_at": clock_now,
                    },
                )

    def _persist_quarantine(
        self,
        run_id: int,
        dataset: str,
        row_key: str,
        reason: str,
        payload: dict[str, Any],
        clock_now: datetime,
    ) -> None:
        """Persists critical defect records into dq.quarantine table."""
        quar_tbl = self._get_target_table("dq", "quarantine")
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {quar_tbl} (
                        run_id, dataset, row_key, reason, payload, quarantined_at
                    ) VALUES (
                        :run_id, :dataset, :row_key, :reason, :payload, :quarantined_at
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "dataset": dataset,
                    "row_key": row_key,
                    "reason": reason,
                    "payload": json.dumps(payload, default=str),
                    "quarantined_at": clock_now,
                },
            )

    def _persist_lineage(
        self,
        run_id: int,
        source: str,
        transformation: str,
        target: str,
        cell_diffs: int,
        coerced_nulls: int,
        duration_ms: int,
        clock_now: datetime,
    ) -> None:
        """Persists transformation audit record into dq.lineage."""
        lineage_tbl = self._get_target_table("dq", "lineage")
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {lineage_tbl} (
                        run_id, source, transformation, target, cell_diff_count,
                        coerced_null_count, duration_ms, created_at
                    ) VALUES (
                        :run_id, :source, :tx, :target, :diffs,
                        :nulls, :dur, :created_at
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "source": source,
                    "tx": transformation,
                    "target": target,
                    "diffs": cell_diffs,
                    "nulls": coerced_nulls,
                    "dur": duration_ms,
                    "created_at": clock_now,
                },
            )

    def _create_clean_table_and_insert(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """Creates staging.clean_<table_name> and inserts cleaned rows."""
        if not rows:
            return

        clean_tbl = self._get_target_table("staging", f"clean_{table_name}")
        cols = list(rows[0].keys())

        numeric_cols = {
            "parsed_quantity",
            "quantity",
            "unit_price",
            "parsed_unit_price",
            "total_amount",
            "parsed_total_amount",
            "credit_limit",
        }

        # Define column DDL
        col_defs = ", ".join(
            f'"{c}" NUMERIC' if c in numeric_cols else f'"{c}" TEXT' for c in cols
        )
        cascade = " CASCADE" if self.is_postgres else ""

        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {clean_tbl}{cascade};"))
            conn.execute(text(f"CREATE TABLE {clean_tbl} ({col_defs});"))

            # Insert rows
            col_list = ", ".join(f'"{c}"' for c in cols)
            param_list = ", ".join(f":{c}" for c in cols)
            insert_sql = text(
                f"INSERT INTO {clean_tbl} ({col_list}) VALUES ({param_list})"
            )

            for r in rows:
                param_dict = {}
                for c in cols:
                    val = r.get(c)
                    if val is None or val == "":
                        param_dict[c] = None
                    elif c in numeric_cols:
                        try:
                            clean_val = (
                                str(val)
                                .replace("₱", "")
                                .replace("PHP", "")
                                .replace(",", "")
                                .strip()
                            )
                            param_dict[c] = float(clean_val)
                        except (ValueError, TypeError):
                            param_dict[c] = None
                    else:
                        param_dict[c] = str(val)
                conn.execute(insert_sql, param_dict)

    def run(
        self,
        datasets: list[str] | None = None,
        preview: bool = False,
        circuit_breaker: bool = False,
        clock_now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Executes data quality evaluation and cleaning stage.
        Returns dictionary execution summary with run_id, scorecards, and quarantine totals.
        """
        now = clock_now or datetime.now(UTC)

        # 1. Create ETL Run record
        with self.engine.begin() as conn:
            runs_tbl = self._get_target_table("etl", "runs")
            conn.execute(
                text(
                    f"""
                    INSERT INTO {runs_tbl} (
                        job, started_at, status, rows_extracted
                    ) VALUES (
                        'data_quality', :started_at, 'running', 0
                    )
                    """
                ),
                {"started_at": now},
            )
            run_id = (
                conn.execute(text(f"SELECT MAX(run_id) FROM {runs_tbl}")).scalar() or 1
            )

        summary: dict[str, Any] = {
            "run_id": run_id,
            "status": "success",
            "scorecards": {},
            "quarantined_total": 0,
            "previews": {},
        }

        target_datasets = datasets or ["legacy_customers", "legacy_sales"]
        total_critical_defects = 0

        try:
            # 2. Evaluate and clean legacy_customers
            if "legacy_customers" in target_datasets:
                source_tbl = self._get_target_table("staging", "stg_legacy_customers")
                try:
                    cust_rows = self._fetch_rows(f"SELECT * FROM {source_tbl}")
                except Exception:  # noqa: BLE001
                    try:
                        raw_tbl = self._get_target_table("raw", "legacy_customers")
                        cust_rows = self._fetch_rows(f"SELECT * FROM {raw_tbl}")
                    except Exception:  # noqa: BLE001
                        import csv

                        csv_p = analytics_settings.legacy_customers_csv_path
                        if csv_p.exists():
                            with open(csv_p, encoding="utf-8-sig") as f:
                                cust_rows = list(csv.DictReader(f))
                        else:
                            cust_rows = []

                cust_rules = get_default_customer_rules()

                if preview:
                    prev = preview_cleaning(
                        "legacy_customers", cust_rows, cust_rules, "legacy_customer_id"
                    )
                    summary["previews"]["legacy_customers"] = prev
                else:
                    t0 = time.time()
                    rule_results = []
                    all_cust_issues: list[RuleIssue] = []
                    for rule in cust_rules:
                        r_res, r_issues = rule.evaluate(cust_rows, "legacy_customer_id")
                        rule_results.append(r_res)
                        all_cust_issues.extend(r_issues)

                    cust_scorecard = calculate_quality_scorecard(
                        "legacy_customers", rule_results
                    )
                    summary["scorecards"]["legacy_customers"] = cust_scorecard
                    total_critical_defects += cust_scorecard.critical_failures

                    self._persist_results_and_issues(
                        run_id=run_id,
                        dataset="legacy_customers",
                        scorecard=cust_scorecard,
                        issues=all_cust_issues,
                        clock_now=now,
                    )

                    # Clean customers
                    clean_cust_rows = []
                    cust_diffs = []
                    cust_coerced_nulls = 0
                    for r in cust_rows:
                        cl_r, diffs, coerced = clean_customer_row(
                            r, "legacy_customer_id"
                        )
                        clean_cust_rows.append(cl_r)
                        cust_diffs.extend(diffs)
                        cust_coerced_nulls += coerced

                    self._create_clean_table_and_insert(
                        "legacy_customers", clean_cust_rows
                    )
                    dur_ms = int((time.time() - t0) * 1000)
                    self._persist_lineage(
                        run_id=run_id,
                        source="stg_legacy_customers",
                        transformation="standardize_casing_phone_currency_formula_sanitization",
                        target="staging.clean_legacy_customers",
                        cell_diffs=len(cust_diffs),
                        coerced_nulls=cust_coerced_nulls,
                        duration_ms=dur_ms,
                        clock_now=now,
                    )

                    # Entity Resolution: legacy customers to ERP customers
                    try:
                        erp_tbl = self._get_target_table("staging", "stg_customers")
                        erp_cust_rows = self._fetch_rows(f"SELECT * FROM {erp_tbl}")
                    except Exception:  # noqa: BLE001
                        try:
                            erp_raw_tbl = self._get_target_table("raw", "customers")
                            erp_cust_rows = self._fetch_rows(
                                f"SELECT * FROM {erp_raw_tbl}"
                            )
                        except Exception:  # noqa: BLE001
                            erp_cust_rows = []

                    matches = resolve_entities(clean_cust_rows, erp_cust_rows)
                    matched_count = persist_entity_matches(
                        matches, self.engine, run_id, now
                    )
                    summary["entity_matches"] = matched_count

            # 3. Evaluate and clean legacy_sales
            if "legacy_sales" in target_datasets:
                source_tbl = self._get_target_table("staging", "stg_legacy_sales")
                try:
                    sales_rows = self._fetch_rows(f"SELECT * FROM {source_tbl}")
                except Exception:  # noqa: BLE001
                    try:
                        raw_tbl = self._get_target_table("raw", "legacy_sales")
                        sales_rows = self._fetch_rows(f"SELECT * FROM {raw_tbl}")
                    except Exception:  # noqa: BLE001
                        import csv

                        csv_p = analytics_settings.legacy_sales_csv_path
                        if csv_p.exists():
                            with open(csv_p, encoding="utf-8-sig") as f:
                                sales_rows = list(csv.DictReader(f))
                        else:
                            sales_rows = []

                sales_rules = get_default_sales_rules()

                if preview:
                    prev = preview_cleaning(
                        "legacy_sales", sales_rows, sales_rules, "invoice_no"
                    )
                    summary["previews"]["legacy_sales"] = prev
                else:
                    t0 = time.time()
                    rule_results = []
                    all_sales_issues: list[RuleIssue] = []
                    for rule in sales_rules:
                        r_res, r_issues = rule.evaluate(sales_rows, "invoice_no")
                        rule_results.append(r_res)
                        all_sales_issues.extend(r_issues)

                    sales_scorecard = calculate_quality_scorecard(
                        "legacy_sales", rule_results
                    )
                    summary["scorecards"]["legacy_sales"] = sales_scorecard
                    total_critical_defects += sales_scorecard.critical_failures

                    self._persist_results_and_issues(
                        run_id=run_id,
                        dataset="legacy_sales",
                        scorecard=sales_scorecard,
                        issues=all_sales_issues,
                        clock_now=now,
                    )

                    # Clean sales & Quarantine critical failures
                    clean_sales_rows = []
                    sales_diffs = []
                    sales_coerced_nulls = 0
                    quarantined_sales_count = 0

                    for r in sales_rows:
                        cl_r, diffs, coerced, is_quar, quar_reason = clean_sales_row(
                            r, "invoice_no"
                        )
                        if is_quar:
                            quarantined_sales_count += 1
                            key = str(r.get("invoice_no") or r.get("_row_number", ""))
                            self._persist_quarantine(
                                run_id=run_id,
                                dataset="legacy_sales",
                                row_key=key,
                                reason=quar_reason,
                                payload=r,
                                clock_now=now,
                            )
                        else:
                            clean_sales_rows.append(cl_r)
                            sales_diffs.extend(diffs)
                            sales_coerced_nulls += coerced

                    summary["quarantined_total"] += quarantined_sales_count
                    self._create_clean_table_and_insert(
                        "legacy_sales", clean_sales_rows
                    )
                    dur_ms = int((time.time() - t0) * 1000)
                    self._persist_lineage(
                        run_id=run_id,
                        source="stg_legacy_sales",
                        transformation="quarantine_critical_normalize_dates_currencies",
                        target="staging.clean_legacy_sales",
                        cell_diffs=len(sales_diffs),
                        coerced_nulls=sales_coerced_nulls,
                        duration_ms=dur_ms,
                        clock_now=now,
                    )

            # 4. Check Circuit Breaker
            if circuit_breaker and total_critical_defects > 0:
                with self.engine.begin() as conn:
                    runs_tbl = self._get_target_table("etl", "runs")
                    conn.execute(
                        text(
                            f"""
                            UPDATE {runs_tbl}
                            SET status = 'BLOCKED', finished_at = :now
                            WHERE run_id = :run_id
                            """
                        ),
                        {"now": datetime.now(UTC), "run_id": run_id},
                    )
                summary["status"] = "BLOCKED"
                raise CircuitBreakerError(
                    f"Mart load blocked: {total_critical_defects} critical DQ failures detected."
                )

            # 5. Complete ETL Run
            with self.engine.begin() as conn:
                runs_tbl = self._get_target_table("etl", "runs")
                conn.execute(
                    text(
                        f"""
                        UPDATE {runs_tbl}
                        SET status = 'success', finished_at = :now
                        WHERE run_id = :run_id
                        """
                    ),
                    {"now": datetime.now(UTC), "run_id": run_id},
                )

        except CircuitBreakerError:
            raise
        except Exception as e:
            with self.engine.begin() as conn:
                runs_tbl = self._get_target_table("etl", "runs")
                conn.execute(
                    text(
                        f"""
                        UPDATE {runs_tbl}
                        SET status = 'failed', finished_at = :now, error = :err
                        WHERE run_id = :run_id
                        """
                    ),
                    {"now": datetime.now(UTC), "run_id": run_id, "err": str(e)},
                )
            summary["status"] = "failed"
            summary["error"] = str(e)
            raise

        return summary
