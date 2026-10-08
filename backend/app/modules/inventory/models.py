from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin

if TYPE_CHECKING:
    from app.modules.catalog.models import Product
    from app.modules.identity.models import User
    from app.modules.sales.models import SalesOrderItem


class Warehouse(Base, AuditMixin, VersionMixin):
    __tablename__ = "warehouses"
    __table_args__ = (
        Index(
            "uq_warehouses_single_default",
            "is_default",
            unique=True,
            postgresql_where=func.coalesce("is_default", False),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    balances: Mapped[list["InventoryBalance"]] = relationship(
        "InventoryBalance", back_populates="warehouse", cascade="all, delete-orphan"
    )


class InventoryBalance(Base):
    """
    Inventory state cache per (product, warehouse).
    Updated in the exact same database transaction as the corresponding inventory transaction ledger row.
    """

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint("qty_on_hand >= 0", name="ck_inv_balances_on_hand_non_negative"),
        CheckConstraint(
            "qty_reserved >= 0 AND qty_reserved <= qty_on_hand",
            name="ck_inv_balances_reserved_valid",
        ),
        CheckConstraint("avg_unit_cost >= 0", name="ck_inv_balances_cost_non_negative"),
        Index("ix_inventory_balances_warehouse", "warehouse_id"),
    )

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), primary_key=True
    )
    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000"), server_default="0.000"
    )
    qty_reserved: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000"), server_default="0.000"
    )
    avg_unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0.0000"), server_default="0.0000"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="balances")

    @property
    def qty_available(self) -> Decimal:
        return self.qty_on_hand - self.qty_reserved


class InventoryTransaction(Base):
    """
    Append-only inventory movement ledger.
    Every stock movement writes here first, maintaining running balances and unit cost tracking.
    """

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="ck_inv_txn_quantity_nonzero"),
        CheckConstraint("unit_cost >= 0", name="ck_inv_txn_unit_cost_non_negative"),
        CheckConstraint(
            "txn_type IN ('opening', 'receipt', 'issue', 'adjustment_in', 'adjustment_out', 'transfer_in', 'transfer_out')",
            name="ck_inv_txn_type",
        ),
        CheckConstraint(
            "source_type IN ('opening', 'shipment', 'goods_receipt', 'stock_adjustment', 'stock_transfer')",
            name="ck_inv_txn_source_type",
        ),
        Index(
            "ix_inventory_txns_lookup",
            "product_id",
            "warehouse_id",
            "occurred_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    txn_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    qty_on_hand_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    avg_cost_after: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_line_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    user: Mapped["User | None"] = relationship("User")


class StockReservation(Base):
    """
    Tracks inventory reserved for confirmed sales order items.
    Prevents overselling during the gap between order confirmation and physical shipment.
    """

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservations_quantity_positive"),
        CheckConstraint(
            "quantity_consumed >= 0 AND quantity_consumed <= quantity",
            name="ck_reservations_consumed_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'consumed', 'released')",
            name="ck_reservations_status",
        ),
        Index("ix_stock_reservations_item", "sales_order_item_id"),
        Index("ix_stock_reservations_pw", "product_id", "warehouse_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales_order_items.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_consumed: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000"), server_default="0.000"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    sales_order_item: Mapped["SalesOrderItem"] = relationship("SalesOrderItem")
    product: Mapped["Product"] = relationship("Product")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
