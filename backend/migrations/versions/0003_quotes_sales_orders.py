"""V0.3a schema: Commercial Commitment (Tax Rates, Quotes, Sales Orders)

Revision ID: 0003_quotes_sales_orders
Revises: 0002_crm_core
Create Date: 2026-10-08 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_quotes_sales_orders"
down_revision: str | None = "0002_crm_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. tax_rates table
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("rate >= 0 AND rate < 1", name="ck_tax_rates_rate_valid"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "uq_tax_rates_single_default",
        "tax_rates",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.execute("""
    CREATE TRIGGER trg_tax_rates_updated_at
    BEFORE UPDATE ON tax_rates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Seed default tax rates (Roadmap §V0.3)
    op.execute("""
    INSERT INTO tax_rates (code, name, rate, is_default, is_active)
    VALUES
        ('VAT12', 'Value-Added Tax 12%', 0.1200, true, true),
        ('VAT0', 'Zero-Rated VAT 0%', 0.0000, false, true),
        ('EXEMPT', 'VAT-Exempt', 0.0000, false, true)
    ON CONFLICT (code) DO NOTHING;
    """)

    # 2. Add tax_rate_id to products and backfill with VAT12 default
    op.add_column("products", sa.Column("tax_rate_id", sa.BigInteger(), nullable=True))
    op.execute("""
    UPDATE products
    SET tax_rate_id = (SELECT id FROM tax_rates WHERE code = 'VAT12' LIMIT 1)
    WHERE tax_rate_id IS NULL;
    """)
    op.alter_column("products", "tax_rate_id", nullable=False)
    op.create_foreign_key(
        "fk_products_tax_rate_id",
        "products",
        "tax_rates",
        ["tax_rate_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_products_tax_rate_id", "products", ["tax_rate_id"])

    # 3. quotes table
    op.create_table(
        "quotes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("quote_no", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=True),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "status IN ('draft', 'sent', 'accepted', 'rejected', 'expired', 'cancelled')",
            name="ck_quotes_status",
        ),
        sa.CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_quotes_grand_total_matches",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_no"),
    )
    op.create_index("ix_quotes_customer_id", "quotes", ["customer_id"])
    op.create_index("ix_quotes_opportunity_id", "quotes", ["opportunity_id"])
    op.create_index("ix_quotes_contact_id", "quotes", ["contact_id"])
    op.create_index("ix_quotes_owner_user_id", "quotes", ["owner_user_id"])
    op.execute("""
    CREATE TRIGGER trg_quotes_updated_at
    BEFORE UPDATE ON quotes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 4. quote_items table
    op.create_table(
        "quote_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint("quantity > 0", name="ck_quote_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_quote_items_unit_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_quote_items_discount_non_negative"),
        sa.CheckConstraint("line_total = line_net + line_tax", name="ck_quote_items_total_matches"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_items_quote_id", "quote_items", ["quote_id"])
    op.create_index("ix_quote_items_product_id", "quote_items", ["product_id"])
    op.create_index("ix_quote_items_tax_rate_id", "quote_items", ["tax_rate_id"])
    op.create_index("uq_quote_items_line", "quote_items", ["quote_id", "line_no"], unique=True)

    # 5. sales_orders table
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("order_no", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=True),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("requested_delivery_date", sa.Date(), nullable=True),
        sa.Column("billing_address_snapshot", sa.Text(), server_default="", nullable=False),
        sa.Column("shipping_address_snapshot", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "payment_terms_days_snapshot", sa.SmallInteger(), server_default="0", nullable=False
        ),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "status IN ('draft', 'confirmed', 'on_hold', 'partially_shipped', 'shipped', 'completed', 'cancelled')",
            name="ck_sales_orders_status",
        ),
        sa.CheckConstraint(
            "grand_total = subtotal + tax_total",
            name="ck_sales_orders_grand_total_matches",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
    )
    op.create_index("ix_sales_orders_customer_id", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_quote_id", "sales_orders", ["quote_id"])
    op.create_index("ix_sales_orders_contact_id", "sales_orders", ["contact_id"])
    op.create_index("ix_sales_orders_owner_user_id", "sales_orders", ["owner_user_id"])
    op.execute("""
    CREATE TRIGGER trg_sales_orders_updated_at
    BEFORE UPDATE ON sales_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 6. sales_order_items table
    op.create_table(
        "sales_order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
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
        sa.Column(
            "quantity_invoiced",
            sa.Numeric(precision=14, scale=3),
            server_default="0.000",
            nullable=False,
        ),
        sa.Column(
            "quantity_shipped",
            sa.Numeric(precision=14, scale=3),
            server_default="0.000",
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_so_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_so_items_unit_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_so_items_discount_non_negative"),
        sa.CheckConstraint("line_total = line_net + line_tax", name="ck_so_items_total_matches"),
        sa.CheckConstraint(
            "quantity_invoiced >= 0 AND quantity_invoiced <= quantity",
            name="ck_so_items_quantity_invoiced_valid",
        ),
        sa.CheckConstraint(
            "quantity_shipped >= 0 AND quantity_shipped <= quantity",
            name="ck_so_items_quantity_shipped_valid",
        ),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_order_items_sales_order_id", "sales_order_items", ["sales_order_id"])
    op.create_index("ix_sales_order_items_product_id", "sales_order_items", ["product_id"])
    op.create_index("ix_sales_order_items_tax_rate_id", "sales_order_items", ["tax_rate_id"])
    op.create_index(
        "uq_sales_order_items_line",
        "sales_order_items",
        ["sales_order_id", "line_no"],
        unique=True,
    )

    # 7. Seed document sequences for quote and sales_order (Roadmap §4.5)
    op.execute("""
    INSERT INTO document_sequences (doc_type, prefix, include_year, padding, current_year, next_value)
    VALUES
        ('quote', 'QT', true, 6, NULL, 1),
        ('sales_order', 'SO', true, 6, NULL, 1)
    ON CONFLICT (doc_type) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM document_sequences WHERE doc_type IN ('quote', 'sales_order');")

    op.execute("DROP TRIGGER IF EXISTS trg_sales_orders_updated_at ON sales_orders;")
    op.execute("DROP TRIGGER IF EXISTS trg_quotes_updated_at ON quotes;")
    op.execute("DROP TRIGGER IF EXISTS trg_tax_rates_updated_at ON tax_rates;")

    op.drop_table("sales_order_items")
    op.drop_table("sales_orders")
    op.drop_table("quote_items")
    op.drop_table("quotes")

    op.drop_constraint("fk_products_tax_rate_id", "products", type_="foreignkey")
    op.drop_index("ix_products_tax_rate_id", table_name="products")
    op.drop_column("products", "tax_rate_id")

    op.drop_table("tax_rates")
