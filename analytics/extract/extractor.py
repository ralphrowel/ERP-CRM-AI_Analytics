"""
Analytics Extraction Orchestrator (Roadmap §V1.1)
Coordinates incremental extraction by updated_at with watermark tracking,
configurable overlap windows, full-extract reference tables, and legacy CSV ingestion.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from analytics.config import analytics_settings
from analytics.db import get_analytics_engine, get_erp_engine, init_analytics_db
from analytics.extract.erp import extract_table
from analytics.extract.legacy import ingest_legacy_csv
from analytics.extract.models import EtlRun, EtlWatermark


def get_session(engine: Engine) -> Session:
    """Creates a session configured for PostgreSQL schemas or SQLite translation."""
    if engine.dialect.name == "sqlite":
        exec_engine = engine.execution_options(schema_translate_map={"etl": None, "raw": None})
    else:
        exec_engine = engine
    session_cls = sessionmaker(
        bind=exec_engine, autoflush=False, autocommit=False, info={"skip_audit": True}
    )
    session = session_cls()
    session.info["skip_audit"] = True
    return session


class Extractor:
    """
    Main extraction engine moving data from operational ERP and legacy files
    into the append-only raw analytics layer.
    """

    def __init__(
        self,
        erp_engine: Engine | None = None,
        analytics_engine: Engine | None = None,
        overlap_minutes: int | None = None,
    ):
        self.erp_engine = erp_engine or get_erp_engine()
        self.analytics_engine = analytics_engine or get_analytics_engine()
        self.overlap_minutes = (
            overlap_minutes
            if overlap_minutes is not None
            else analytics_settings.ETL_OVERLAP_MINUTES
        )

        # Initialize target schemas and metadata tables
        init_analytics_db(self.analytics_engine)

    def run(
        self,
        tables: list[str] | None = None,
        full_refresh: bool = False,
        legacy_only: bool = False,
        erp_only: bool = False,
        job_name: str = "extract",
        clock_now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Executes an extraction run.
        Returns a dictionary summary with run_id, status, rows_extracted, and per-table counts.
        """
        now = clock_now or datetime.now(UTC)
        total_rows = 0
        table_counts: dict[str, int] = {}

        session = get_session(self.analytics_engine)

        # 1. Create Run Record in etl.runs
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

        try:
            # 2. Ingest Legacy CSVs (if not erp_only and not scoped to specific ERP tables)
            if not erp_only and (tables is None or "legacy" in tables):
                if analytics_settings.legacy_customers_csv_path.exists():
                    cust_rows = ingest_legacy_csv(
                        file_path=analytics_settings.legacy_customers_csv_path,
                        target_table_name="legacy_customers",
                        engine=self.analytics_engine,
                        run_id=run_id,
                        extracted_at=now,
                    )
                    table_counts["legacy_customers"] = cust_rows
                    total_rows += cust_rows

                if analytics_settings.legacy_sales_csv_path.exists():
                    sales_rows = ingest_legacy_csv(
                        file_path=analytics_settings.legacy_sales_csv_path,
                        target_table_name="legacy_sales",
                        engine=self.analytics_engine,
                        run_id=run_id,
                        extracted_at=now,
                    )
                    table_counts["legacy_sales"] = sales_rows
                    total_rows += sales_rows

            # 3. Extract ERP Tables (if not legacy_only)
            if not legacy_only:
                erp_inspector = inspect(self.erp_engine)
                existing_erp_tables = set(erp_inspector.get_table_names())

                # Determine target tables to extract
                if tables:
                    target_tables = [t for t in tables if t in existing_erp_tables]
                else:
                    target_tables = [
                        t
                        for t in (
                            analytics_settings.REFERENCE_TABLES
                            + analytics_settings.INCREMENTAL_TABLES
                        )
                        if t in existing_erp_tables
                    ]

                for tbl in target_tables:
                    is_reference = tbl in analytics_settings.REFERENCE_TABLES
                    watermark = session.execute(
                        select(EtlWatermark).where(EtlWatermark.source_table == tbl)
                    ).scalar_one_or_none()

                    strictly_greater = False
                    if is_reference or full_refresh or watermark is None:
                        window_start = None
                    elif self.overlap_minutes > 0:
                        window_start = watermark.last_updated_at - timedelta(
                            minutes=self.overlap_minutes
                        )
                    else:
                        window_start = watermark.last_updated_at
                        strictly_greater = True

                    extracted_count, max_ts = extract_table(
                        table_name=tbl,
                        erp_engine=self.erp_engine,
                        analytics_engine=self.analytics_engine,
                        run_id=run_id,
                        extracted_at=now,
                        window_start=window_start,
                        window_end=now,
                        strictly_greater=strictly_greater,
                        full_refresh=(is_reference or full_refresh),
                    )

                    table_counts[tbl] = extracted_count
                    total_rows += extracted_count

                    # Update high-watermark for incremental tables
                    if not is_reference and (max_ts is not None or watermark is None):
                        new_watermark_ts = max_ts or now
                        if watermark is None:
                            watermark = EtlWatermark(
                                source_table=tbl,
                                last_updated_at=new_watermark_ts,
                                last_run_id=run_id,
                            )
                            session.add(watermark)
                        else:
                            if max_ts and max_ts > watermark.last_updated_at:
                                watermark.last_updated_at = max_ts
                            watermark.last_run_id = run_id
                        session.commit()

            # 4. Finalize successful run
            finished_at = datetime.now(UTC)
            run_record.status = "success"
            run_record.finished_at = finished_at
            run_record.rows_extracted = total_rows
            session.commit()

            return {
                "run_id": run_id,
                "status": "success",
                "started_at": now.isoformat(),
                "finished_at": finished_at.isoformat(),
                "rows_extracted": total_rows,
                "table_counts": table_counts,
            }

        except Exception as exc:
            session.rollback()
            run_record.status = "failed"
            run_record.finished_at = datetime.now(UTC)
            run_record.error = str(exc)
            session.commit()
            raise
        finally:
            session.close()
