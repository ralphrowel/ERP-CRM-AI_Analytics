"""
Analytics Transformation Runner (Roadmap §V1.2)
Orchestrates SQL model execution in topological dependency order,
enforces failure cascading, captures data freshness and deterministic checksums,
and records execution state in etl.runs and etl.model_runs.
"""

import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from analytics.db import get_analytics_engine, init_analytics_db
from analytics.extract.models import EtlModelRun, EtlRun
from analytics.transform.checksum import compute_table_checksum
from analytics.transform.dag import ModelDAG, SqlModel


def get_analytics_session(engine: Engine) -> Session:
    """Creates a session configured for PostgreSQL schemas or SQLite translation."""
    if engine.dialect.name == "sqlite":
        exec_engine = engine.execution_options(
            schema_translate_map={"etl": None, "raw": None, "staging": None}
        )
    else:
        exec_engine = engine
    session_cls = sessionmaker(
        bind=exec_engine, autoflush=False, autocommit=False, info={"skip_audit": True}
    )
    session = session_cls()
    session.info["skip_audit"] = True
    return session


class TransformRunner:
    """
    Executes staging transformation models according to the dependency DAG.
    """

    def __init__(
        self,
        engine: Engine | None = None,
        models_dir: Path | None = None,
    ):
        self._engine = engine
        self.dag = ModelDAG(models_dir=models_dir)

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_analytics_engine()
        return self._engine

    def _render_sql(self, model: SqlModel) -> tuple[str, str, str | None]:
        """
        Renders model SQL for PostgreSQL or SQLite target dialect.
        Returns (rendered_sql, target_table_full_name, schema_name).
        """
        sql = model.sql_content.strip()
        # Remove trailing semicolon if present
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()

        is_postgres = self.engine.dialect.name == "postgresql"

        if is_postgres:
            rendered = sql.replace("{{ raw }}", "raw").replace(
                "{{ staging }}", "staging"
            )
            schema = "staging"
            target_full_name = f"staging.{model.target_table}"
        else:
            # On SQLite, strip schema prefixes
            rendered = (
                sql.replace("{{ raw }}.", "")
                .replace("{{ raw }}", "")
                .replace("{{ staging }}.", "")
                .replace("{{ staging }}", "")
            )
            schema = None
            target_full_name = model.target_table

        return rendered, target_full_name, schema

    def _get_data_freshness(self, target_full_name: str) -> datetime | None:
        """Queries MAX(_extracted_at) from the target table to track source freshness."""
        try:
            with self.engine.connect() as conn:
                res = conn.execute(
                    text(f"SELECT MAX(_extracted_at) FROM {target_full_name}")
                ).scalar_one_or_none()
                if isinstance(res, str):
                    return datetime.fromisoformat(res)
                return res
        except Exception:  # noqa: BLE001
            return None

    def run(
        self,
        models: list[str] | None = None,
        job_name: str = "transform",
        clock_now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Executes models in topological order.
        Handles failure cascading: any failure halts downstream dependents.
        """
        now = clock_now or datetime.now(UTC)
        init_analytics_db(self.engine)
        session = get_analytics_session(self.engine)

        # 1. Start ETL run record
        run_record = EtlRun(
            job=job_name,
            started_at=now,
            status="running",
            rows_extracted=0,
        )
        session.add(run_record)
        session.commit()
        session.refresh(run_record)
        run_id = run_record.run_id

        execution_order = self.dag.get_execution_order(target_models=models)
        failed_models: set[str] = set()
        skipped_models: dict[str, str] = {}  # model_name -> reason
        model_results: list[dict[str, Any]] = []
        total_rows = 0

        try:
            for model in execution_order:
                # Check failure cascading
                if model.name in skipped_models:
                    skip_reason = skipped_models[model.name]
                    model_run = EtlModelRun(
                        run_id=run_id,
                        model_name=model.name,
                        target_table=model.target_table,
                        status="skipped",
                        rows_affected=0,
                        started_at=datetime.now(UTC),
                        finished_at=datetime.now(UTC),
                        duration_ms=0,
                        error=skip_reason,
                    )
                    session.add(model_run)
                    session.commit()
                    model_results.append(
                        {
                            "model": model.name,
                            "status": "skipped",
                            "error": skip_reason,
                            "rows": 0,
                        }
                    )
                    continue

                # Execute model
                m_start = datetime.now(UTC)
                start_perf = time.perf_counter()
                rendered_sql, target_full_name, schema = self._render_sql(model)

                try:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"DROP TABLE IF EXISTS {target_full_name};"))
                        conn.execute(
                            text(f"CREATE TABLE {target_full_name} AS {rendered_sql};")
                        )

                    m_end = datetime.now(UTC)
                    duration_ms = int((time.perf_counter() - start_perf) * 1000)

                    # Row count
                    with self.engine.connect() as conn:
                        count_res = conn.execute(
                            text(f"SELECT COUNT(*) FROM {target_full_name}")
                        ).scalar_one()
                        rows_affected = int(count_res)

                    total_rows += rows_affected
                    freshness = self._get_data_freshness(target_full_name)
                    checksum = compute_table_checksum(
                        table_name=model.target_table,
                        engine=self.engine,
                        schema=schema,
                    )

                    model_run = EtlModelRun(
                        run_id=run_id,
                        model_name=model.name,
                        target_table=model.target_table,
                        status="success",
                        rows_affected=rows_affected,
                        started_at=m_start,
                        finished_at=m_end,
                        duration_ms=duration_ms,
                        data_freshness=freshness,
                        checksum=checksum,
                    )
                    session.add(model_run)
                    session.commit()

                    model_results.append(
                        {
                            "model": model.name,
                            "status": "success",
                            "rows": rows_affected,
                            "duration_ms": duration_ms,
                            "freshness": freshness,
                            "checksum": checksum,
                        }
                    )

                except Exception as err:  # noqa: BLE001
                    m_end = datetime.now(UTC)
                    duration_ms = int((time.perf_counter() - start_perf) * 1000)
                    err_msg = f"{type(err).__name__}: {err!s}"

                    model_run = EtlModelRun(
                        run_id=run_id,
                        model_name=model.name,
                        target_table=model.target_table,
                        status="failed",
                        rows_affected=0,
                        started_at=m_start,
                        finished_at=m_end,
                        duration_ms=duration_ms,
                        error=err_msg,
                    )
                    session.add(model_run)
                    session.commit()

                    failed_models.add(model.name)
                    # Cascade skip to all downstream models
                    downstream = self.dag.get_downstream_dependents(model.name)
                    for ds_model in downstream:
                        skipped_models[ds_model] = (
                            f"Prerequisite model '{model.name}' failed"
                        )

                    model_results.append(
                        {
                            "model": model.name,
                            "status": "failed",
                            "error": err_msg,
                            "rows": 0,
                        }
                    )

            # Finalize run status
            run_status = "failed" if failed_models else "success"
            run_record.status = run_status
            run_record.finished_at = datetime.now(UTC)
            run_record.rows_extracted = total_rows
            if failed_models:
                run_record.error = f"Models failed: {', '.join(sorted(failed_models))}"
            session.commit()

            return {
                "run_id": run_id,
                "status": run_status,
                "rows_affected": total_rows,
                "models": model_results,
            }

        except Exception:
            run_record.status = "failed"
            run_record.finished_at = datetime.now(UTC)
            run_record.error = traceback.format_exc()
            session.commit()
            raise
        finally:
            session.close()
