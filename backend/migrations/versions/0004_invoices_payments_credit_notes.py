"""V0.3b schema: Financial Obligation (Invoices, Payments, Credit Notes, Idempotency)

Revision ID: 0004_invoices_payments_credit_notes
Revises: 0003_quotes_sales_orders
Create Date: 2026-10-08 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_invoices_payments_credit_notes"
down_revision: str | None = "0003_quotes_sales_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. invoices table
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("invoice_no", sa.String(length=50), nullable=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("customer_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("customer_tin_snapshot", sa.String(length=50), nullable=True),
        sa.Column("billing_address_snapshot", sa.Text(), nullable=True),
        sa.Column(
            "amount_paid",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "amount_credited",
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
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), server_default="PHP", nullable=False),
        sa.Column(
            "subtotal", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
        ),
        sa.Column(
            "discount_total",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "tax_total", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
        ),
        sa.Column(
            "grand_total", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
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
            "status IN ('draft', 'issued', 'partially_paid', 'paid', 'void')",
            name="ck_invoices_status",
        ),
        sa.CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_invoices_grand_total_matches",
        ),
        sa.CheckConstraint(
            "(status = 'void' AND balance_due = 0) OR (balance_due = grand_total - amount_paid - amount_credited AND balance_due >= 0)",
            name="ck_invoices_balance_due_calc",
        ),
        sa.CheckConstraint(
            "status = 'draft' OR invoice_no IS NOT NULL",
            name="ck_invoices_issued_has_no",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_no"),
    )
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_sales_order_id", "invoices", ["sales_order_id"])
    op.execute("""
    CREATE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 2. invoice_items table
    op.create_table(
        "invoice_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=True),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("tax_rate_id", sa.BigInteger(), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_tax", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_inv_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_inv_items_unit_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_inv_items_discount_non_negative"),
        sa.CheckConstraint("line_total = line_net + line_tax", name="ck_inv_items_total_matches"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sales_order_item_id"], ["sales_order_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])
    op.create_index(
        "ix_invoice_items_sales_order_item_id", "invoice_items", ["sales_order_item_id"]
    )
    op.create_index("ix_invoice_items_product_id", "invoice_items", ["product_id"])
    op.create_index("ix_invoice_items_tax_rate_id", "invoice_items", ["tax_rate_id"])
    op.create_index(
        "uq_invoice_items_line", "invoice_items", ["invoice_id", "line_no"], unique=True
    )

    # 3. credit_notes table
    op.create_table(
        "credit_notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("credit_note_no", sa.String(length=50), nullable=True),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("currency_code", sa.String(length=3), server_default="PHP", nullable=False),
        sa.Column(
            "subtotal", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
        ),
        sa.Column(
            "discount_total",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column(
            "tax_total", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
        ),
        sa.Column(
            "grand_total", sa.Numeric(precision=19, scale=2), server_default="0.00", nullable=False
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
            "status IN ('draft', 'issued', 'void')",
            name="ck_credit_notes_status",
        ),
        sa.CheckConstraint(
            "reason IN ('pricing_error', 'discount', 'damaged', 'returned', 'other')",
            name="ck_credit_notes_reason",
        ),
        sa.CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_credit_notes_grand_total_matches",
        ),
        sa.CheckConstraint(
            "status = 'draft' OR credit_note_no IS NOT NULL",
            name="ck_credit_notes_issued_has_no",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_note_no"),
    )
    op.create_index("ix_credit_notes_invoice_id", "credit_notes", ["invoice_id"])
    op.create_index("ix_credit_notes_customer_id", "credit_notes", ["customer_id"])
    op.execute("""
    CREATE TRIGGER trg_credit_notes_updated_at
    BEFORE UPDATE ON credit_notes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 4. credit_note_items table
    op.create_table(
        "credit_note_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("credit_note_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_item_id", sa.BigInteger(), nullable=True),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("tax_rate_id", sa.BigInteger(), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("line_net", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_tax", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_cn_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_cn_items_unit_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_cn_items_discount_non_negative"),
        sa.CheckConstraint("line_total = line_net + line_tax", name="ck_cn_items_total_matches"),
        sa.ForeignKeyConstraint(["credit_note_id"], ["credit_notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_item_id"], ["invoice_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_note_items_credit_note_id", "credit_note_items", ["credit_note_id"])
    op.create_index(
        "ix_credit_note_items_invoice_item_id", "credit_note_items", ["invoice_item_id"]
    )
    op.create_index("ix_credit_note_items_product_id", "credit_note_items", ["product_id"])
    op.create_index("ix_credit_note_items_tax_rate_id", "credit_note_items", ["tax_rate_id"])
    op.create_index(
        "uq_credit_note_items_line", "credit_note_items", ["credit_note_id", "line_no"], unique=True
    )

    # 5. payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("payment_no", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column(
            "amount_allocated",
            sa.Numeric(precision=19, scale=2),
            server_default="0.00",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), server_default="posted", nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "amount_allocated >= 0 AND amount_allocated <= amount",
            name="ck_payments_amount_allocated_valid",
        ),
        sa.CheckConstraint(
            "method IN ('cash', 'bank_transfer', 'check', 'gcash', 'maya', 'card')",
            name="ck_payments_method",
        ),
        sa.CheckConstraint("status IN ('posted', 'void')", name="ck_payments_status"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_no"),
    )
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.execute("""
    CREATE TRIGGER trg_payments_updated_at
    BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 6. payment_allocations table
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column(
            "allocated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("allocated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_allocations_amount_positive"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["allocated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"])
    op.create_index(
        "uq_payment_allocations_pair",
        "payment_allocations",
        ["payment_id", "invoice_id"],
        unique=True,
    )

    # 7. idempotency_keys table
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_idempotency_keys_user_key", "idempotency_keys", ["user_id", "key"], unique=True
    )

    # 8. Seed document sequences for invoice, credit_note, payment (Roadmap §4.5)
    op.execute("""
    INSERT INTO document_sequences (doc_type, prefix, include_year, padding, current_year, next_value)
    VALUES
        ('invoice', 'INV', true, 6, NULL, 1),
        ('credit_note', 'CN', true, 6, NULL, 1),
        ('payment', 'PAY', true, 6, NULL, 1)
    ON CONFLICT (doc_type) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM document_sequences WHERE doc_type IN ('invoice', 'credit_note', 'payment');"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_payments_updated_at ON payments;")
    op.execute("DROP TRIGGER IF EXISTS trg_credit_notes_updated_at ON credit_notes;")
    op.execute("DROP TRIGGER IF EXISTS trg_invoices_updated_at ON invoices;")

    op.drop_table("idempotency_keys")
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("credit_note_items")
    op.drop_table("credit_notes")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
