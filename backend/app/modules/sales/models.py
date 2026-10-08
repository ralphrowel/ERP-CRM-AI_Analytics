from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin

if TYPE_CHECKING:
    from app.modules.catalog.models import Product
    from app.modules.crm.models import Contact, Customer, Opportunity


class TaxRate(Base, AuditMixin):
    __tablename__ = "tax_rates"
    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate < 1", name="ck_tax_rates_rate_valid"),
        Index("uq_tax_rates_single_default", "is_default", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.1200"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="tax_rate")


class Quote(Base, AuditMixin, VersionMixin):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'rejected', 'expired', 'cancelled')",
            name="ck_quotes_status",
        ),
        CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_quotes_grand_total_matches",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    quote_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Header totals (Roadmap §4.3)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="PHP")
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer")
    opportunity: Mapped["Opportunity | None"] = relationship("Opportunity")
    contact: Mapped["Contact | None"] = relationship("Contact")
    items: Mapped[list["QuoteItem"]] = relationship(
        "QuoteItem", back_populates="quote", cascade="all, delete-orphan", order_by="QuoteItem.line_no"
    )


class QuoteItem(Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quote_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_quote_items_unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_quote_items_discount_non_negative"),
        CheckConstraint("line_total = line_net + line_tax", name="ck_quote_items_total_matches"),
        Index("uq_quote_items_line", "quote_id", "line_no", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Snapshots per Roadmap §4.3 & §V0.3 Rule 1
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    tax_rate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tax_rates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    # Computed fields
    line_net: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)

    quote: Mapped["Quote"] = relationship("Quote", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")
    tax_rate_ref: Mapped["TaxRate"] = relationship("TaxRate")


class SalesOrder(Base, AuditMixin, VersionMixin):
    __tablename__ = "sales_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'on_hold', 'partially_shipped', 'shipped', 'completed', 'cancelled')",
            name="ck_sales_orders_status",
        ),
        CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_sales_orders_grand_total_matches",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quote_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Snapshots taken at confirmation (Roadmap Rule 6)
    billing_address_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shipping_address_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payment_terms_days_snapshot: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Header totals (Roadmap §4.3)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="PHP")
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    tax_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer")
    quote: Mapped["Quote | None"] = relationship("Quote")
    contact: Mapped["Contact | None"] = relationship("Contact")
    items: Mapped[list["SalesOrderItem"]] = relationship(
        "SalesOrderItem", back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderItem.line_no"
    )


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_so_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_so_items_unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_so_items_discount_non_negative"),
        CheckConstraint("line_total = line_net + line_tax", name="ck_so_items_total_matches"),
        CheckConstraint(
            "quantity_invoiced >= 0 AND quantity_invoiced <= quantity",
            name="ck_so_items_quantity_invoiced_valid",
        ),
        CheckConstraint(
            "quantity_shipped >= 0 AND quantity_shipped <= quantity",
            name="ck_so_items_quantity_shipped_valid",
        ),
        Index("uq_sales_order_items_line", "sales_order_id", "line_no", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Snapshots
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    tax_rate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tax_rates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    # Computed fields
    line_net: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)

    # Invoiced / Shipped tracking for completion checks
    quantity_invoiced: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    quantity_shipped: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )

    order: Mapped["SalesOrder"] = relationship("SalesOrder", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")
    tax_rate_ref: Mapped["TaxRate"] = relationship("TaxRate")
