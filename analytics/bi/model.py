"""
Power BI Semantic Model & Tabular Metadata Specification (Roadmap §V1.5)
Defines star schema relationships, dimensional hierarchies, measure containers,
and TMDL (Tabular Model Definition Language) generation.
"""

import json
from dataclasses import dataclass
from typing import Any

from analytics.bi.dax import get_kpi_dax_catalog


@dataclass
class ModelColumn:
    name: str
    data_type: str
    is_hidden: bool = False
    format_string: str | None = None
    description: str | None = None


@dataclass
class ModelTable:
    name: str
    schema_name: str
    is_fact: bool
    columns: list[ModelColumn]
    description: str = ""


@dataclass
class ModelRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str = "manyToOne"
    cross_filter_direction: str = "single"
    is_active: bool = True


class SemanticModel:
    """Manages full Power BI tabular semantic model definition over mart schema."""

    def __init__(self):
        self.tables: list[ModelTable] = self._build_tables()
        self.relationships: list[ModelRelationship] = self._build_relationships()
        self.measures = get_kpi_dax_catalog()

    def _build_tables(self) -> list[ModelTable]:
        return [
            # 1. Dimensions
            ModelTable(
                name="dim_date",
                schema_name="mart",
                is_fact=False,
                description="Conformed calendar and fiscal date dimension (Asia/Manila, 2023-2026).",
                columns=[
                    ModelColumn("date_key", "int64", is_hidden=False),
                    ModelColumn("date", "dateTime", format_string="yyyy-MM-dd"),
                    ModelColumn("year", "int64"),
                    ModelColumn("quarter", "int64"),
                    ModelColumn("month", "int64"),
                    ModelColumn("month_name", "string"),
                    ModelColumn("day", "int64"),
                    ModelColumn("day_of_week", "int64"),
                    ModelColumn("day_name", "string"),
                    ModelColumn("is_weekend", "boolean"),
                    ModelColumn("fiscal_year", "int64"),
                    ModelColumn("fiscal_quarter", "int64"),
                ],
            ),
            ModelTable(
                name="dim_customer",
                schema_name="mart",
                is_fact=False,
                description="Conformed customer master with Slowly Changing Dimension Type 2 validity intervals.",
                columns=[
                    ModelColumn("customer_key", "int64", is_hidden=False),
                    ModelColumn("customer_id", "int64", is_hidden=True),
                    ModelColumn("customer_no", "string"),
                    ModelColumn("legacy_customer_id", "string", is_hidden=True),
                    ModelColumn("name", "string"),
                    ModelColumn("customer_type", "string"),
                    ModelColumn("industry", "string"),
                    ModelColumn("city", "string"),
                    ModelColumn("province", "string"),
                    ModelColumn("region", "string"),
                    ModelColumn("credit_limit", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("valid_from", "dateTime", is_hidden=True),
                    ModelColumn("valid_to", "dateTime", is_hidden=True),
                    ModelColumn("is_current", "int64"),
                ],
            ),
            ModelTable(
                name="dim_product",
                schema_name="mart",
                is_fact=False,
                description="Conformed item catalog and standard costing dimension.",
                columns=[
                    ModelColumn("product_key", "int64", is_hidden=False),
                    ModelColumn("product_id", "int64", is_hidden=True),
                    ModelColumn("sku", "string"),
                    ModelColumn("name", "string"),
                    ModelColumn("category", "string"),
                    ModelColumn("unit_of_measure", "string"),
                    ModelColumn("standard_cost", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("list_price", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("is_active", "boolean"),
                ],
            ),
            ModelTable(
                name="dim_employee",
                schema_name="mart",
                is_fact=False,
                description="Conformed workforce and sales representative dimension.",
                columns=[
                    ModelColumn("employee_key", "int64", is_hidden=False),
                    ModelColumn("employee_id", "int64", is_hidden=True),
                    ModelColumn("employee_no", "string"),
                    ModelColumn("full_name", "string"),
                    ModelColumn("email", "string"),
                    ModelColumn("department_code", "string"),
                    ModelColumn("department_name", "string"),
                    ModelColumn("role", "string"),
                    ModelColumn("is_active", "boolean"),
                ],
            ),
            ModelTable(
                name="dim_source_system",
                schema_name="mart",
                is_fact=False,
                description="Conformed source lineage tracking upstream transactional engines.",
                columns=[
                    ModelColumn("source_system_key", "int64", is_hidden=False),
                    ModelColumn("code", "string"),
                    ModelColumn("name", "string"),
                    ModelColumn("description", "string"),
                ],
            ),
            ModelTable(
                name="dim_warehouse",
                schema_name="mart",
                is_fact=False,
                description="Conformed storage warehouse location dimension.",
                columns=[
                    ModelColumn("warehouse_key", "int64", is_hidden=False),
                    ModelColumn("warehouse_id", "int64", is_hidden=True),
                    ModelColumn("code", "string"),
                    ModelColumn("name", "string"),
                    ModelColumn("is_active", "boolean"),
                ],
            ),
            ModelTable(
                name="dim_supplier",
                schema_name="mart",
                is_fact=False,
                description="Conformed procurement vendor and payment terms dimension.",
                columns=[
                    ModelColumn("supplier_key", "int64", is_hidden=False),
                    ModelColumn("supplier_id", "int64", is_hidden=True),
                    ModelColumn("supplier_no", "string"),
                    ModelColumn("name", "string"),
                    ModelColumn("email", "string"),
                    ModelColumn("payment_terms_days", "int64"),
                    ModelColumn("is_active", "boolean"),
                ],
            ),
            # 2. Fact Tables
            ModelTable(
                name="fact_sales_line",
                schema_name="mart",
                is_fact=True,
                description="Sales line transactional fact: invoices, credit notes, and legacy sales items.",
                columns=[
                    ModelColumn("sales_fact_key", "int64", is_hidden=True),
                    ModelColumn("date_key", "int64", is_hidden=True),
                    ModelColumn("customer_key", "int64", is_hidden=True),
                    ModelColumn("product_key", "int64", is_hidden=True),
                    ModelColumn("employee_key", "int64", is_hidden=True),
                    ModelColumn("source_system_key", "int64", is_hidden=True),
                    ModelColumn("invoice_no", "string"),
                    ModelColumn("credit_note_no", "string"),
                    ModelColumn("document_type", "string"),
                    ModelColumn("source_system", "string"),
                    ModelColumn("line_number", "int64"),
                    ModelColumn("quantity", "decimal", format_string="#,##0.00"),
                    ModelColumn("unit_price", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("gross", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("discount", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("net_revenue", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("tax", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("cogs", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("gross_margin", "decimal", format_string="₱#,##0.00"),
                ],
            ),
            ModelTable(
                name="fact_opportunity_stage",
                schema_name="mart",
                is_fact=True,
                description="CRM pipeline conversion and stage duration tracking fact.",
                columns=[
                    ModelColumn("stage_fact_key", "int64", is_hidden=True),
                    ModelColumn("opportunity_id", "int64"),
                    ModelColumn("transition_id", "int64"),
                    ModelColumn("date_key", "int64", is_hidden=True),
                    ModelColumn("customer_key", "int64", is_hidden=True),
                    ModelColumn("employee_key", "int64", is_hidden=True),
                    ModelColumn("from_stage", "string"),
                    ModelColumn("to_stage", "string"),
                    ModelColumn("days_in_previous_stage", "int64"),
                    ModelColumn(
                        "estimated_amount", "decimal", format_string="₱#,##0.00"
                    ),
                ],
            ),
            ModelTable(
                name="fact_inventory_daily",
                schema_name="mart",
                is_fact=True,
                description="Daily snapshot of stock on hand, reservations, and inventory valuation.",
                columns=[
                    ModelColumn("inventory_fact_key", "int64", is_hidden=True),
                    ModelColumn("date_key", "int64", is_hidden=True),
                    ModelColumn("product_key", "int64", is_hidden=True),
                    ModelColumn("warehouse_key", "int64", is_hidden=True),
                    ModelColumn("qty_on_hand", "decimal", format_string="#,##0.00"),
                    ModelColumn("qty_reserved", "decimal", format_string="#,##0.00"),
                    ModelColumn(
                        "inventory_value", "decimal", format_string="₱#,##0.00"
                    ),
                ],
            ),
            ModelTable(
                name="fact_purchase_line",
                schema_name="mart",
                is_fact=True,
                description="Procurement purchase order lines and delivery punctuality fact.",
                columns=[
                    ModelColumn("purchase_fact_key", "int64", is_hidden=True),
                    ModelColumn("date_key", "int64", is_hidden=True),
                    ModelColumn("supplier_key", "int64", is_hidden=True),
                    ModelColumn("product_key", "int64", is_hidden=True),
                    ModelColumn("po_no", "string"),
                    ModelColumn("line_number", "int64"),
                    ModelColumn("qty_ordered", "decimal", format_string="#,##0.00"),
                    ModelColumn("qty_received", "decimal", format_string="#,##0.00"),
                    ModelColumn("unit_cost", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("cost", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("days_late", "int64"),
                ],
            ),
            ModelTable(
                name="fact_ar_allocation",
                schema_name="mart",
                is_fact=True,
                description="Accounts receivable payment allocations and delinquency tracking fact.",
                columns=[
                    ModelColumn("ar_fact_key", "int64", is_hidden=True),
                    ModelColumn("customer_key", "int64", is_hidden=True),
                    ModelColumn("payment_date_key", "int64", is_hidden=True),
                    ModelColumn("payment_no", "string"),
                    ModelColumn("invoice_no", "string"),
                    ModelColumn("allocation_id", "int64"),
                    ModelColumn("payment_method", "string"),
                    ModelColumn("amount", "decimal", format_string="₱#,##0.00"),
                    ModelColumn("days_after_due", "int64"),
                ],
            ),
        ]

    def _build_relationships(self) -> list[ModelRelationship]:
        return [
            # fact_sales_line relationships
            ModelRelationship("fact_sales_line", "date_key", "dim_date", "date_key"),
            ModelRelationship(
                "fact_sales_line", "customer_key", "dim_customer", "customer_key"
            ),
            ModelRelationship(
                "fact_sales_line", "product_key", "dim_product", "product_key"
            ),
            ModelRelationship(
                "fact_sales_line", "employee_key", "dim_employee", "employee_key"
            ),
            ModelRelationship(
                "fact_sales_line",
                "source_system_key",
                "dim_source_system",
                "source_system_key",
            ),
            # fact_opportunity_stage relationships
            ModelRelationship(
                "fact_opportunity_stage", "date_key", "dim_date", "date_key"
            ),
            ModelRelationship(
                "fact_opportunity_stage", "customer_key", "dim_customer", "customer_key"
            ),
            ModelRelationship(
                "fact_opportunity_stage", "employee_key", "dim_employee", "employee_key"
            ),
            # fact_inventory_daily relationships
            ModelRelationship(
                "fact_inventory_daily", "date_key", "dim_date", "date_key"
            ),
            ModelRelationship(
                "fact_inventory_daily", "product_key", "dim_product", "product_key"
            ),
            ModelRelationship(
                "fact_inventory_daily",
                "warehouse_key",
                "dim_warehouse",
                "warehouse_key",
            ),
            # fact_purchase_line relationships
            ModelRelationship("fact_purchase_line", "date_key", "dim_date", "date_key"),
            ModelRelationship(
                "fact_purchase_line", "supplier_key", "dim_supplier", "supplier_key"
            ),
            ModelRelationship(
                "fact_purchase_line", "product_key", "dim_product", "product_key"
            ),
            # fact_ar_allocation relationships
            ModelRelationship(
                "fact_ar_allocation", "payment_date_key", "dim_date", "date_key"
            ),
            ModelRelationship(
                "fact_ar_allocation", "customer_key", "dim_customer", "customer_key"
            ),
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serializes the entire semantic model into JSON-compliant dictionary."""
        return {
            "name": "ERP_CRM_Analytical_Mart",
            "compatibility_level": 1600,
            "mode": "Import",
            "source_database": "PostgreSQL",
            "target_schema": "mart",
            "tables": [
                {
                    "name": t.name,
                    "schema": t.schema_name,
                    "is_fact": t.is_fact,
                    "description": t.description,
                    "columns": [
                        {
                            "name": c.name,
                            "dataType": c.data_type,
                            "isHidden": c.is_hidden,
                            "formatString": c.format_string,
                            "description": c.description,
                        }
                        for c in t.columns
                    ],
                }
                for t in self.tables
            ],
            "relationships": [
                {
                    "fromTable": r.from_table,
                    "fromColumn": r.from_column,
                    "toTable": r.to_table,
                    "toColumn": r.to_column,
                    "cardinality": r.cardinality,
                    "crossFilterDirection": r.cross_filter_direction,
                    "isActive": r.is_active,
                }
                for r in self.relationships
            ],
            "measures": [m.to_dict() for m in self.measures],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes semantic model to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_tmdl(self) -> str:
        """
        Generates modern Tabular Model Definition Language (TMDL) format
        supported by Power BI Desktop Developer Mode and Git integration.
        """
        lines = [
            "model Model",
            "\tcompatibilityLevel: 1600",
            "\tculture: en-US",
            "",
        ]

        for t in self.tables:
            lines.append(f"table {t.name}")
            if t.description:
                lines.append(f"\t/// {t.description}")
            for c in t.columns:
                lines.append(f"\tcolumn {c.name}")
                lines.append(f"\t\tdataType: {c.data_type}")
                if c.is_hidden:
                    lines.append("\t\tisHidden")
                if c.format_string:
                    lines.append(f'\t\tformatString: "{c.format_string}"')
                lines.append("")

            # Attach measures
            table_measures = [m for m in self.measures if m.table == t.name]
            for m in table_measures:
                lines.append(f"\tmeasure '{m.name}' = {m.expression}")
                if m.format_string:
                    lines.append(f'\t\tformatString: "{m.format_string}"')
                lines.append("")
                for suffix, t_expr in m.time_intelligence.items():
                    lines.append(f"\tmeasure '{m.name} {suffix}' = {t_expr}")
                    if m.format_string:
                        lines.append(f'\t\tformatString: "{m.format_string}"')
                    lines.append("")

        for r in self.relationships:
            lines.append(f"relationship {r.from_table}_{r.from_column}_to_{r.to_table}")
            lines.append(f"\tfromColumn: {r.from_table}.{r.from_column}")
            lines.append(f"\ttoColumn: {r.to_table}.{r.to_column}")
            lines.append(f"\tcrossFilteringBehavior: {r.cross_filter_direction}")
            lines.append("")

        return "\n".join(lines)
