from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class KPICard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kpi_id: str
    kpi_name: str
    domain: str
    value: Decimal | float | int
    formatted_value: str
    unit: str | None = None
    comparison_value: Decimal | float | int | None = None
    change_pct: float | None = None
    trend: str | None = None  # "up" | "down" | "neutral"


class ExecutiveSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of_date: date
    period_start: date
    period_end: date
    scorecards: list[KPICard]


class RevenueMarginMonthlyPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str  # YYYY-MM
    gross_invoiced: Decimal
    credit_notes: Decimal
    net_revenue: Decimal  # KPI-001
    cogs: Decimal
    gross_margin: Decimal  # KPI-002
    gross_margin_pct: Decimal  # KPI-003
    invoice_count: int


class RevenueReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_start: date
    period_end: date
    net_revenue: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal
    total_invoices: int
    total_credit_notes: int
    trend: list[RevenueMarginMonthlyPoint]


class ARAgingBucket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket: str  # "current" | "1-30" | "31-60" | "61-90" | "90+"
    label: str
    amount: Decimal
    count: int
    percentage: Decimal


class ARAgingCustomerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_no: str
    customer_name: str
    total_balance: Decimal
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_90_plus: Decimal


class ARAgingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of_date: date
    total_outstanding: Decimal  # KPI-005
    buckets: list[ARAgingBucket]  # KPI-006
    customers: list[ARAgingCustomerRow]
    dso_days: Decimal | None = None  # KPI-018


class PipelineStageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    label: str
    count: int
    nominal_amount: Decimal
    weighted_amount: Decimal


class PipelineReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of_date: date
    period_start: date
    period_end: date
    total_open_opportunities: int
    total_open_amount: Decimal
    weighted_pipeline: Decimal  # KPI-007
    win_rate_pct: Decimal  # KPI-008
    lead_conversion_pct: Decimal  # KPI-009
    avg_sales_cycle_days: Decimal  # KPI-010
    stages: list[PipelineStageSummary]


class LowStockItemRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    sku: str
    name: str
    uom: str
    qty_on_hand: Decimal
    qty_reserved: Decimal
    qty_available: Decimal
    reorder_point: Decimal
    deficit: Decimal


class WarehouseInventorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    total_value: Decimal
    sku_count: int


class InventoryReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of_date: date
    total_inventory_value: Decimal  # KPI-013
    low_stock_count: int  # KPI-015
    warehouses: list[WarehouseInventorySummary]
    low_stock_items: list[LowStockItemRow]


class SupplierSpendRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: int
    supplier_no: str
    supplier_name: str
    spend: Decimal
    bill_count: int
    on_time_rate_pct: Decimal | None = None


class ProcurementReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_start: date
    period_end: date
    total_purchase_spend: Decimal  # KPI-016
    overall_on_time_rate_pct: Decimal  # KPI-017
    suppliers: list[SupplierSpendRow]
