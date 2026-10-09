"""V0.5a schema: Purchasing Core (Suppliers, Supplier Products, Purchase Orders)

Revision ID: 0007_purchasing_suppliers_po
Revises: 0006_fulfillment_costing
Create Date: 2026-10-09 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_purchasing_suppliers_po"
down_revision: str | None = "0006_fulfillment_costing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add bill_price_tolerance_pct to company_settings
    op.add_column(
        "company_settings",
        sa.Column(
            "bill_price_tolerance_pct",
            sa.Numeric(precision=6, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
    )

    # 2. suppliers table
    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("supplier_no", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tin", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("payment_terms_days", sa.SmallInteger(), server_default="30", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("payment_terms_days >= 0", name="ck_suppliers_payment_terms_days"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_no"),
    )
    op.create_index("ix_suppliers_supplier_no", "suppliers", ["supplier_no"])
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    # 3. supplier_products join table
    op.create_table(
        "supplier_products",
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_sku", sa.String(length=100), nullable=True),
        sa.Column("last_unit_cost", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("lead_time_days", sa.SmallInteger(), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "last_unit_cost IS NULL OR last_unit_cost >= 0",
            name="ck_supplier_products_last_unit_cost",
        ),
        sa.CheckConstraint(
            "lead_time_days IS NULL OR lead_time_days >= 0",
            name="ck_supplier_products_lead_time_days",
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("supplier_id", "product_id"),
    )
    op.create_index("ix_supplier_products_supplier_id", "supplier_products", ["supplier_id"])
    op.create_index("ix_supplier_products_product_id", "supplier_products", ["product_id"])

    # 4. purchase_orders table
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("po_no", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="draft", nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "payment_terms_days_snapshot", sa.SmallInteger(), server_default="30", nullable=False
        ),
        sa.Column("supplier_address_snapshot", sa.Text(), nullable=True),
        sa.Column("warehouse_address_snapshot", sa.Text(), nullable=True),
        sa.Column(
            "subtotal", sa.Numeric(precision=19, scale=4), server_default="0", nullable=False
        ),
        sa.Column(
            "tax_total", sa.Numeric(precision=19, scale=4), server_default="0", nullable=False
        ),
        sa.Column(
            "grand_total", sa.Numeric(precision=19, scale=4), server_default="0", nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'sent', 'partially_received', 'received', 'closed', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        sa.CheckConstraint("subtotal >= 0", name="ck_purchase_orders_subtotal_non_negative"),
        sa.CheckConstraint("tax_total >= 0", name="ck_purchase_orders_tax_total_non_negative"),
        sa.CheckConstraint("grand_total >= 0", name="ck_purchase_orders_grand_total_non_negative"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_no"),
    )
    op.create_index("ix_purchase_orders_po_no", "purchase_orders", ["po_no"])
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_warehouse_id", "purchase_orders", ["warehouse_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])

    # 5. purchase_order_items table
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("uom", sa.String(length=50), server_default="UNIT", nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("tax_rate_id", sa.BigInteger(), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("line_tax", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column(
            "quantity_received",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "quantity_billed",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_items_qty_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchase_order_items_unit_cost_non_negative"),
        sa.CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity",
            name="ck_purchase_order_items_qty_received_bounds",
        ),
        sa.CheckConstraint(
            "quantity_billed >= 0",
            name="ck_purchase_order_items_qty_billed_non_negative",
        ),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_order_id", "line_no", name="uq_po_items_po_line_no"),
    )
    op.create_index("ix_purchase_order_items_po_id", "purchase_order_items", ["purchase_order_id"])
    op.create_index("ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"])

    # 6. Seed document sequence records for supplier and purchase_order
    op.execute(
        """
        INSERT INTO document_sequences (doc_type, prefix, include_year, padding, next_value)
        VALUES
            ('supplier', 'SUP', false, 5, 1),
            ('purchase_order', 'PO', true, 6, 1)
        ON CONFLICT (doc_type) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("supplier_products")
    op.drop_table("suppliers")
    op.drop_column("company_settings", "bill_price_tolerance_pct")
