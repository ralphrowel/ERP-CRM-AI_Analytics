"""
SQLAlchemy Models for Analytical Data Mart - Star Schema (Roadmap §V1.4)
Defines conformed dimensions (dim_*) with SCD Type 2 for dim_customer,
and fact tables (fact_*) with declared grain and surrogate keys.
Schema: mart
"""

from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from analytics.extract.models import Base

# =========================================================================
# Conformed Dimensions
# =========================================================================


class DimDate(Base):
    """
    Date Dimension (Asia/Manila, calendar = fiscal).
    Schema: mart.dim_date
    """

    __tablename__ = "dim_date"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    date_key: Mapped[int] = mapped_column(Integer, primary_key=True)  # YYYYMMDD
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    month_name: Mapped[str] = mapped_column(String(20), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 1=Monday .. 7=Sunday
    day_name: Mapped[str] = mapped_column(String(20), nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(Integer, nullable=False)


class DimSourceSystem(Base):
    """
    Source System Dimension (ERP vs Legacy).
    Schema: mart.dim_source_system
    """

    __tablename__ = "dim_source_system"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    source_system_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )  # 'erp', 'legacy'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class DimCustomer(Base):
    """
    Customer Dimension with SCD Type 2 history tracking.
    Surrogate key customer_key is separate from natural keys customer_id and customer_no.
    Schema: mart.dim_customer
    """

    __tablename__ = "dim_customer"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    customer_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    customer_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    legacy_customer_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str] = mapped_column(
        String(100), default="Luzon", nullable=False
    )  # Luzon, Visayas, Mindanao, NCR
    credit_limit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # SCD Type 2 attributes
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DimProduct(Base):
    """
    Product Dimension.
    Schema: mart.dim_product
    """

    __tablename__ = "dim_product"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    product_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    standard_cost: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0.0, nullable=False
    )
    list_price: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0.0, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DimEmployee(Base):
    """
    Employee Dimension (Sales reps, managers).
    Schema: mart.dim_employee
    """

    __tablename__ = "dim_employee"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    employee_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    employee_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DimWarehouse(Base):
    """
    Warehouse Dimension.
    Schema: mart.dim_warehouse
    """

    __tablename__ = "dim_warehouse"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    warehouse_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    warehouse_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DimSupplier(Base):
    """
    Supplier Dimension.
    Schema: mart.dim_supplier
    """

    __tablename__ = "dim_supplier"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    supplier_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    supplier_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# =========================================================================
# Facts (Declared Grain)
# =========================================================================


class FactSalesLine(Base):
    """
    Sales Line Fact.
    Grain: One row per invoice line OR credit-note line (negative) OR legacy sale line.
    Key measures: quantity, gross, discount, net_revenue, tax, cogs, gross_margin.
    Degenerate dimensions: invoice_no, credit_note_no, document_type, source_system.
    Schema: mart.fact_sales_line
    """

    __tablename__ = "fact_sales_line"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    sales_line_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    # Foreign Keys to Dimensions
    date_key: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_key: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )  # SCD Type 2 key valid at document date
    product_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    employee_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_system_key: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )

    # Degenerate Dimensions
    invoice_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    credit_note_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    document_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'invoice', 'credit_note', 'legacy_sale'
    source_system: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'erp', 'legacy'
    line_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Measures
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    gross: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    net_revenue: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    cogs: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    gross_margin: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)


class FactOpportunityStage(Base):
    """
    Opportunity Stage Transitions Fact.
    Grain: One row per opportunity stage transition (from status_history).
    Key measures: days_in_previous_stage, estimated_amount.
    Schema: mart.fact_opportunity_stage
    """

    __tablename__ = "fact_opportunity_stage"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    opportunity_stage_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    opportunity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    transition_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date_key: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    employee_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    from_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    days_in_previous_stage: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    estimated_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0.0, nullable=False
    )


class FactInventoryDaily(Base):
    """
    Daily Inventory Snapshot Fact.
    Grain: One row per product x warehouse x day.
    Key measures: qty_on_hand, qty_reserved, inventory_value.
    Schema: mart.fact_inventory_daily
    """

    __tablename__ = "fact_inventory_daily"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    inventory_snapshot_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    date_key: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    product_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    warehouse_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    qty_on_hand: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, nullable=False
    )
    qty_reserved: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, nullable=False
    )
    inventory_value: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0.0, nullable=False
    )


class FactPurchaseLine(Base):
    """
    Purchase Order Line Fact.
    Grain: One row per purchase order line.
    Key measures: qty_ordered, qty_received, cost, days_late.
    Schema: mart.fact_purchase_line
    """

    __tablename__ = "fact_purchase_line"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    purchase_line_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    date_key: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    supplier_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    product_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    po_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    qty_received: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, nullable=False
    )
    cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    days_late: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class FactArAllocation(Base):
    """
    Accounts Receivable Payment Allocation Fact.
    Grain: One row per payment allocation.
    Key measures: amount, days_after_due.
    Schema: mart.fact_ar_allocation
    """

    __tablename__ = "fact_ar_allocation"
    __table_args__: ClassVar[dict[str, Any]] = {"schema": "mart"}

    ar_allocation_key: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    customer_key: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    payment_date_key: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    payment_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    invoice_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    allocation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    days_after_due: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
