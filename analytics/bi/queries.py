"""
SQL Reference Queries for Power BI DAX Parity Testing (Roadmap §V1.5)
Executes deterministic SQL queries on the mart star schema matching the DAX formulas.
"""

from typing import Any

from sqlalchemy import Engine, text


class KpiQueryRunner:
    """Executes reference SQL queries against the analytical mart for DAX validation."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.is_postgres = engine.dialect.name == "postgresql"

    def _qual(self, schema: str, table: str) -> str:
        if self.is_postgres:
            return f"{schema}.{table}"
        return table

    def calculate_kpi_001_net_revenue(
        self, start_date_key: int | None = None, end_date_key: int | None = None
    ) -> float:
        """KPI-001: Net Revenue = SUM(net_revenue) on fact_sales_line."""
        tbl = self._qual("mart", "fact_sales_line")
        where_clauses = ["1=1"]
        params: dict[str, Any] = {}
        if start_date_key:
            where_clauses.append("date_key >= :start_k")
            params["start_k"] = start_date_key
        if end_date_key:
            where_clauses.append("date_key <= :end_k")
            params["end_k"] = end_date_key

        sql = f"SELECT COALESCE(SUM(net_revenue), 0.0) AS val FROM {tbl} WHERE {' AND '.join(where_clauses)}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql), params).scalar() or 0.0)

    def calculate_kpi_002_gross_margin(
        self, start_date_key: int | None = None, end_date_key: int | None = None
    ) -> float:
        """KPI-002: Gross Margin = SUM(gross_margin) on fact_sales_line."""
        tbl = self._qual("mart", "fact_sales_line")
        where_clauses = ["1=1"]
        params: dict[str, Any] = {}
        if start_date_key:
            where_clauses.append("date_key >= :start_k")
            params["start_k"] = start_date_key
        if end_date_key:
            where_clauses.append("date_key <= :end_k")
            params["end_k"] = end_date_key

        sql = f"SELECT COALESCE(SUM(gross_margin), 0.0) AS val FROM {tbl} WHERE {' AND '.join(where_clauses)}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql), params).scalar() or 0.0)

    def calculate_kpi_003_gross_margin_pct(
        self, start_date_key: int | None = None, end_date_key: int | None = None
    ) -> float:
        """KPI-003: Gross Margin % = Gross Margin / Net Revenue."""
        rev = self.calculate_kpi_001_net_revenue(start_date_key, end_date_key)
        margin = self.calculate_kpi_002_gross_margin(start_date_key, end_date_key)
        if rev == 0.0:
            return 0.0
        return margin / rev

    def calculate_kpi_004_orders(
        self, start_date_key: int | None = None, end_date_key: int | None = None
    ) -> int:
        """KPI-004: Orders = DISTINCTCOUNT(invoice_no) on fact_sales_line."""
        tbl = self._qual("mart", "fact_sales_line")
        where_clauses = ["invoice_no IS NOT NULL"]
        params: dict[str, Any] = {}
        if start_date_key:
            where_clauses.append("date_key >= :start_k")
            params["start_k"] = start_date_key
        if end_date_key:
            where_clauses.append("date_key <= :end_k")
            params["end_k"] = end_date_key

        sql = f"SELECT COUNT(DISTINCT invoice_no) AS val FROM {tbl} WHERE {' AND '.join(where_clauses)}"
        with self.engine.connect() as conn:
            return int(conn.execute(text(sql), params).scalar() or 0)

    def calculate_kpi_005_ar_outstanding(self) -> float:
        """KPI-005: AR Outstanding = SUM(amount) on fact_ar_allocation."""
        tbl = self._qual("mart", "fact_ar_allocation")
        sql = f"SELECT COALESCE(SUM(amount), 0.0) AS val FROM {tbl}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql)).scalar() or 0.0)

    def calculate_kpi_007_weighted_pipeline(self) -> float:
        """KPI-007: Weighted Pipeline = SUM(estimated_amount) on fact_opportunity_stage."""
        tbl = self._qual("mart", "fact_opportunity_stage")
        sql = f"SELECT COALESCE(SUM(estimated_amount), 0.0) AS val FROM {tbl}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql)).scalar() or 0.0)

    def calculate_kpi_010_avg_sales_cycle(self) -> float:
        """KPI-010: Avg Sales Cycle = AVERAGE(days_in_previous_stage)."""
        tbl = self._qual("mart", "fact_opportunity_stage")
        sql = f"SELECT COALESCE(AVG(days_in_previous_stage), 0.0) AS val FROM {tbl}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql)).scalar() or 0.0)

    def calculate_kpi_013_inventory_value(self) -> float:
        """KPI-013: Inventory Value = SUM(inventory_value) on fact_inventory_daily."""
        tbl = self._qual("mart", "fact_inventory_daily")
        sql = f"SELECT COALESCE(SUM(inventory_value), 0.0) AS val FROM {tbl}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql)).scalar() or 0.0)

    def calculate_kpi_016_purchase_spend(self) -> float:
        """KPI-016: Purchase Spend = SUM(cost) on fact_purchase_line."""
        tbl = self._qual("mart", "fact_purchase_line")
        sql = f"SELECT COALESCE(SUM(cost), 0.0) AS val FROM {tbl}"
        with self.engine.connect() as conn:
            return float(conn.execute(text(sql)).scalar() or 0.0)

    def calculate_kpi_017_supplier_on_time_rate(self) -> float:
        """KPI-017: Supplier On-Time Rate = lines with days_late <= 0 / total lines."""
        tbl = self._qual("mart", "fact_purchase_line")
        sql = f"""
        SELECT 
            COUNT(*) AS total_lines,
            SUM(CASE WHEN days_late <= 0 THEN 1 ELSE 0 END) AS on_time_lines
        FROM {tbl}
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().one()
            tot = int(row["total_lines"] or 0)
            if tot == 0:
                return 0.0
            return float(row["on_time_lines"] or 0) / tot
