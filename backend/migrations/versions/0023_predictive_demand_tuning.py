"""V3.3 schema: Predictive demand tuning columns on warehouse_reorder_policies

Revision ID: 0023_predictive_demand_tuning
Revises: 0022_purchase_replenishment
Create Date: 2026-10-22 18:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_predictive_demand_tuning"
down_revision: str | None = "0022_purchase_replenishment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "warehouse_reorder_policies",
        sa.Column(
            "service_level",
            sa.Numeric(5, 4),
            server_default="0.9500",
            nullable=False,
        ),
    )
    op.add_column(
        "warehouse_reorder_policies",
        sa.Column(
            "safety_stock",
            sa.Numeric(14, 3),
            nullable=True,
        ),
    )
    op.add_column(
        "warehouse_reorder_policies",
        sa.Column(
            "last_tuned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "warehouse_reorder_policies",
        sa.Column(
            "tuning_method",
            sa.String(50),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("warehouse_reorder_policies", "tuning_method")
    op.drop_column("warehouse_reorder_policies", "last_tuned_at")
    op.drop_column("warehouse_reorder_policies", "safety_stock")
    op.drop_column("warehouse_reorder_policies", "service_level")
