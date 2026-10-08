"""V0.4a schema: Inventory Foundation & Reservations (warehouses, balances, transactions, reservations)

Revision ID: 0005_inventory_foundation
Revises: 0004_financial_obligation
Create Date: 2026-10-08 18:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_inventory_foundation"
down_revision: str | None = "0004_financial_obligation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. warehouses table
    op.create_table(
        "warehouses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "uq_warehouses_single_default",
        "warehouses",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.execute("""
    CREATE TRIGGER trg_warehouses_updated_at
    BEFORE UPDATE ON warehouses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Seed default warehouse (Roadmap §V0.4)
    op.execute("""
    INSERT INTO warehouses (code, name, address, is_active, is_default)
    VALUES ('MNL-MAIN', 'Main Warehouse - Manila', 'Port Area, Manila, Philippines', true, true)
    ON CONFLICT (code) DO NOTHING;
    """)

    # 2. Add reorder_point to products
    op.add_column(
        "products",
        sa.Column("reorder_point", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.create_check_constraint(
        "ck_products_reorder_point_non_negative",
        "products",
        "reorder_point IS NULL OR reorder_point >= 0",
    )

    # 3. Add warehouse_id to sales_orders
    op.add_column(
        "sales_orders",
        sa.Column("warehouse_id", sa.BigInteger(), nullable=True),
    )
    # Backfill existing sales orders with default warehouse
    op.execute("""
    UPDATE sales_orders
    SET warehouse_id = (SELECT id FROM warehouses WHERE is_default = true LIMIT 1)
    WHERE warehouse_id IS NULL;
    """)
    op.alter_column("sales_orders", "warehouse_id", nullable=False)
    op.create_foreign_key(
        "fk_sales_orders_warehouse_id",
        "sales_orders",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_sales_orders_warehouse_id", "sales_orders", ["warehouse_id"])

    # 4. inventory_balances table (State Cache)
    op.create_table(
        "inventory_balances",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "qty_on_hand",
            sa.Numeric(precision=14, scale=3),
            server_default="0.000",
            nullable=False,
        ),
        sa.Column(
            "qty_reserved",
            sa.Numeric(precision=14, scale=3),
            server_default="0.000",
            nullable=False,
        ),
        sa.Column(
            "avg_unit_cost",
            sa.Numeric(precision=19, scale=4),
            server_default="0.0000",
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("qty_on_hand >= 0", name="ck_inv_balances_on_hand_non_negative"),
        sa.CheckConstraint(
            "qty_reserved >= 0 AND qty_reserved <= qty_on_hand",
            name="ck_inv_balances_reserved_valid",
        ),
        sa.CheckConstraint("avg_unit_cost >= 0", name="ck_inv_balances_cost_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("product_id", "warehouse_id"),
    )
    op.create_index("ix_inventory_balances_warehouse", "inventory_balances", ["warehouse_id"])

    # 5. inventory_transactions table (Append-Only Truth Ledger)
    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("txn_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("qty_on_hand_after", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("avg_cost_after", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("source_line_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_inv_txn_quantity_nonzero"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_inv_txn_unit_cost_non_negative"),
        sa.CheckConstraint(
            "txn_type IN ('opening', 'receipt', 'issue', 'adjustment_in', 'adjustment_out', 'transfer_in', 'transfer_out')",
            name="ck_inv_txn_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('opening', 'shipment', 'goods_receipt', 'stock_adjustment', 'stock_transfer')",
            name="ck_inv_txn_source_type",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_txns_lookup",
        "inventory_transactions",
        ["product_id", "warehouse_id", "occurred_at"],
    )

    # 6. stock_reservations table
    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column(
            "quantity_consumed",
            sa.Numeric(precision=14, scale=3),
            server_default="0.000",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_reservations_quantity_positive"),
        sa.CheckConstraint(
            "quantity_consumed >= 0 AND quantity_consumed <= quantity",
            name="ck_reservations_consumed_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'consumed', 'released')",
            name="ck_reservations_status",
        ),
        sa.ForeignKeyConstraint(
            ["sales_order_item_id"], ["sales_order_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_reservations_item", "stock_reservations", ["sales_order_item_id"])
    op.create_index(
        "ix_stock_reservations_pw", "stock_reservations", ["product_id", "warehouse_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("stock_reservations")
    op.drop_table("inventory_transactions")
    op.drop_table("inventory_balances")

    op.drop_constraint("fk_sales_orders_warehouse_id", "sales_orders", type_="foreignkey")
    op.drop_index("ix_sales_orders_warehouse_id", table_name="sales_orders")
    op.drop_column("sales_orders", "warehouse_id")

    op.drop_constraint("ck_products_reorder_point_non_negative", "products", type_="check")
    op.drop_column("products", "reorder_point")

    op.execute("DROP TRIGGER IF EXISTS trg_warehouses_updated_at ON warehouses;")
    op.drop_table("warehouses")
