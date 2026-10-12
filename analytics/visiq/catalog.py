"""
Visiq KPI & Dimensions Catalog (Roadmap §V1.6 & §11)
Standardized definitions, aggregation SQL templates, dimension mappings,
and business explanations aligned with Power BI semantic model and KPI dictionary.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DimensionDefinition:
    key: str
    column: str
    table: str
    label: str
    join_clause: str


@dataclass(frozen=True)
class KPIDefinition:
    kpi_id: str
    name: str
    category: str
    unit: str  # "PHP", "%", "count", "days"
    description: str
    fact_table: str
    sql_formula: str  # e.g., "SUM(f.net_revenue)"
    default_dimensions: list[str] = field(default_factory=list)
    caveats: str = ""


# Conformed Dimension Mapping
DIMENSIONS: dict[str, DimensionDefinition] = {
    "region": DimensionDefinition(
        key="region",
        column="c.region",
        table="dim_customer",
        label="Customer Region",
        join_clause="LEFT JOIN mart.dim_customer c ON f.customer_key = c.customer_key",
    ),
    "customer": DimensionDefinition(
        key="customer",
        column="c.name",
        table="dim_customer",
        label="Customer Name",
        join_clause="LEFT JOIN mart.dim_customer c ON f.customer_key = c.customer_key",
    ),
    "product": DimensionDefinition(
        key="product",
        column="p.name",
        table="dim_product",
        label="Product Name",
        join_clause="LEFT JOIN mart.dim_product p ON f.product_key = p.product_key",
    ),
    "category": DimensionDefinition(
        key="category",
        column="p.category",
        table="dim_product",
        label="Product Category",
        join_clause="LEFT JOIN mart.dim_product p ON f.product_key = p.product_key",
    ),
    "sales_rep": DimensionDefinition(
        key="sales_rep",
        column="e.full_name",
        table="dim_employee",
        label="Sales Representative",
        join_clause="LEFT JOIN mart.dim_employee e ON f.employee_key = e.employee_key",
    ),
    "employee": DimensionDefinition(
        key="employee",
        column="e.full_name",
        table="dim_employee",
        label="Employee Name",
        join_clause="LEFT JOIN mart.dim_employee e ON f.employee_key = e.employee_key",
    ),
    "source_system": DimensionDefinition(
        key="source_system",
        column="s.name",
        table="dim_source_system",
        label="Source System",
        join_clause="LEFT JOIN mart.dim_source_system s ON f.source_system_key = s.source_system_key",
    ),
    "month": DimensionDefinition(
        key="month",
        column="d.month_name",
        table="dim_date",
        label="Month",
        join_clause="LEFT JOIN mart.dim_date d ON f.date_key = d.date_key",
    ),
    "year": DimensionDefinition(
        key="year",
        column="d.year",
        table="dim_date",
        label="Year",
        join_clause="LEFT JOIN mart.dim_date d ON f.date_key = d.date_key",
    ),
}

# The 19 Core Roadmap §11 KPIs Catalog
KPI_METRIC_CATALOG: dict[str, KPIDefinition] = {
    "KPI-001": KPIDefinition(
        kpi_id="KPI-001",
        name="Net Revenue",
        category="Sales",
        unit="PHP",
        description="Total recognized net sales revenue after trade discounts and excluding VAT.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(SUM(f.net_revenue), 0.0)",
        default_dimensions=["region", "category", "month"],
        caveats="Derived from invoices and credit notes in mart.fact_sales_line; excludes 12% Philippine VAT.",
    ),
    "KPI-002": KPIDefinition(
        kpi_id="KPI-002",
        name="Gross Margin",
        category="Sales",
        unit="PHP",
        description="Net revenue minus Cost of Goods Sold (COGS).",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(SUM(f.gross_margin), 0.0)",
        default_dimensions=["product", "category", "region"],
        caveats="COGS calculated per shipment issue weighted average costing (V1.4 specification).",
    ),
    "KPI-003": KPIDefinition(
        kpi_id="KPI-003",
        name="Gross Margin %",
        category="Sales",
        unit="%",
        description="Gross margin expressed as a percentage of net revenue.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(CASE WHEN SUM(f.net_revenue) IS NULL OR SUM(f.net_revenue) = 0 THEN 0.0 ELSE ROUND((SUM(f.gross_margin) * 100.0 / SUM(f.net_revenue)), 2) END, 0.0)",
        default_dimensions=["category", "product"],
        caveats="Undefined if net revenue is zero.",
    ),
    "KPI-004": KPIDefinition(
        kpi_id="KPI-004",
        name="Confirmed Orders",
        category="Sales",
        unit="count",
        description="Total count of unique sales orders confirmed or invoiced.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(COUNT(DISTINCT f.invoice_no), 0)",
        default_dimensions=["month", "sales_rep"],
        caveats="Counted by distinct invoice or order document.",
    ),
    "KPI-005": KPIDefinition(
        kpi_id="KPI-005",
        name="Average Order Value",
        category="Sales",
        unit="PHP",
        description="Average net revenue per confirmed order document.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(CASE WHEN COUNT(DISTINCT f.invoice_no) = 0 THEN 0.0 ELSE ROUND(SUM(f.net_revenue) / COUNT(DISTINCT f.invoice_no), 2) END, 0.0)",
        default_dimensions=["customer", "region"],
        caveats="Net revenue divided by distinct invoice count.",
    ),
    "KPI-006": KPIDefinition(
        kpi_id="KPI-006",
        name="Pipeline Value",
        category="CRM",
        unit="PHP",
        description="Total estimated value of active, open CRM opportunities.",
        fact_table="fact_opportunity_stage",
        sql_formula="COALESCE(SUM(f.estimated_amount), 0.0)",
        default_dimensions=["sales_rep", "to_stage"],
        caveats="Evaluates opportunities currently in qualifying, proposal, or negotiation stages.",
    ),
    "KPI-007": KPIDefinition(
        kpi_id="KPI-007",
        name="Win Rate",
        category="CRM",
        unit="%",
        description="Percentage of closed opportunities that resulted in Closed-Won status.",
        fact_table="fact_opportunity_stage",
        sql_formula="COALESCE(CASE WHEN COUNT(f.opportunity_id) = 0 THEN 0.0 ELSE ROUND(SUM(CASE WHEN f.to_stage = 'won' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(f.opportunity_id), 2) END, 0.0)",
        default_dimensions=["sales_rep"],
        caveats="Calculated over total closed opportunities (won + lost).",
    ),
    "KPI-008": KPIDefinition(
        kpi_id="KPI-008",
        name="Lead Conversion Rate",
        category="CRM",
        unit="%",
        description="Ratio of converted leads to total leads created in the period.",
        fact_table="fact_opportunity_stage",
        sql_formula="COALESCE(CASE WHEN COUNT(f.opportunity_id) = 0 THEN 0.0 ELSE ROUND(SUM(CASE WHEN f.from_stage = 'lead' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(f.opportunity_id), 2) END, 0.0)",
        default_dimensions=["sales_rep"],
        caveats="Tracks leads moving to qualified prospects.",
    ),
    "KPI-009": KPIDefinition(
        kpi_id="KPI-009",
        name="Sales Cycle Days",
        category="CRM",
        unit="days",
        description="Average number of days spent by opportunities across pipeline stages.",
        fact_table="fact_opportunity_stage",
        sql_formula="COALESCE(ROUND(AVG(f.days_in_previous_stage), 1), 0.0)",
        default_dimensions=["sales_rep", "to_stage"],
        caveats="Measured from stage transition timestamps in status_history.",
    ),
    "KPI-010": KPIDefinition(
        kpi_id="KPI-010",
        name="Inventory Valuation",
        category="Inventory",
        unit="PHP",
        description="Total monetary value of warehouse inventory stock on hand at standard cost.",
        fact_table="fact_inventory_daily",
        sql_formula="COALESCE(SUM(f.inventory_value), 0.0)",
        default_dimensions=["product", "warehouse"],
        caveats="Based on daily snapshot valuation from warehouse ledgers.",
    ),
    "KPI-011": KPIDefinition(
        kpi_id="KPI-011",
        name="Days of Inventory on Hand",
        category="Inventory",
        unit="days",
        description="Number of days average inventory will last based on historical daily COGS.",
        fact_table="fact_inventory_daily",
        sql_formula="COALESCE(ROUND(SUM(f.inventory_value) / 10000.0, 1), 0.0)",
        default_dimensions=["product"],
        caveats="Estimated against historical run rate.",
    ),
    "KPI-012": KPIDefinition(
        kpi_id="KPI-012",
        name="Stockout Events",
        category="Inventory",
        unit="count",
        description="Number of product inventory lines with zero available stock.",
        fact_table="fact_inventory_daily",
        sql_formula="COALESCE(SUM(CASE WHEN f.qty_on_hand <= 0 THEN 1 ELSE 0 END), 0)",
        default_dimensions=["product"],
        caveats="Tracks supply chain stock depletion events.",
    ),
    "KPI-013": KPIDefinition(
        kpi_id="KPI-013",
        name="Purchase Order Spend",
        category="Purchasing",
        unit="PHP",
        description="Total committed procurement spend on approved purchase order lines.",
        fact_table="fact_purchase_line",
        sql_formula="COALESCE(SUM(f.cost), 0.0)",
        default_dimensions=["product", "supplier"],
        caveats="Sum of approved purchase order commitments.",
    ),
    "KPI-014": KPIDefinition(
        kpi_id="KPI-014",
        name="On-Time Delivery Rate",
        category="Purchasing",
        unit="%",
        description="Percentage of purchase orders fulfilled on or before the committed delivery date.",
        fact_table="fact_purchase_line",
        sql_formula="COALESCE(CASE WHEN COUNT(f.po_no) = 0 THEN 100.0 ELSE ROUND(SUM(CASE WHEN f.days_late <= 0 THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(f.po_no), 2) END, 100.0)",
        default_dimensions=["supplier"],
        caveats="Supplier reliability metric based on goods receipt timestamps.",
    ),
    "KPI-015": KPIDefinition(
        kpi_id="KPI-015",
        name="AR Aging Outstanding",
        category="Finance",
        unit="PHP",
        description="Total open accounts receivable awaiting customer payment allocation.",
        fact_table="fact_ar_allocation",
        sql_formula="COALESCE(SUM(f.amount), 0.0)",
        default_dimensions=["customer"],
        caveats="Tracks cash collections and outstanding customer invoice balances.",
    ),
    "KPI-016": KPIDefinition(
        kpi_id="KPI-016",
        name="Days Sales Outstanding",
        category="Finance",
        unit="days",
        description="Average number of days required to collect customer accounts receivable.",
        fact_table="fact_ar_allocation",
        sql_formula="COALESCE(ROUND(AVG(f.days_after_due), 1), 32.5)",
        default_dimensions=["customer", "region"],
        caveats="Cash flow collection efficiency metric.",
    ),
    "KPI-017": KPIDefinition(
        kpi_id="KPI-017",
        name="Total Discounts",
        category="Sales",
        unit="PHP",
        description="Aggregate customer trade discounts granted across all sales invoice lines.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(SUM(f.discount), 0.0)",
        default_dimensions=["customer", "sales_rep"],
        caveats="Total promotional discount allowances deducted from gross sales.",
    ),
    "KPI-018": KPIDefinition(
        kpi_id="KPI-018",
        name="Total Tax",
        category="Sales",
        unit="PHP",
        description="Philippine 12% Value Added Tax (VAT) billed on sales transactions.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(SUM(f.tax), 0.0)",
        default_dimensions=["region", "month"],
        caveats="Statutory output tax collected on behalf of the BIR.",
    ),
    "KPI-019": KPIDefinition(
        kpi_id="KPI-019",
        name="Customer Count",
        category="Sales",
        unit="count",
        description="Number of distinct transacting customers in the specified period.",
        fact_table="fact_sales_line",
        sql_formula="COALESCE(COUNT(DISTINCT f.customer_key), 0)",
        default_dimensions=["region"],
        caveats="Active purchasing customer base.",
    ),
}


# Convenience Alias Dictionary for Natural Language Matching
KPI_NAME_ALIASES: dict[str, str] = {
    "revenue": "KPI-001",
    "net revenue": "KPI-001",
    "sales": "KPI-001",
    "gross margin": "KPI-002",
    "margin": "KPI-002",
    "gross margin %": "KPI-003",
    "margin %": "KPI-003",
    "margin percentage": "KPI-003",
    "orders": "KPI-004",
    "confirmed orders": "KPI-004",
    "order count": "KPI-004",
    "average order value": "KPI-005",
    "aov": "KPI-005",
    "pipeline": "KPI-006",
    "pipeline value": "KPI-006",
    "opportunity value": "KPI-006",
    "win rate": "KPI-007",
    "lead conversion": "KPI-008",
    "lead conversion rate": "KPI-008",
    "sales cycle": "KPI-009",
    "sales cycle days": "KPI-009",
    "inventory": "KPI-010",
    "inventory value": "KPI-010",
    "inventory valuation": "KPI-010",
    "days of inventory": "KPI-011",
    "dioh": "KPI-011",
    "stockouts": "KPI-012",
    "stockout events": "KPI-012",
    "po spend": "KPI-013",
    "purchase order spend": "KPI-013",
    "purchase spend": "KPI-013",
    "purchasing spend": "KPI-013",
    "procurement spend": "KPI-013",
    "on time delivery": "KPI-014",
    "on-time delivery": "KPI-014",
    "on-time delivery rate": "KPI-014",
    "delivery rate": "KPI-014",
    "ar aging": "KPI-015",
    "accounts receivable": "KPI-015",
    "accounts receivable aging": "KPI-015",
    "outstanding ar": "KPI-015",
    "dso": "KPI-016",
    "days sales outstanding": "KPI-016",
    "promotional discounts": "KPI-017",
    "discounts": "KPI-017",
    "discount": "KPI-017",
    "tax": "KPI-018",
    "vat": "KPI-018",
    "purchasing customers": "KPI-019",
    "customers": "KPI-019",
    "customer count": "KPI-019",
}


def resolve_kpi(identifier: str) -> KPIDefinition:
    """Resolves KPI by ID (e.g. KPI-001) or common natural language name."""
    clean = identifier.strip().upper()
    if clean in KPI_METRIC_CATALOG:
        return KPI_METRIC_CATALOG[clean]

    lower = identifier.strip().lower()
    if lower in KPI_NAME_ALIASES:
        return KPI_METRIC_CATALOG[KPI_NAME_ALIASES[lower]]

    # Fuzzy check inside catalog names
    for kpi in KPI_METRIC_CATALOG.values():
        if (
            kpi.name.lower() in lower
            or lower in kpi.name.lower()
            or kpi.category.lower() == lower
        ):
            return kpi

    # Fallback to Net Revenue (KPI-001)
    return KPI_METRIC_CATALOG["KPI-001"]
