from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin

if TYPE_CHECKING:
    from app.modules.catalog.models import Product
    from app.modules.inventory.models import Warehouse
    from app.modules.sales.models import TaxRate


class Supplier(Base, AuditMixin, VersionMixin):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("payment_terms_days >= 0", name="ck_suppliers_payment_terms_days"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    supplier_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(
        SmallInteger, server_default="30", default=30, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", default=True, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    products: Mapped[list["SupplierProduct"]] = relationship(
        "SupplierProduct", back_populates="supplier", cascade="all, delete-orphan"
    )
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder", back_populates="supplier"
    )


class SupplierProduct(Base, AuditMixin):
    __tablename__ = "supplier_products"
    __table_args__ = (
        CheckConstraint(
            "last_unit_cost IS NULL OR last_unit_cost >= 0",
            name="ck_supplier_products_last_unit_cost",
        ),
        CheckConstraint(
            "lead_time_days IS NULL OR lead_time_days >= 0",
            name="ck_supplier_products_lead_time_days",
        ),
    )

    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_preferred: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="products")
    product: Mapped["Product"] = relationship("Product")


class PurchaseOrder(Base, AuditMixin, VersionMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'sent', 'partially_received', 'received', 'closed', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        CheckConstraint("subtotal >= 0", name="ck_purchase_orders_subtotal_non_negative"),
        CheckConstraint("tax_total >= 0", name="ck_purchase_orders_tax_total_non_negative"),
        CheckConstraint("grand_total >= 0", name="ck_purchase_orders_grand_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    po_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), server_default="draft", default="draft", nullable=False, index=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms_days_snapshot: Mapped[int] = mapped_column(
        SmallInteger, server_default="30", default=30, nullable=False
    )
    supplier_address_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    warehouse_address_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), server_default="0", default=Decimal("0"), nullable=False
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), server_default="0", default=Decimal("0"), nullable=False
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), server_default="0", default=Decimal("0"), nullable=False
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderItem.line_no",
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_order_items_qty_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_order_items_unit_cost_non_negative"),
        CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity",
            name="ck_purchase_order_items_qty_received_bounds",
        ),
        CheckConstraint(
            "quantity_billed >= 0",
            name="ck_purchase_order_items_qty_billed_non_negative",
        ),
        UniqueConstraint("purchase_order_id", "line_no", name="uq_po_items_po_line_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uom: Mapped[str] = mapped_column(
        String(50), server_default="UNIT", default="UNIT", nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    tax_rate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tax_rates.id", ondelete="RESTRICT"), nullable=False
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    line_net: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), server_default="0", default=Decimal("0"), nullable=False
    )
    quantity_billed: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), server_default="0", default=Decimal("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product")
    tax_rate_rel: Mapped["TaxRate"] = relationship("TaxRate")
