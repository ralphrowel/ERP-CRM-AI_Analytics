"""
Power BI DAX Measure Catalog and KPI Dictionary Alignment (Roadmap §V1.5 & §11)
Defines all 19 standardized enterprise KPI measures, business definitions,
DAX formulas, formatting tokens, and time-intelligence variants.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DaxMeasure:
    kpi_id: str
    name: str
    domain: str
    description: str
    table: str
    expression: str
    format_string: str = "#,##0.00"
    time_intelligence: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kpi_id": self.kpi_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "table": self.table,
            "expression": self.expression,
            "format_string": self.format_string,
            "time_intelligence": self.time_intelligence,
        }


def get_kpi_dax_catalog() -> list[DaxMeasure]:
    """
    Returns the comprehensive catalog of all 19 KPI measures defined in Roadmap §11
    with rigorous DAX syntax optimized for Power BI Analysis Services / Tabular engine.
    """
    return [
        # ---------------------------------------------------------------------
        # 1. Financial & Revenue Domain (KPI-001 - KPI-003)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-001",
            name="KPI-001 Net Revenue",
            domain="revenue",
            description="Total accrual net revenue excluding VAT: sum of issued/paid invoices minus issued credit notes.",
            table="fact_sales_line",
            expression="SUM(fact_sales_line[net_revenue])",
            format_string="₱#,##0.00",
            time_intelligence={
                "MTD": "TOTALMTD([KPI-001 Net Revenue], dim_date[date])",
                "YTD": "TOTALYTD([KPI-001 Net Revenue], dim_date[date])",
                "PY": "CALCULATE([KPI-001 Net Revenue], SAMEPERIODLASTYEAR(dim_date[date]))",
                "YoY_Growth": "DIVIDE([KPI-001 Net Revenue] - [KPI-001 Net Revenue PY], [KPI-001 Net Revenue PY], 0)",
                "MoM_Growth": "DIVIDE([KPI-001 Net Revenue] - CALCULATE([KPI-001 Net Revenue], DATEADD(dim_date[date], -1, MONTH)), CALCULATE([KPI-001 Net Revenue], DATEADD(dim_date[date], -1, MONTH)), 0)",
            },
        ),
        DaxMeasure(
            kpi_id="KPI-002",
            name="KPI-002 Gross Margin",
            domain="revenue",
            description="Net Revenue minus cost of goods sold (COGS).",
            table="fact_sales_line",
            expression="SUM(fact_sales_line[gross_margin])",
            format_string="₱#,##0.00",
            time_intelligence={
                "YTD": "TOTALYTD([KPI-002 Gross Margin], dim_date[date])",
                "PY": "CALCULATE([KPI-002 Gross Margin], SAMEPERIODLASTYEAR(dim_date[date]))",
                "YoY_Growth": "DIVIDE([KPI-002 Gross Margin] - [KPI-002 Gross Margin PY], [KPI-002 Gross Margin PY], 0)",
            },
        ),
        DaxMeasure(
            kpi_id="KPI-003",
            name="KPI-003 Gross Margin %",
            domain="revenue",
            description="Gross Margin as a percentage of Net Revenue.",
            table="fact_sales_line",
            expression="DIVIDE([KPI-002 Gross Margin], [KPI-001 Net Revenue], 0)",
            format_string="0.0%",
            time_intelligence={
                "YTD": "DIVIDE([KPI-002 Gross Margin YTD], [KPI-001 Net Revenue YTD], 0)",
            },
        ),
        # ---------------------------------------------------------------------
        # 2. Commercial & Orders Domain (KPI-004)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-004",
            name="KPI-004 Orders",
            domain="sales",
            description="Count of distinct confirmed customer sales orders in the period.",
            table="fact_sales_line",
            expression="DISTINCTCOUNT(fact_sales_line[invoice_no])",
            format_string="#,##0",
            time_intelligence={
                "MTD": "TOTALMTD([KPI-004 Orders], dim_date[date])",
                "YTD": "TOTALYTD([KPI-004 Orders], dim_date[date])",
                "PY": "CALCULATE([KPI-004 Orders], SAMEPERIODLASTYEAR(dim_date[date]))",
            },
        ),
        # ---------------------------------------------------------------------
        # 3. Credit & Accounts Receivable (KPI-005 - KPI-006)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-005",
            name="KPI-005 AR Outstanding",
            domain="ar",
            description="Total outstanding accounts receivable balances on unpaid or partially paid invoices.",
            table="fact_ar_allocation",
            expression="SUM(fact_ar_allocation[amount])",
            format_string="₱#,##0.00",
        ),
        DaxMeasure(
            kpi_id="KPI-006",
            name="KPI-006 AR Aging",
            domain="ar",
            description="Accounts receivable balance categorized by days past due date (current, 1-30, 31-60, 61-90, 90+).",
            table="fact_ar_allocation",
            expression=(
                "CALCULATE(SUM(fact_ar_allocation[amount]), "
                "FILTER(fact_ar_allocation, fact_ar_allocation[days_after_due] > 0))"
            ),
            format_string="₱#,##0.00",
        ),
        # ---------------------------------------------------------------------
        # 4. Pipeline & Sales Execution Domain (KPI-007 - KPI-010)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-007",
            name="KPI-007 Weighted Pipeline",
            domain="crm",
            description="Sum of opportunity estimated amounts weighted by stage probability.",
            table="fact_opportunity_stage",
            expression="SUM(fact_opportunity_stage[estimated_amount])",
            format_string="₱#,##0.00",
        ),
        DaxMeasure(
            kpi_id="KPI-008",
            name="KPI-008 Win Rate",
            domain="crm",
            description="Ratio of won opportunities to total closed (won + lost) opportunities in the period.",
            table="fact_opportunity_stage",
            expression=(
                'VAR WonCount = CALCULATE(COUNTROWS(fact_opportunity_stage), fact_opportunity_stage[to_stage] = "closed_won") '
                'VAR ClosedCount = CALCULATE(COUNTROWS(fact_opportunity_stage), fact_opportunity_stage[to_stage] IN {"closed_won", "closed_lost"}) '
                "RETURN DIVIDE(WonCount, ClosedCount, 0)"
            ),
            format_string="0.0%",
        ),
        DaxMeasure(
            kpi_id="KPI-009",
            name="KPI-009 Lead Conversion Rate",
            domain="crm",
            description="Ratio of converted leads to total leads created in the cohort.",
            table="fact_opportunity_stage",
            expression=(
                'VAR Converted = CALCULATE(COUNTROWS(fact_opportunity_stage), fact_opportunity_stage[from_stage] = "lead_qualification") '
                "VAR Total = COUNTROWS(fact_opportunity_stage) "
                "RETURN DIVIDE(Converted, Total, 0)"
            ),
            format_string="0.0%",
        ),
        DaxMeasure(
            kpi_id="KPI-010",
            name="KPI-010 Avg Sales Cycle",
            domain="crm",
            description="Average days elapsed from opportunity creation to closed-won milestone.",
            table="fact_opportunity_stage",
            expression="AVERAGE(fact_opportunity_stage[days_in_previous_stage])",
            format_string='0.0 "days"',
        ),
        # ---------------------------------------------------------------------
        # 5. Customer Intelligence Domain (KPI-011 - KPI-012)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-011",
            name="KPI-011 Active Customers",
            domain="customer",
            description="Count of distinct customers with at least one transaction in the trailing 12 months.",
            table="fact_sales_line",
            expression=(
                "CALCULATE(DISTINCTCOUNT(fact_sales_line[customer_key]), "
                "DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -12, MONTH))"
            ),
            format_string="#,##0",
        ),
        DaxMeasure(
            kpi_id="KPI-012",
            name="KPI-012 New Customers",
            domain="customer",
            description="Count of customers whose initial transaction occurred during the evaluated period.",
            table="fact_sales_line",
            expression=(
                "VAR CurrentCust = VALUES(fact_sales_line[customer_key]) "
                "VAR PriorCust = CALCULATE(VALUES(fact_sales_line[customer_key]), FILTER(ALL(dim_date), dim_date[date] < MIN(dim_date[date]))) "
                "RETURN COUNTROWS(EXCEPT(CurrentCust, PriorCust))"
            ),
            format_string="#,##0",
        ),
        # ---------------------------------------------------------------------
        # 6. Inventory & Supply Chain Domain (KPI-013 - KPI-015)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-013",
            name="KPI-013 Inventory Value",
            domain="inventory",
            description="Total on-hand inventory valuation at standard cost as of latest snapshot date.",
            table="fact_inventory_daily",
            expression=(
                "CALCULATE(SUM(fact_inventory_daily[inventory_value]), "
                "LASTDATE(fact_inventory_daily[date_key]))"
            ),
            format_string="₱#,##0.00",
        ),
        DaxMeasure(
            kpi_id="KPI-014",
            name="KPI-014 Inventory Turnover",
            domain="inventory",
            description="Trailing 12-month COGS divided by average inventory valuation.",
            table="fact_inventory_daily",
            expression=(
                "VAR T12COGS = CALCULATE(SUM(fact_sales_line[cogs]), DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -12, MONTH)) "
                "VAR AvgInv = AVERAGE(fact_inventory_daily[inventory_value]) "
                "RETURN DIVIDE(T12COGS, AvgInv, 0)"
            ),
            format_string='0.00 "x"',
        ),
        DaxMeasure(
            kpi_id="KPI-015",
            name="KPI-015 Low-Stock Items",
            domain="inventory",
            description="Count of product-warehouse combinations where available quantity is below safety stock.",
            table="fact_inventory_daily",
            expression="COUNTROWS(FILTER(fact_inventory_daily, fact_inventory_daily[qty_on_hand] <= 10))",
            format_string="#,##0",
        ),
        # ---------------------------------------------------------------------
        # 7. Procurement & Supplier Performance (KPI-016 - KPI-017)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-016",
            name="KPI-016 Purchase Spend",
            domain="purchasing",
            description="Total procurement spend across purchase order line items in the period.",
            table="fact_purchase_line",
            expression="SUM(fact_purchase_line[cost])",
            format_string="₱#,##0.00",
            time_intelligence={
                "MTD": "TOTALMTD([KPI-016 Purchase Spend], dim_date[date])",
                "YTD": "TOTALYTD([KPI-016 Purchase Spend], dim_date[date])",
            },
        ),
        DaxMeasure(
            kpi_id="KPI-017",
            name="KPI-017 Supplier On-Time Rate",
            domain="purchasing",
            description="Percentage of purchase order deliveries completed on or before expected delivery date.",
            table="fact_purchase_line",
            expression=(
                "VAR OnTimeLines = CALCULATE(COUNTROWS(fact_purchase_line), fact_purchase_line[days_late] <= 0) "
                "VAR TotalLines = COUNTROWS(fact_purchase_line) "
                "RETURN DIVIDE(OnTimeLines, TotalLines, 0)"
            ),
            format_string="0.0%",
        ),
        # ---------------------------------------------------------------------
        # 8. Working Capital & Data Quality (KPI-018 - KPI-019)
        # ---------------------------------------------------------------------
        DaxMeasure(
            kpi_id="KPI-018",
            name="KPI-018 DSO",
            domain="ar",
            description="Days Sales Outstanding: AR Outstanding divided by (Net Revenue in last 90 days / 90).",
            table="fact_ar_allocation",
            expression=(
                "VAR Rev90 = CALCULATE(SUM(fact_sales_line[net_revenue]), DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -90, DAY)) "
                "VAR DailyRev = DIVIDE(Rev90, 90, 0) "
                "RETURN DIVIDE([KPI-005 AR Outstanding], DailyRev, 0)"
            ),
            format_string='0.0 "days"',
        ),
        DaxMeasure(
            kpi_id="KPI-019",
            name="KPI-019 Data Quality Score",
            domain="dq",
            description="Weighted pass rate score across all evaluated data quality rules (0 to 100).",
            table="_Measures",
            expression="AVERAGE(dq_results[score])",
            format_string='0.0 "%"',
        ),
    ]


def get_all_dax_expressions() -> str:
    """Formats all KPI measures and their time-intelligence variants as clean DAX code."""
    catalog = get_kpi_dax_catalog()
    lines: list[str] = [
        "// =============================================================================",
        "// Power BI DAX Measures Catalog (Roadmap §V1.5 & §11)",
        "// Auto-generated by analytics.bi.dax engine",
        "// =============================================================================",
        "",
    ]

    for m in catalog:
        lines.append(f"// --- {m.kpi_id}: {m.name} ({m.domain.upper()}) ---")
        lines.append(f"// {m.description}")
        lines.append(f"[{m.name}] =")
        lines.append(f"    {m.expression}")
        lines.append("")

        for suffix, t_expr in m.time_intelligence.items():
            lines.append(f"[{m.name} {suffix}] =")
            lines.append(f"    {t_expr}")
            lines.append("")

    return "\n".join(lines)
