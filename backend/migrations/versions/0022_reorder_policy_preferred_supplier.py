"""V3.2 schema: Reorder policy preferred supplier for automated purchase replenishment

Revision ID: 0022_reorder_policy_preferred_supplier
Revises: 0021_warehouse_replenishment
Create Date: 2026-10-22 17:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_reorder_policy_preferred_supplier"
down_revision: str | None = "0021_warehouse_replenishment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "warehouse_reorder_policies",
        sa.Column(
            "preferred_supplier_id",
            sa.BigInteger(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_reorder_policies_supplier",
        "warehouse_reorder_policies",
        ["preferred_supplier_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reorder_policies_supplier", table_name="warehouse_reorder_policies")
    op.drop_column("warehouse_reorder_policies", "preferred_supplier_id")
