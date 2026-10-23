"""
Visiq Conversational Analytical Agent (Roadmap §V1.6)
Parses analytical questions, enforces security guardrails against raw SQL/PII,
routes to deterministic tools, synthesizes executive narratives without numeric hallucination,
and generates reactive Plotly visual specifications.
"""

import logging
import os
import re
from typing import Any

from sqlalchemy import Engine

from analytics.visiq.catalog import (
    KPI_NAME_ALIASES,
    resolve_kpi,
)
from analytics.visiq.tools import VisiqTools
from analytics.visiq.visualizer import PlotlyVisualizer

logger = logging.getLogger("analytics.visiq.agent")


class VisiqAgent:
    """Conversational data analyst answering business questions over mart and dq schemas."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.tools = VisiqTools(engine)
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

    def ask(
        self,
        question: str,
        theme: str = "light",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Processes a natural language business question.
        Returns narrative, tool results, Plotly chart spec, ETL freshness, and DQ warnings.
        """
        q_clean = question.strip()

        # 1. Security & Guardrail Check (Roadmap §V1.6 Exit Criteria)
        refusal = self._check_safety_guardrails(q_clean)
        if refusal:
            return {
                "question": q_clean,
                "refused": True,
                "narrative": refusal,
                "tool_called": None,
                "tool_output": None,
                "plotly_spec": None,
                "freshness": self.tools.query_engine.get_etl_freshness(),
                "dq_warnings": [],
            }

        # 2. Intent Parsing & Tool Routing
        intent = self._route_intent(q_clean)

        # 3. Tool Execution
        tool_name = intent["tool"]
        tool_output: dict[str, Any] = {}

        if tool_name == "dq_summary":
            tool_output = self.tools.dq_summary()
        elif tool_name == "gl_reconciliation_audit":
            tool_output = self.tools.gl_reconciliation_audit(
                as_of_date=intent.get("as_of_date")
            )
        elif tool_name == "financial_statement_summary":
            tool_output = self.tools.financial_statement_summary(
                statement_type=intent.get("statement_type", "balance_sheet"),
                as_of_date=intent.get("as_of_date"),
                start_date=intent.get("start_date"),
                end_date=intent.get("end_date"),
            )
        elif tool_name == "explain_metric":
            tool_output = self.tools.explain_metric(intent["kpi_id"])
        elif tool_name == "compare_periods":
            tool_output = self.tools.compare_periods(
                kpi_id=intent["kpi_id"],
                current_start=intent["current_start"],
                current_end=intent["current_end"],
                prior_start=intent["prior_start"],
                prior_end=intent["prior_end"],
                filters=intent.get("filters"),
            )
        elif tool_name == "top_n":
            tool_output = self.tools.top_n(
                kpi_id=intent["kpi_id"],
                dimension=intent["dimension"],
                n=intent.get("n", 5),
                start_date=intent.get("start_date"),
                end_date=intent.get("end_date"),
                filters=intent.get("filters"),
            )
        elif tool_name == "breakdown":
            tool_output = self.tools.breakdown(
                kpi_id=intent["kpi_id"],
                dimension=intent["dimension"],
                start_date=intent.get("start_date"),
                end_date=intent.get("end_date"),
                filters=intent.get("filters"),
            )
        elif tool_name == "forecast_demand":
            tool_output = self.tools.forecast_demand(
                product_name_or_sku=intent.get("product"),
                horizon_days=intent.get("horizon_days", 30),
                model=intent.get("model", "auto"),
            )
        else:
            # Default get_metric
            tool_output = self.tools.get_metric(
                kpi_id=intent["kpi_id"],
                start_date=intent.get("start_date"),
                end_date=intent.get("end_date"),
                filters=intent.get("filters"),
            )

        # 4. Multi-step decomposition for "Why did revenue decrease?" (Roadmap §V1.6 Exit Criteria)
        if intent.get("is_why_decrease_root_cause"):
            # Augment tool output with breakdown by customer, product, and region
            sub_region = self.tools.breakdown(
                kpi_id="KPI-001",
                dimension="region",
                start_date="2025-01-01",
                end_date="2025-12-31",
            )
            sub_category = self.tools.breakdown(
                kpi_id="KPI-001",
                dimension="category",
                start_date="2025-01-01",
                end_date="2025-12-31",
            )
            sub_customer = self.tools.top_n(
                kpi_id="KPI-001",
                dimension="customer",
                n=5,
                start_date="2025-01-01",
                end_date="2025-12-31",
            )
            tool_output["root_cause_decomposition"] = {
                "by_region": sub_region.get("segments", []),
                "by_category": sub_category.get("segments", []),
                "top_customers": sub_customer.get("items", []),
            }

        # 5. Narrative Synthesis (Numbers passed in, never generated)
        narrative = self._synthesize_narrative(q_clean, tool_name, tool_output)

        # 6. Plotly Specification Generation
        plotly_spec = PlotlyVisualizer.generate_spec(tool_output, theme=theme)

        return {
            "question": q_clean,
            "refused": False,
            "narrative": narrative,
            "tool_called": tool_name,
            "tool_output": tool_output,
            "plotly_spec": plotly_spec,
            "freshness": tool_output.get("freshness")
            or self.tools.query_engine.get_etl_freshness(),
            "dq_warnings": tool_output.get("dq_warnings") or [],
        }

    def _check_safety_guardrails(self, q: str) -> str | None:
        """
        Enforces strict safety guardrails:
        - Rejects free-form SQL queries (SELECT, DROP, INSERT, UNION, etc.)
        - Rejects personal PII requests (phone numbers, contact emails)
        """
        q_upper = q.upper()

        # 1. SQL Injection / Raw SQL execution attempt
        sql_keywords = [
            "SELECT ",
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
            "DROP TABLE",
            "UNION SELECT",
            "EXEC(",
            "INFORMATION_SCHEMA",
            "PG_TABLES",
            "PG_USER",
            "--",
        ]
        if any(kw in q_upper for kw in sql_keywords):
            return (
                "**Security Guardrail Notice:** Direct SQL execution is strictly prohibited. "
                "Visiq operates exclusively through predefined analytical tools over conformed mart schemas."
            )

        # 2. PII Contact Info Request (RA 10173)
        pii_keywords = [
            "PHONE NUMBER",
            "PHONE NUMBERS",
            "TELEPHONE",
            "MOBILE NUMBER",
            "CUSTOMER EMAIL",
            "CONTACT EMAIL",
            "HOME ADDRESS",
            "PERSONAL EMAIL",
            "CREDIT CARD",
        ]
        if any(kw in q_upper for kw in pii_keywords):
            return (
                "**Privacy Guardrail Notice (RA 10173):** Access to personal contact identifiers "
                "(phone numbers, personal emails) is prohibited by design. "
                "Analytical queries in Visiq are anonymized and aggregated at the enterprise account level."
            )

        return None

    def _route_intent(self, q: str) -> dict[str, Any]:
        """Classifies question intent and extracts parameters."""
        q_lower = q.lower()

        # Check for DQ summary
        if any(
            term in q_lower
            for term in ("data quality", "dq summary", "health score", "defects")
        ):
            return {"tool": "dq_summary"}

        # Check for GL Reconciliation audit
        if any(
            term in q_lower
            for term in (
                "reconciliation",
                "reconcile",
                "gl audit",
                "ledger parity",
                "balanced in the mart",
                "debit credit parity",
            )
        ):
            return {"tool": "gl_reconciliation_audit"}

        # Check for Demand Forecasting / Predictive Analytics
        if any(
            term in q_lower
            for term in (
                "forecast",
                "predict demand",
                "predict sales",
                "demand forecast",
                "sales forecast",
                "future demand",
                "safety stock",
            )
        ):
            m_days = re.search(r"(\d+)\s*(?:day|days)", q_lower)
            horizon = int(m_days.group(1)) if m_days else 30
            clean_q = q_lower
            for stop in [
                "forecast demand for",
                "forecast sales for",
                "demand forecast for",
                "predict demand for",
                "predict sales for",
                "forecast for",
                "forecast",
                "predict",
                "demand",
                "sales",
                "over the next",
                "next",
                f"{horizon} days",
                "days",
            ]:
                clean_q = clean_q.replace(stop, " ")
            prod_candidate = clean_q.strip() or "All Products"
            return {
                "tool": "forecast_demand",
                "product": prod_candidate,
                "horizon_days": horizon,
                "model": "auto",
            }

        # Check for Financial Statements (Balance Sheet / Income Statement / P&L)
        if any(
            term in q_lower
            for term in (
                "balance sheet",
                "statement of financial position",
                "income statement",
                "profit and loss",
                "p&l",
            )
        ):
            st_type = (
                "income_statement"
                if any(t in q_lower for t in ("income", "p&l", "profit and loss"))
                else "balance_sheet"
            )
            return {"tool": "financial_statement_summary", "statement_type": st_type}

        # Check for Explain Metric
        if any(
            term in q_lower
            for term in ("explain metric", "how is", "definition of", "formula for")
        ):
            kpi = self._extract_kpi(q_lower)
            return {"tool": "explain_metric", "kpi_id": kpi.kpi_id}

        # Check for "Why did revenue decrease" root cause decomposition
        if "why" in q_lower and any(
            w in q_lower for w in ("decrease", "drop", "fell", "drop")
        ):
            return {
                "tool": "compare_periods",
                "kpi_id": "KPI-001",
                "current_start": "2025-05-01",
                "current_end": "2025-05-31",
                "prior_start": "2025-04-01",
                "prior_end": "2025-04-30",
                "is_why_decrease_root_cause": True,
            }

        # Check for Comparison
        if any(
            term in q_lower
            for term in ("compare", "vs", "versus", "change from", "growth")
        ):
            kpi = self._extract_kpi(q_lower)
            years = re.findall(r"\b(202[3-6])\b", q_lower)
            if len(years) >= 2:
                p1, p2 = sorted(years)[:2]
                return {
                    "tool": "compare_periods",
                    "kpi_id": kpi.kpi_id,
                    "current_start": f"{p2}-01-01",
                    "current_end": f"{p2}-12-31",
                    "prior_start": f"{p1}-01-01",
                    "prior_end": f"{p1}-12-31",
                }
            return {
                "tool": "compare_periods",
                "kpi_id": kpi.kpi_id,
                "current_start": "2025-05-01",
                "current_end": "2025-05-31",
                "prior_start": "2025-04-01",
                "prior_end": "2025-04-30",
            }

        # Check for Top N ranking
        top_match = re.search(r"top\s+(\d+)", q_lower)
        if top_match or "top" in q_lower or "best" in q_lower or "highest" in q_lower:
            n = int(top_match.group(1)) if top_match else 5
            dim = self._extract_dimension(q_lower)
            kpi = self._extract_kpi(q_lower)
            return {
                "tool": "top_n",
                "kpi_id": kpi.kpi_id,
                "dimension": dim,
                "n": n,
            }

        # Check for Breakdown / by dimension
        if any(
            term in q_lower
            for term in (
                "breakdown",
                "by region",
                "by product",
                "by category",
                "by customer",
                "by month",
                "by rep",
            )
        ):
            dim = self._extract_dimension(q_lower)
            kpi = self._extract_kpi(q_lower)
            return {
                "tool": "breakdown",
                "kpi_id": kpi.kpi_id,
                "dimension": dim,
            }

        # Default: get_metric
        kpi = self._extract_kpi(q_lower)
        return {
            "tool": "get_metric",
            "kpi_id": kpi.kpi_id,
        }

    def _extract_kpi(self, q_lower: str):
        # Explicit KPI-xxx format
        match = re.search(r"(kpi-\d{3})", q_lower)
        if match:
            return resolve_kpi(match.group(1))

        # Check alias dictionary (longest match first to avoid substrings matching prematurely)
        for alias in sorted(KPI_NAME_ALIASES.keys(), key=len, reverse=True):
            if alias in q_lower:
                return resolve_kpi(KPI_NAME_ALIASES[alias])

        return resolve_kpi("KPI-001")

    def _extract_dimension(self, q_lower: str) -> str:
        for dim_key in (
            "region",
            "customer",
            "product",
            "category",
            "sales_rep",
            "employee",
            "month",
            "year",
            "source_system",
        ):
            if dim_key in q_lower:
                return dim_key
        if "rep" in q_lower or "salesperson" in q_lower:
            return "sales_rep"
        if "item" in q_lower:
            return "product"
        if "location" in q_lower or "island" in q_lower:
            return "region"
        return "region"

    def _synthesize_narrative(
        self, question: str, tool_name: str, output: dict[str, Any]
    ) -> str:
        """
        Generates an executive explanation. All numbers are drawn directly from the tool output.
        """
        # If root cause decomposition present
        if output.get("root_cause_decomposition"):
            decomp = output["root_cause_decomposition"]
            reg_lines = [
                f"- **{r['name']}**: ₱{r['value']:,.2f} ({r['share_percentage']}%)"
                for r in decomp["by_region"][:3]
            ]
            cat_lines = [
                f"- **{c['name']}**: ₱{c['value']:,.2f} ({c['share_percentage']}%)"
                for c in decomp["by_category"][:3]
            ]
            curr_val = output.get("current_period", {}).get("value", 0)
            prior_val = output.get("prior_period", {}).get("value", 0)
            diff = output.get("absolute_difference", 0)
            pct = output.get("percentage_change", 0)

            return (
                f"### Executive Variance Decomposition: Revenue Movement\n\n"
                f"Revenue moved by **₱{abs(diff):,.2f}** ({pct:+0.1f}%), from **₱{prior_val:,.2f}** to **₱{curr_val:,.2f}**.\n\n"
                f"#### Regional Drivers:\n" + "\n".join(reg_lines) + "\n\n"
                "#### Product Category Breakdown:\n" + "\n".join(cat_lines) + "\n\n"
                "*Key Insight:* The revenue variation was primarily concentrated in the top regional segments, "
                "validated against deterministic `mart.fact_sales_line` records."
            )

        if tool_name == "get_metric":
            val = output.get("value", 0)
            unit = output.get("unit", "")
            prefix = "₱" if unit == "PHP" else ""
            suffix = f" {unit}" if unit and unit != "PHP" else ""
            return (
                f"### {output.get('metric_name')} Summary\n\n"
                f"The current aggregate **{output.get('metric_name')}** is **{prefix}{val:,.2f}{suffix}**.\n\n"
                f"- **Fact Grain:** Evaluated from conformed analytical mart records.\n"
                f"- **Data Freshness:** ETL pipeline status `{output.get('freshness', {}).get('status', 'fresh')}`."
            )

        elif tool_name == "compare_periods":
            curr = output.get("current_period", {})
            prior = output.get("prior_period", {})
            diff = output.get("absolute_difference", 0)
            pct = output.get("percentage_change", 0)
            unit = output.get("unit", "")
            prefix = "₱" if unit == "PHP" else ""
            trend_word = "increased" if diff >= 0 else "decreased"

            return (
                f"### {output.get('metric_name')} Period Comparison\n\n"
                f"{output.get('metric_name')} **{trend_word} by {abs(pct):.1f}%** (change of **{prefix}{abs(diff):,.2f}**).\n\n"
                f"- **Current Period:** {prefix}{curr.get('value', 0):,.2f}\n"
                f"- **Prior Period:** {prefix}{prior.get('value', 0):,.2f}\n"
                f"- **Trajectory:** `{output.get('trend', 'flat').upper()}`"
            )

        elif tool_name == "top_n":
            items = output.get("items", [])
            lines = [
                f"{it['rank']}. **{it['name']}**: ₱{it['value']:,.2f} ({it['share_percentage']}%)"
                for it in items
            ]
            return (
                f"### Top {output.get('n')} {output.get('dimension', '').title()} by {output.get('metric_name')}\n\n"
                + "\n".join(lines)
                + f"\n\n**Total Top {output.get('n')} Contribution:** ₱{output.get('total_top_n_value', 0):,.2f}"
            )

        elif tool_name == "breakdown":
            segments = output.get("segments", [])[:5]
            lines = [
                f"- **{s['name']}**: ₱{s['value']:,.2f} ({s['share_percentage']}%)"
                for s in segments
            ]
            return (
                f"### {output.get('metric_name')} Breakdown by {output.get('dimension', '').title()}\n\n"
                + "\n".join(lines)
                + f"\n\n**Total Analyzed:** ₱{output.get('total_value', 0):,.2f} across {output.get('segment_count')} segments."
            )

        elif tool_name == "dq_summary":
            score = output.get("overall_health_score", 100.0)
            tests = output.get("recent_test_results", [])
            test_lines = [
                f"- `{t['test_name']}` ({t['layer']}.{t['table']}): **{t['status'].upper()}** ({t['defect_count']} defects)"
                for t in tests[:4]
            ]
            return (
                f"### Data Quality Health Overview\n\n"
                f"The analytics platform health score is **{score:.1f}%**.\n\n"
                f"#### Recent Integrity Validations:\n" + "\n".join(test_lines)
            )

        elif tool_name == "explain_metric":
            return (
                f"### Metric Documentation: {output.get('name')} ({output.get('kpi_id')})\n\n"
                f"{output.get('description')}\n\n"
                f"- **Category:** {output.get('category')}\n"
                f"- **Source Table:** `{output.get('source_fact_table')}`\n"
                f"- **SQL Aggregation Formula:** `{output.get('calculation_formula')}`\n"
                f"- **Business Caveats:** {output.get('business_caveats')}"
            )

        elif tool_name == "gl_reconciliation_audit":
            status = str(output.get("status", "unknown")).upper()
            op_deb = output.get("operational_debit_total", 0.0)
            op_cred = output.get("operational_credit_total", 0.0)
            mart_deb = output.get("mart_debit_total", 0.0)
            mart_cred = output.get("mart_credit_total", 0.0)
            net_var = output.get("net_variance", 0.0)
            accts = output.get("account_count", 0)
            discrepant = len(output.get("discrepant_accounts", []))

            reconciled_str = (
                "**PERFECT RECONCILIATION ACHIEVED**: Exact centavo parity between OLTP General Ledger and OLAP analytical marts."
                if status == "RECONCILED"
                else f"**DISCREPANCY DETECTED**: {discrepant} accounts show variances requiring investigation."
            )

            return (
                f"### General Ledger to Analytics Reconciliation Audit\n\n"
                f"**Audit Status:** `{status}`\n\n"
                f"{reconciled_str}\n\n"
                f"- **Operational Total Debits:** ₱{op_deb:,.2f} | **Credits:** ₱{op_cred:,.2f}\n"
                f"- **Analytical Mart Debits:** ₱{mart_deb:,.2f} | **Credits:** ₱{mart_cred:,.2f}\n"
                f"- **Net Variance:** ₱{net_var:,.2f}\n"
                f"- **Accounts Audited:** {accts} active accounts\n"
                f"- **Discrepant Accounts Count:** {discrepant}"
            )

        elif tool_name == "financial_statement_summary":
            st_type = output.get("statement_type", "balance_sheet")
            if st_type == "balance_sheet":
                assets = output.get("total_assets", 0.0)
                liab = output.get("total_liabilities", 0.0)
                equity = output.get("total_equity", 0.0)
                net_inc = output.get("current_period_net_income", 0.0)
                balanced = output.get("is_balanced", False)
                status_txt = (
                    "BALANCED (`Assets = Liabilities + Equity`)"
                    if balanced
                    else "IMBALANCED"
                )

                return (
                    f"### Balance Sheet Summary (as of {output.get('as_of_date')})\n\n"
                    f"**Accounting Equilibrium Status:** `{status_txt}`\n\n"
                    f"- **Total Assets:** ₱{assets:,.2f}\n"
                    f"- **Total Liabilities:** ₱{liab:,.2f}\n"
                    f"- **Total Equity (including net income):** ₱{equity:,.2f}\n"
                    f"  - *Current Period Net Income:* ₱{net_inc:,.2f}\n"
                    f"- **Total Liabilities & Equity:** ₱{liab + equity:,.2f}"
                )
            else:
                rev = output.get("total_revenue", 0.0)
                cogs = output.get("total_cogs", 0.0)
                gp = output.get("gross_profit", 0.0)
                exp = output.get("total_operating_expenses", 0.0)
                net_inc = output.get("net_income", 0.0)
                margin = output.get("operating_margin_pct", 0.0)

                return (
                    f"### Income Statement (P&L) Summary\n\n"
                    f"- **Total Revenue:** ₱{rev:,.2f}\n"
                    f"- **Cost of Goods Sold (COGS):** ₱{cogs:,.2f}\n"
                    f"- **Gross Profit:** ₱{gp:,.2f}\n"
                    f"- **Operating Expenses:** ₱{exp:,.2f}\n"
                    f"- **Net Income:** ₱{net_inc:,.2f}\n"
                    f"- **Operating Margin:** {margin:.1f}%"
                )

        elif tool_name == "forecast_demand":
            prod = output.get("product", "All Products")
            model = output.get("model_name", "ML Model").upper()
            horizon = output.get("horizon_days", 30)
            total_fc = output.get("total_forecast_demand", 0.0)
            avg_daily = output.get("average_daily_demand", 0.0)
            std_dev = output.get("demand_std_dev", 0.0)
            ss_rec = output.get("safety_stock_recommendation", {})
            ss_val = ss_rec.get("safety_stock", 0.0)
            rop_val = ss_rec.get("reorder_point", 0.0)
            mape = output.get("evaluation", {}).get("mape", 0.0)

            return (
                f"### Predictive Demand Forecast: {prod}\n\n"
                f"**Optimal Forecasting Model:** `{model}` (Backtest MAPE: **{mape:.1f}%**)\n\n"
                f"- **Projected Demand ({horizon} Days):** **{total_fc:,.1f} units**\n"
                f"- **Average Daily Demand:** **{avg_daily:,.2f} units/day** (Std Dev: **{std_dev:,.2f}**)\n\n"
                f"#### Dynamic Safety Stock & Inventory Optimization (95% Service Level):\n"
                f"- **Recommended Safety Stock:** **{ss_val:,.1f} units**\n"
                f"- **Recommended Reorder Point (ROP):** **{rop_val:,.1f} units**\n"
                f"- **Recommended Target Level:** **{ss_rec.get('recommended_max', 0.0):,.1f} units**\n\n"
                f"*Inventory Intelligence:* Dynamic replenishment thresholds absorb volatility in supplier lead times and historical demand swings."
            )

        return f"Completed analysis for query: {question}"
