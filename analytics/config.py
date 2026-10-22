"""
Analytics Platform Configuration (Roadmap §V1.1)
Defines connection URLs for ETL reader and Analytics database, schema registries,
and extraction window policies.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AnalyticsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Operational ERP database (read-only for ETL)
    ETL_READER_DATABASE_URL: str = (
        "postgresql+psycopg://etl_reader:etl_reader_password@localhost:5432/erp_crm"
    )
    # Target Analytics Database
    ANALYTICS_DATABASE_URL: str = "postgresql+psycopg://analytics_owner:analytics_owner_password@localhost:5432/erp_analytics"

    # Overlap window in minutes to catch long-running/concurrent transactions (default: 10 min)
    ETL_OVERLAP_MINUTES: int = 10

    # Analytics Database Schemas (Roadmap §V1.1 - §V1.5)
    SCHEMAS: list[str] = ["raw", "staging", "dq", "mart", "etl"]

    # Small reference tables (full extract on every run)
    REFERENCE_TABLES: list[str] = [
        "tax_rates",
        "departments",
        "warehouses",
        "currencies",
    ]

    # Core operational tables (extracted incrementally by updated_at / timestamp)
    INCREMENTAL_TABLES: list[str] = [
        "customers",
        "contacts",
        "leads",
        "opportunities",
        "products",
        "quotes",
        "quote_lines",
        "quote_items",
        "sales_orders",
        "sales_order_lines",
        "sales_order_items",
        "invoices",
        "invoice_lines",
        "invoice_items",
        "payments",
        "shipments",
        "shipment_lines",
        "suppliers",
        "supplier_products",
        "purchase_orders",
        "purchase_order_lines",
        "purchase_order_items",
        "goods_receipts",
        "goods_receipt_lines",
        "goods_receipt_items",
        "supplier_invoices",
        "supplier_invoice_lines",
        "supplier_payments",
        "inventory_ledger",
        "audit_log",
        "status_history",
        "approval_requests",
        "users",
        "accounts",
        "fiscal_periods",
        "journal_entries",
        "journal_entry_lines",
        "fx_rates",
        "stock_transfers",
        "stock_transfer_items",
        "warehouse_reorder_policies",
    ]

    # Paths to Legacy Datasets
    @property
    def legacy_customers_csv_path(self) -> Path:
        root = Path(__file__).resolve().parent.parent
        return root / "backend" / "data" / "legacy" / "legacy_customers.csv"

    @property
    def legacy_sales_csv_path(self) -> Path:
        root = Path(__file__).resolve().parent.parent
        return root / "backend" / "data" / "legacy" / "legacy_sales_2023_2025.csv"

    @property
    def defect_manifest_path(self) -> Path:
        root = Path(__file__).resolve().parent.parent
        return root / "backend" / "data" / "legacy" / "defect_manifest.json"


analytics_settings = AnalyticsSettings()
