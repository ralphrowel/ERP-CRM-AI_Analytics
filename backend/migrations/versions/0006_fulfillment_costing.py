"""V0.4b schema: Physical Fulfillment, Costing & COGS (shipments, adjustments, transfers)

Revision ID: 0006_fulfillment_costing
Revises: 0005_inventory_foundation
Create Date: 2026-10-08 20:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_fulfillment_costing"
down_revision: str | None = "0005_inventory_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. shipments table
    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("shipment_no", sa.String(length=50), nullable=True),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("carrier", sa.String(length=100), nullable=True),
        sa.Column("tracking_no", sa.String(length=100), nullable=True),
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
            name="ck_shipments_status",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR shipment_no IS NOT NULL",
            name="ck_shipments_posted_has_no",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR shipped_at IS NOT NULL",
            name="ck_shipments_posted_has_shipped_at",
        ),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shipment_no"),
    )
    op.create_index("ix_shipments_sales_order_id", "shipments", ["sales_order_id"])
    op.create_index("ix_shipments_warehouse_id", "shipments", ["warehouse_id"])
    op.create_index("ix_shipments_status", "shipments", ["status"])

    op.execute("""
    CREATE TRIGGER trg_shipments_updated_at
    BEFORE UPDATE ON shipments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 2. shipment_items table
    op.create_table(
        "shipment_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("cogs_amount", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_shipment_items_quantity_positive"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0", name="ck_shipment_items_unit_cost_non_negative"
        ),
        sa.CheckConstraint(
            "cogs_amount IS NULL OR cogs_amount >= 0", name="ck_shipment_items_cogs_non_negative"
        ),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sales_order_item_id"], ["sales_order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shipment_id", "sales_order_item_id", name="uq_shipment_so_item"),
    )
    op.create_index("ix_shipment_items_product_id", "shipment_items", ["product_id"])

    # 3. stock_adjustments table
    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("adjustment_no", sa.String(length=50), nullable=True),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
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
            name="ck_stock_adjustments_status",
        ),
        sa.CheckConstraint(
            "reason IN ('count_correction', 'damage', 'loss', 'found', 'expired', 'other')",
            name="ck_stock_adjustments_reason",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR adjustment_no IS NOT NULL",
            name="ck_stock_adjustments_posted_has_no",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR posted_at IS NOT NULL",
            name="ck_stock_adjustments_posted_has_posted_at",
        ),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adjustment_no"),
    )
    op.create_index("ix_stock_adjustments_warehouse_id", "stock_adjustments", ["warehouse_id"])
    op.create_index("ix_stock_adjustments_status", "stock_adjustments", ["status"])

    op.execute("""
    CREATE TRIGGER trg_stock_adjustments_updated_at
    BEFORE UPDATE ON stock_adjustments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 4. stock_adjustment_items table
    op.create_table(
        "stock_adjustment_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("stock_adjustment_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity_change", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity_change <> 0", name="ck_adj_items_quantity_nonzero"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0", name="ck_adj_items_cost_non_negative"
        ),
        sa.CheckConstraint(
            "quantity_change <= 0 OR unit_cost IS NOT NULL",
            name="ck_adj_items_positive_requires_unit_cost",
        ),
        sa.ForeignKeyConstraint(
            ["stock_adjustment_id"], ["stock_adjustments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_adjustment_id", "product_id", name="uq_adj_product"),
    )

    # 5. stock_transfers table
    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("transfer_no", sa.String(length=50), nullable=True),
        sa.Column("from_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("to_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
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
            name="ck_stock_transfers_status",
        ),
        sa.CheckConstraint(
            "from_warehouse_id <> to_warehouse_id",
            name="ck_stock_transfers_different_warehouses",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR transfer_no IS NOT NULL",
            name="ck_stock_transfers_posted_has_no",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR posted_at IS NOT NULL",
            name="ck_stock_transfers_posted_has_posted_at",
        ),
        sa.ForeignKeyConstraint(["from_warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_no"),
    )
    op.create_index("ix_stock_transfers_from_warehouse", "stock_transfers", ["from_warehouse_id"])
    op.create_index("ix_stock_transfers_to_warehouse", "stock_transfers", ["to_warehouse_id"])
    op.create_index("ix_stock_transfers_status", "stock_transfers", ["status"])

    op.execute("""
    CREATE TRIGGER trg_stock_transfers_updated_at
    BEFORE UPDATE ON stock_transfers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 6. stock_transfer_items table
    op.create_table(
        "stock_transfer_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("stock_transfer_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_transfer_items_quantity_positive"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0", name="ck_transfer_items_cost_non_negative"
        ),
        sa.ForeignKeyConstraint(["stock_transfer_id"], ["stock_transfers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_transfer_id", "product_id", name="uq_transfer_product"),
    )

    # 7. Seed document sequences for fulfillment documents
    op.execute("""
    INSERT INTO document_sequences (doc_type, prefix, include_year, padding, next_value)
    VALUES
        ('shipment', 'SHP', true, 6, 1),
        ('stock_adjustment', 'ADJ', true, 6, 1),
        ('stock_transfer', 'TRF', true, 6, 1)
    ON CONFLICT (doc_type) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM document_sequences WHERE doc_type IN ('shipment', 'stock_adjustment', 'stock_transfer');"
    )
    op.drop_table("stock_transfer_items")
    op.drop_table("stock_transfers")
    op.drop_table("stock_adjustment_items")
    op.drop_table("stock_adjustments")
    op.drop_table("shipment_items")
    op.drop_table("shipments")
