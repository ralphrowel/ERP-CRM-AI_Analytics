"""V0.5b schema: Physical Receipts, 3-Way Match & AP Payments

Revision ID: 0008_purchasing_receipts_bills_payments
Revises: 0007_purchasing_suppliers_po
Create Date: 2026-10-09 11:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_purchasing_receipts_bills_payments"
down_revision: str | None = "0007_purchasing_suppliers_po"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. goods_receipts table
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("gr_no", sa.String(length=50), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supplier_delivery_ref", sa.String(length=100), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'posted', 'cancelled')",
            name="ck_goods_receipts_status",
        ),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gr_no"),
    )
    op.create_index("ix_goods_receipts_gr_no", "goods_receipts", ["gr_no"])
    op.create_index("ix_goods_receipts_po_id", "goods_receipts", ["purchase_order_id"])
    op.create_index("ix_goods_receipts_warehouse_id", "goods_receipts", ["warehouse_id"])
    op.create_index("ix_goods_receipts_status", "goods_receipts", ["status"])

    op.execute(
        """
        CREATE TRIGGER trg_goods_receipts_updated_at
        BEFORE UPDATE ON goods_receipts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # 2. goods_receipt_items table
    op.create_table(
        "goods_receipt_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("goods_receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_gr_items_quantity_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_gr_items_unit_cost_non_negative"),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_item_id"], ["purchase_order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gr_items_gr_id", "goods_receipt_items", ["goods_receipt_id"])
    op.create_index("ix_gr_items_po_item_id", "goods_receipt_items", ["purchase_order_item_id"])
    op.create_index("ix_gr_items_product_id", "goods_receipt_items", ["product_id"])

    # 3. supplier_invoices (Supplier Bills)
    op.create_table(
        "supplier_invoices",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bill_no", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_invoice_ref", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "subtotal",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "tax_total",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "grand_total",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "amount_paid",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "balance_due",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("match_notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'matched', 'exception', 'approved', 'partially_paid', 'paid', 'void')",
            name="ck_supplier_invoices_status",
        ),
        sa.CheckConstraint("subtotal >= 0", name="ck_supplier_invoices_subtotal_non_negative"),
        sa.CheckConstraint("tax_total >= 0", name="ck_supplier_invoices_tax_total_non_negative"),
        sa.CheckConstraint(
            "grand_total >= 0", name="ck_supplier_invoices_grand_total_non_negative"
        ),
        sa.CheckConstraint(
            "amount_paid >= 0", name="ck_supplier_invoices_amount_paid_non_negative"
        ),
        sa.CheckConstraint(
            "balance_due >= 0", name="ck_supplier_invoices_balance_due_non_negative"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_no"),
        sa.UniqueConstraint("supplier_id", "supplier_invoice_ref", name="uq_supplier_invoice_ref"),
    )
    op.create_index("ix_supplier_invoices_bill_no", "supplier_invoices", ["bill_no"])
    op.create_index("ix_supplier_invoices_supplier_id", "supplier_invoices", ["supplier_id"])
    op.create_index("ix_supplier_invoices_po_id", "supplier_invoices", ["purchase_order_id"])
    op.create_index("ix_supplier_invoices_status", "supplier_invoices", ["status"])

    op.execute(
        """
        CREATE TRIGGER trg_supplier_invoices_updated_at
        BEFORE UPDATE ON supplier_invoices
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # 4. supplier_invoice_items table
    op.create_table(
        "supplier_invoice_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("supplier_invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("tax_rate_id", sa.BigInteger(), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_tax", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_bill_items_quantity_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_bill_items_unit_cost_non_negative"),
        sa.CheckConstraint("line_net >= 0", name="ck_bill_items_line_net_non_negative"),
        sa.CheckConstraint("line_tax >= 0", name="ck_bill_items_line_tax_non_negative"),
        sa.CheckConstraint("line_total >= 0", name="ck_bill_items_line_total_non_negative"),
        sa.ForeignKeyConstraint(
            ["supplier_invoice_id"], ["supplier_invoices.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_item_id"], ["purchase_order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_invoice_id", "line_no", name="uq_bill_items_bill_line_no"),
    )
    op.create_index(
        "ix_supplier_invoice_items_bill_id", "supplier_invoice_items", ["supplier_invoice_id"]
    )
    op.create_index(
        "ix_supplier_invoice_items_po_item_id",
        "supplier_invoice_items",
        ["purchase_order_item_id"],
    )
    op.create_index(
        "ix_supplier_invoice_items_product_id", "supplier_invoice_items", ["product_id"]
    )

    # 5. supplier_payments table
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("payment_no", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column(
            "amount_allocated",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="posted", nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount > 0", name="ck_supplier_payments_amount_positive"),
        sa.CheckConstraint(
            "amount_allocated >= 0 AND amount_allocated <= amount",
            name="ck_supplier_payments_amount_allocated_bounds",
        ),
        sa.CheckConstraint(
            "status IN ('posted', 'void')",
            name="ck_supplier_payments_status",
        ),
        sa.CheckConstraint(
            "payment_method IN ('bank_transfer', 'check', 'cash', 'credit_card', 'other')",
            name="ck_supplier_payments_method",
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_no"),
    )
    op.create_index("ix_supplier_payments_payment_no", "supplier_payments", ["payment_no"])
    op.create_index("ix_supplier_payments_supplier_id", "supplier_payments", ["supplier_id"])
    op.create_index("ix_supplier_payments_status", "supplier_payments", ["status"])

    op.execute(
        """
        CREATE TRIGGER trg_supplier_payments_updated_at
        BEFORE UPDATE ON supplier_payments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # 6. supplier_payment_allocations table
    op.create_table(
        "supplier_payment_allocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("supplier_payment_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column(
            "allocated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("allocated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_spay_allocations_amount_positive"),
        sa.ForeignKeyConstraint(
            ["supplier_payment_id"], ["supplier_payments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_invoice_id"], ["supplier_invoices.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["allocated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supplier_payment_id", "supplier_invoice_id", name="uq_spay_payment_bill"
        ),
    )
    op.create_index(
        "ix_spay_allocations_payment_id",
        "supplier_payment_allocations",
        ["supplier_payment_id"],
    )
    op.create_index(
        "ix_spay_allocations_invoice_id",
        "supplier_payment_allocations",
        ["supplier_invoice_id"],
    )

    # 7. Document sequence seeds
    op.execute(
        """
        INSERT INTO document_sequences (doc_type, prefix, include_year, padding, next_value)
        VALUES
            ('goods_receipt', 'GR', true, 6, 1),
            ('supplier_invoice', 'BILL', true, 6, 1),
            ('supplier_payment', 'SPAY', true, 6, 1)
        ON CONFLICT (doc_type) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("supplier_payment_allocations")
    op.drop_table("supplier_payments")
    op.drop_table("supplier_invoice_items")
    op.drop_table("supplier_invoices")
    op.drop_table("goods_receipt_items")
    op.drop_table("goods_receipts")
