"""V3.1 schema: Multi-Warehouse Automated Replenishment & In-Transit Transfer Logistics

Revision ID: 0021_warehouse_replenishment
Revises: 0020_multi_currency_fx
Create Date: 2026-10-22 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_warehouse_replenishment"
down_revision: str | None = "0020_multi_currency_fx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add workflow tracking columns to stock_transfers
    op.add_column(
        "stock_transfers", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "stock_transfers",
        sa.Column(
            "approved_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "stock_transfers", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "stock_transfers",
        sa.Column(
            "dispatched_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "stock_transfers", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "stock_transfers",
        sa.Column(
            "received_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Update stock_transfers check constraints for expanded workflow statuses
    op.drop_constraint("ck_stock_transfers_status", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_stock_transfers_status",
        "stock_transfers",
        "status IN ('draft', 'approved', 'in_transit', 'posted', 'cancelled')",
    )
    op.drop_constraint("ck_stock_transfers_posted_has_no", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_stock_transfers_executed_has_no",
        "stock_transfers",
        "status NOT IN ('in_transit', 'posted') OR transfer_no IS NOT NULL",
    )

    # 3. Create warehouse_reorder_policies table
    op.create_table(
        "warehouse_reorder_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("min_qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("max_qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("reorder_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column(
            "replenishment_source",
            sa.String(30),
            server_default="transfer",
            nullable=False,
        ),
        sa.Column(
            "source_warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("lead_time_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("warehouse_id", "product_id", name="uq_reorder_policies_wh_prod"),
        sa.CheckConstraint("min_qty >= 0", name="ck_reorder_policy_min_non_negative"),
        sa.CheckConstraint("max_qty >= min_qty", name="ck_reorder_policy_max_gte_min"),
        sa.CheckConstraint(
            "reorder_quantity IS NULL OR reorder_quantity > 0",
            name="ck_reorder_policy_reorder_qty_positive",
        ),
        sa.CheckConstraint(
            "replenishment_source IN ('transfer', 'purchase')",
            name="ck_reorder_policy_source",
        ),
        sa.CheckConstraint(
            "replenishment_source <> 'transfer' OR source_warehouse_id IS NOT NULL",
            name="ck_reorder_policy_transfer_source_required",
        ),
        sa.CheckConstraint(
            "source_warehouse_id IS NULL OR source_warehouse_id <> warehouse_id",
            name="ck_reorder_policy_distinct_source_wh",
        ),
        sa.CheckConstraint("lead_time_days >= 0", name="ck_reorder_policy_lead_time_non_negative"),
    )
    op.create_index(
        "ix_reorder_policies_warehouse",
        "warehouse_reorder_policies",
        ["warehouse_id"],
    )
    op.create_index(
        "ix_reorder_policies_product",
        "warehouse_reorder_policies",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reorder_policies_product", table_name="warehouse_reorder_policies")
    op.drop_index("ix_reorder_policies_warehouse", table_name="warehouse_reorder_policies")
    op.drop_table("warehouse_reorder_policies")

    op.drop_column("stock_transfers", "received_by")
    op.drop_column("stock_transfers", "received_at")
    op.drop_column("stock_transfers", "dispatched_by")
    op.drop_column("stock_transfers", "dispatched_at")
    op.drop_column("stock_transfers", "approved_by")
    op.drop_column("stock_transfers", "approved_at")

    op.drop_constraint("ck_stock_transfers_executed_has_no", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_stock_transfers_posted_has_no",
        "stock_transfers",
        "status <> 'posted' OR transfer_no IS NOT NULL",
    )
    op.drop_constraint("ck_stock_transfers_status", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_stock_transfers_status",
        "stock_transfers",
        "status IN ('draft', 'posted', 'cancelled')",
    )
