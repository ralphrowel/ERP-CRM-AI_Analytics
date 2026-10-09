"""V0.7 schema: Workflow Engine and Approvals

Revision ID: 0010_workflow_approvals
Revises: 0009_rbac_permissions_roles
Create Date: 2026-10-09 15:45:00
"""

from decimal import Decimal

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_workflow_approvals"
down_revision = "0009_rbac_permissions_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Update check constraints to include 'pending_approval'
    if dialect == "postgresql":
        op.drop_constraint("ck_sales_orders_status", "sales_orders", type_="check")
        op.create_check_constraint(
            "ck_sales_orders_status",
            "sales_orders",
            "status IN ('draft', 'pending_approval', 'confirmed', 'on_hold', 'partially_shipped', 'shipped', 'completed', 'cancelled')",
        )
        op.drop_constraint("ck_purchase_orders_status", "purchase_orders", type_="check")
        op.create_check_constraint(
            "ck_purchase_orders_status",
            "purchase_orders",
            "status IN ('draft', 'pending_approval', 'sent', 'partially_received', 'received', 'closed', 'cancelled')",
        )

    # 2. approval_rules table
    approval_rules_table = op.create_table(
        "approval_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("threshold_amount", sa.Numeric(precision=19, scale=2), nullable=True),
        sa.Column("threshold_pct", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("approver_permission", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "threshold_amount IS NOT NULL OR threshold_pct IS NOT NULL OR approver_permission IS NOT NULL",
            name="ck_approval_rules_has_condition",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_approval_rules_code", "approval_rules", ["code"])
    op.create_index("ix_approval_rules_entity_type", "approval_rules", ["entity_type"])

    if dialect == "postgresql":
        op.execute(
            """
            CREATE TRIGGER trg_approval_rules_updated_at
            BEFORE UPDATE ON approval_rules
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
            """
        )

    # 3. approval_requests table
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_requests_status",
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> requested_by",
            name="ck_approval_requests_separation_of_duties",
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["approval_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_requests_entity", "approval_requests", ["entity_type", "entity_id"]
    )
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index("ix_approval_requests_requested_by", "approval_requests", ["requested_by"])

    if dialect == "postgresql":
        op.create_index(
            "uq_approval_requests_pending_rule_entity",
            "approval_requests",
            ["rule_id", "entity_type", "entity_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )
    else:
        op.create_index(
            "ix_approval_requests_rule_entity",
            "approval_requests",
            ["rule_id", "entity_type", "entity_id"],
        )

    # 4. Seed initial approval rules
    rules_data = [
        {
            "code": "SO_DISCOUNT",
            "entity_type": "sales_order",
            "description": "Sales Order discount percentage exceeds 15%",
            "threshold_pct": Decimal("0.1500"),
            "threshold_amount": None,
            "approver_permission": "sales_order:approve",
            "is_active": True,
        },
        {
            "code": "CREDIT_OVERRIDE",
            "entity_type": "sales_order",
            "description": "Order confirmation exceeds customer credit limit",
            "threshold_pct": None,
            "threshold_amount": None,
            "approver_permission": "credit:override",
            "is_active": True,
        },
        {
            "code": "PO_AMOUNT",
            "entity_type": "purchase_order",
            "description": "Purchase Order grand total exceeds ₱100,000",
            "threshold_pct": None,
            "threshold_amount": Decimal("100000.00"),
            "approver_permission": "purchase_order:approve",
            "is_active": True,
        },
        {
            "code": "ADJ_VALUE",
            "entity_type": "stock_adjustment",
            "description": "Stock adjustment absolute value exceeds ₱20,000",
            "threshold_pct": None,
            "threshold_amount": Decimal("20000.00"),
            "approver_permission": "stock_adjustment:approve",
            "is_active": True,
        },
        {
            "code": "BILL_EXCEPTION",
            "entity_type": "supplier_invoice",
            "description": "Supplier invoice 3-way match exception approval",
            "threshold_pct": None,
            "threshold_amount": None,
            "approver_permission": "supplier_invoice:approve_exception",
            "is_active": True,
        },
    ]
    op.bulk_insert(approval_rules_table, rules_data)

    # 5. Seed new permissions
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.BigInteger),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("module", sa.String),
    )
    new_perms = [
        {
            "code": "sales_order:approve",
            "description": "Approve sales orders with high discounts",
            "module": "sales",
        },
        {
            "code": "credit:override",
            "description": "Override customer credit limit on confirmation",
            "module": "sales",
        },
        {
            "code": "purchase_order:approve",
            "description": "Approve high-value purchase orders",
            "module": "purchasing",
        },
        {
            "code": "stock_adjustment:approve",
            "description": "Approve high-value inventory adjustments",
            "module": "inventory",
        },
        {
            "code": "supplier_invoice:approve_exception",
            "description": "Approve supplier bills with 3-way match exceptions",
            "module": "purchasing",
        },
        {
            "code": "approval_rule:read",
            "description": "View workflow approval rules and thresholds",
            "module": "workflow",
        },
        {
            "code": "approval_rule:update",
            "description": "Update workflow approval thresholds",
            "module": "workflow",
        },
        {
            "code": "approval_request:read",
            "description": "View approval requests queue",
            "module": "workflow",
        },
        {
            "code": "approval_request:decide",
            "description": "Approve or reject workflow requests",
            "module": "workflow",
        },
    ]
    op.bulk_insert(permissions_table, new_perms)

    # 6. Map new permissions to roles
    # Fetch roles and permissions
    role_rows = bind.execute(sa.text("SELECT id, code FROM roles")).fetchall()
    role_map = {r[1]: r[0] for r in role_rows}

    perm_rows = bind.execute(sa.text("SELECT id, code FROM permissions")).fetchall()
    perm_map = {p[1]: p[0] for p in perm_rows}

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.BigInteger),
        sa.column("permission_id", sa.BigInteger),
        sa.column("scope", sa.String),
    )

    grants = []

    def grant(role_code: str, perm_code: str, scope: str = "all"):
        if role_code in role_map and perm_code in perm_map:
            grants.append(
                {
                    "role_id": role_map[role_code],
                    "permission_id": perm_map[perm_code],
                    "scope": scope,
                }
            )

    # Admin gets all
    for p in new_perms:
        grant("admin", p["code"], "all")

    # Managerial assignments
    grant("sales_manager", "sales_order:approve", "department")
    grant("sales_manager", "credit:override", "department")
    grant("sales_manager", "approval_request:read", "department")
    grant("sales_manager", "approval_request:decide", "department")

    grant("purchasing_officer", "purchase_order:approve", "all")
    grant("purchasing_officer", "supplier_invoice:approve_exception", "all")
    grant("purchasing_officer", "approval_request:read", "all")
    grant("purchasing_officer", "approval_request:decide", "all")

    grant("inventory_manager", "stock_adjustment:approve", "all")
    grant("inventory_manager", "approval_request:read", "all")
    grant("inventory_manager", "approval_request:decide", "all")

    grant("finance_manager", "credit:override", "all")
    grant("finance_manager", "sales_order:approve", "all")
    grant("finance_manager", "purchase_order:approve", "all")
    grant("finance_manager", "supplier_invoice:approve_exception", "all")
    grant("finance_manager", "approval_request:read", "all")
    grant("finance_manager", "approval_request:decide", "all")

    if grants:
        op.bulk_insert(role_permissions_table, grants)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_approval_rules_updated_at ON approval_rules;")
        op.drop_index("uq_approval_requests_pending_rule_entity", table_name="approval_requests")
    else:
        op.drop_index("ix_approval_requests_rule_entity", table_name="approval_requests")

    op.drop_table("approval_requests")
    op.drop_table("approval_rules")

    # Revert check constraints
    if dialect == "postgresql":
        op.drop_constraint("ck_sales_orders_status", "sales_orders", type_="check")
        op.create_check_constraint(
            "ck_sales_orders_status",
            "sales_orders",
            "status IN ('draft', 'confirmed', 'on_hold', 'partially_shipped', 'shipped', 'completed', 'cancelled')",
        )
        op.drop_constraint("ck_purchase_orders_status", "purchase_orders", type_="check")
        op.create_check_constraint(
            "ck_purchase_orders_status",
            "purchase_orders",
            "status IN ('draft', 'sent', 'partially_received', 'received', 'closed', 'cancelled')",
        )
