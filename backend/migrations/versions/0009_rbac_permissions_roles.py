"""V0.6 schema: RBAC and Object-Level Authorization

Revision ID: 0009_rbac_permissions_roles
Revises: 0008_purchasing_receipts_ap
Create Date: 2026-10-09 13:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_rbac_permissions_roles"
down_revision: str | None = "0008_purchasing_receipts_ap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. permissions table
    permissions_table = op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])
    op.create_index("ix_permissions_module", "permissions", ["module"])

    # 2. roles table
    roles_table = op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
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
    op.create_index("ix_roles_code", "roles", ["code"])

    op.execute(
        """
        CREATE TRIGGER trg_roles_updated_at
        BEFORE UPDATE ON roles
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )

    # 3. role_permissions table
    role_permissions_table = op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=20), server_default="all", nullable=False),
        sa.CheckConstraint(
            "scope IN ('own', 'department', 'all')", name="ck_role_permissions_scope"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    # 4. user_roles table
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("assigned_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    # 5. Seed Permissions Catalog
    permissions_data = [
        # CRM
        {"code": "customer:read", "description": "View customers and contacts", "module": "crm"},
        {"code": "customer:create", "description": "Create new customer accounts", "module": "crm"},
        {"code": "customer:update", "description": "Update customer details", "module": "crm"},
        {"code": "contact:read", "description": "View contacts", "module": "crm"},
        {"code": "contact:create", "description": "Create new contacts", "module": "crm"},
        {"code": "contact:update", "description": "Update contact details", "module": "crm"},
        {"code": "lead:read", "description": "View leads", "module": "crm"},
        {"code": "lead:create", "description": "Capture new leads", "module": "crm"},
        {"code": "lead:update", "description": "Update lead information", "module": "crm"},
        {
            "code": "lead:convert",
            "description": "Convert leads to customers/deals",
            "module": "crm",
        },
        {"code": "lead:disqualify", "description": "Disqualify leads", "module": "crm"},
        {"code": "opportunity:read", "description": "View deal pipeline", "module": "crm"},
        {"code": "opportunity:create", "description": "Create new opportunities", "module": "crm"},
        {"code": "opportunity:update", "description": "Advance deal stages", "module": "crm"},
        {"code": "opportunity:close", "description": "Win or lose opportunities", "module": "crm"},
        {"code": "activity:read", "description": "View logged activities", "module": "crm"},
        {"code": "activity:create", "description": "Log new activities", "module": "crm"},
        {"code": "activity:update", "description": "Update activity logs", "module": "crm"},
        # Sales
        {"code": "quote:read", "description": "View quotes and proposals", "module": "sales"},
        {"code": "quote:create", "description": "Draft new sales quotes", "module": "sales"},
        {"code": "quote:update", "description": "Update draft quotes", "module": "sales"},
        {"code": "quote:send", "description": "Send quotes to customers", "module": "sales"},
        {"code": "quote:accept", "description": "Accept quotes into orders", "module": "sales"},
        {"code": "quote:reject", "description": "Reject or expire quotes", "module": "sales"},
        {"code": "sales_order:read", "description": "View sales orders", "module": "sales"},
        {"code": "sales_order:create", "description": "Create new sales orders", "module": "sales"},
        {
            "code": "sales_order:update",
            "description": "Update draft sales orders",
            "module": "sales",
        },
        {
            "code": "sales_order:confirm",
            "description": "Confirm orders and reserve stock",
            "module": "sales",
        },
        {"code": "sales_order:cancel", "description": "Cancel sales orders", "module": "sales"},
        {
            "code": "invoice:read",
            "description": "View invoices and accounts receivable",
            "module": "sales",
        },
        {"code": "invoice:create", "description": "Draft customer invoices", "module": "sales"},
        {"code": "invoice:update", "description": "Update draft invoices", "module": "sales"},
        {
            "code": "invoice:issue",
            "description": "Issue invoices to legal obligee",
            "module": "sales",
        },
        {"code": "invoice:void", "description": "Void issued invoices", "module": "sales"},
        {"code": "payment:read", "description": "View customer payments", "module": "sales"},
        {
            "code": "payment:create",
            "description": "Record payments and allocations",
            "module": "sales",
        },
        {"code": "payment:void", "description": "Void customer payments", "module": "sales"},
        {"code": "credit_note:read", "description": "View credit notes", "module": "sales"},
        {
            "code": "credit_note:create",
            "description": "Issue customer credit notes",
            "module": "sales",
        },
        {
            "code": "credit_note:allocate",
            "description": "Allocate credit to invoices",
            "module": "sales",
        },
        {"code": "credit_note:void", "description": "Void credit notes", "module": "sales"},
        {
            "code": "customer_statement:read",
            "description": "View customer account statements",
            "module": "sales",
        },
        # Inventory
        {
            "code": "inventory:read",
            "description": "View inventory balances and ledger",
            "module": "inventory",
        },
        {"code": "warehouse:read", "description": "View warehouse sites", "module": "inventory"},
        {
            "code": "warehouse:create",
            "description": "Add new warehouse locations",
            "module": "inventory",
        },
        {
            "code": "warehouse:update",
            "description": "Update warehouse details",
            "module": "inventory",
        },
        {
            "code": "stock_adjustment:read",
            "description": "View inventory adjustments",
            "module": "inventory",
        },
        {
            "code": "stock_adjustment:create",
            "description": "Post stock adjustments",
            "module": "inventory",
        },
        {
            "code": "stock_transfer:read",
            "description": "View inter-warehouse transfers",
            "module": "inventory",
        },
        {
            "code": "stock_transfer:create",
            "description": "Initiate stock transfers",
            "module": "inventory",
        },
        {
            "code": "stock_transfer:post",
            "description": "Complete stock transfers",
            "module": "inventory",
        },
        {
            "code": "shipment:read",
            "description": "View fulfillment shipments",
            "module": "inventory",
        },
        {
            "code": "shipment:create",
            "description": "Pick and pack shipments",
            "module": "inventory",
        },
        {
            "code": "shipment:post",
            "description": "Post shipment dispatch and COGS",
            "module": "inventory",
        },
        {"code": "shipment:cancel", "description": "Cancel draft shipments", "module": "inventory"},
        # Purchasing
        {
            "code": "supplier:read",
            "description": "View suppliers and catalogs",
            "module": "purchasing",
        },
        {"code": "supplier:create", "description": "Create new suppliers", "module": "purchasing"},
        {
            "code": "supplier:update",
            "description": "Update supplier details",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:read",
            "description": "View purchase orders",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:create",
            "description": "Draft purchase orders",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:update",
            "description": "Update draft purchase orders",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:send",
            "description": "Send PO to supplier",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:cancel",
            "description": "Cancel purchase orders",
            "module": "purchasing",
        },
        {
            "code": "purchase_order:close",
            "description": "Short-close purchase orders",
            "module": "purchasing",
        },
        {
            "code": "goods_receipt:read",
            "description": "View goods receipts",
            "module": "purchasing",
        },
        {
            "code": "goods_receipt:create",
            "description": "Record physical intake batches",
            "module": "purchasing",
        },
        {
            "code": "goods_receipt:post",
            "description": "Post goods receipts to inventory & WAC",
            "module": "purchasing",
        },
        {
            "code": "goods_receipt:cancel",
            "description": "Cancel draft goods receipts",
            "module": "purchasing",
        },
        {
            "code": "supplier_invoice:read",
            "description": "View vendor bills and 3-way match",
            "module": "purchasing",
        },
        {
            "code": "supplier_invoice:create",
            "description": "Enter vendor bills for matching",
            "module": "purchasing",
        },
        {
            "code": "supplier_invoice:approve",
            "description": "Approve matched/exception bills",
            "module": "purchasing",
        },
        {
            "code": "supplier_invoice:void",
            "description": "Void vendor bills",
            "module": "purchasing",
        },
        {
            "code": "supplier_payment:read",
            "description": "View AP disbursements",
            "module": "purchasing",
        },
        {
            "code": "supplier_payment:create",
            "description": "Disburse payments against bills",
            "module": "purchasing",
        },
        {
            "code": "supplier_payment:void",
            "description": "Void AP disbursements",
            "module": "purchasing",
        },
        {
            "code": "supplier_statement:read",
            "description": "View supplier financial statements",
            "module": "purchasing",
        },
        # Catalog
        {"code": "product:read", "description": "View products catalog", "module": "catalog"},
        {"code": "product:create", "description": "Create new products", "module": "catalog"},
        {
            "code": "product:update",
            "description": "Update product specifications and prices",
            "module": "catalog",
        },
        {"code": "category:read", "description": "View product categories", "module": "catalog"},
        {
            "code": "category:create",
            "description": "Create product categories",
            "module": "catalog",
        },
        {
            "code": "category:update",
            "description": "Update product categories",
            "module": "catalog",
        },
        {"code": "tax_rate:read", "description": "View tax rates", "module": "catalog"},
        {"code": "tax_rate:create", "description": "Configure tax rates", "module": "catalog"},
        {"code": "tax_rate:update", "description": "Update tax rates", "module": "catalog"},
        # Organization
        {
            "code": "employee:read",
            "description": "View employees directory",
            "module": "organization",
        },
        {
            "code": "employee:create",
            "description": "Onboard new employees",
            "module": "organization",
        },
        {
            "code": "employee:update",
            "description": "Update employee records",
            "module": "organization",
        },
        {"code": "department:read", "description": "View departments", "module": "organization"},
        {
            "code": "department:create",
            "description": "Add new departments",
            "module": "organization",
        },
        {
            "code": "department:update",
            "description": "Update department info",
            "module": "organization",
        },
        {
            "code": "company_settings:read",
            "description": "View company settings",
            "module": "organization",
        },
        {
            "code": "company_settings:update",
            "description": "Modify corporate settings",
            "module": "organization",
        },
        # Identity / RBAC
        {"code": "user:read", "description": "View user accounts", "module": "identity"},
        {"code": "user:create", "description": "Provision new users", "module": "identity"},
        {
            "code": "user:update",
            "description": "Update user profiles and status",
            "module": "identity",
        },
        {
            "code": "role:read",
            "description": "View roles and permission matrices",
            "module": "identity",
        },
        {"code": "role:create", "description": "Create custom roles", "module": "identity"},
        {
            "code": "role:update",
            "description": "Update role permissions and scopes",
            "module": "identity",
        },
        {"code": "role:delete", "description": "Delete custom roles", "module": "identity"},
        {
            "code": "role:assign",
            "description": "Assign or unassign roles to users",
            "module": "identity",
        },
        # Reporting
        {
            "code": "report:sales",
            "description": "Access sales analytics and performance reports",
            "module": "reporting",
        },
        {
            "code": "report:financial",
            "description": "Access AR/AP financial reports",
            "module": "reporting",
        },
        {
            "code": "report:inventory",
            "description": "Access inventory valuation and stock reports",
            "module": "reporting",
        },
        {
            "code": "report:purchasing",
            "description": "Access procurement and spend reports",
            "module": "reporting",
        },
    ]

    op.bulk_insert(permissions_table, permissions_data)

    # 6. Seed System Roles
    roles_data = [
        {
            "code": "admin",
            "name": "System Administrator",
            "description": "Full unconstrained administrative access across all system modules.",
            "is_system": True,
        },
        {
            "code": "sales_manager",
            "name": "Sales Manager",
            "description": "Department-wide authority over CRM pipeline, quotes, and orders.",
            "is_system": True,
        },
        {
            "code": "sales_rep",
            "name": "Sales Representative",
            "description": "Manage individual assigned customers, leads, opportunities, and draft quotes.",
            "is_system": True,
        },
        {
            "code": "finance",
            "name": "Finance & Accounts",
            "description": "Full authority over accounts receivable (AR), accounts payable (AP), and billing.",
            "is_system": True,
        },
        {
            "code": "warehouse_staff",
            "name": "Warehouse & Logistics",
            "description": "Fulfillment shipments, goods receipt intake, adjustments, and stock transfers.",
            "is_system": True,
        },
        {
            "code": "purchasing",
            "name": "Purchasing Specialist",
            "description": "Manage vendor master data, purchase order cycles, and physical intake.",
            "is_system": True,
        },
        {
            "code": "management",
            "name": "Executive Management",
            "description": "Read-only access across all operational modules, customer accounts, and reports.",
            "is_system": True,
        },
    ]

    op.bulk_insert(roles_table, roles_data)

    # 7. Map permissions to roles
    # Fetch generated IDs
    bind = op.get_bind()
    perm_rows = bind.execute(sa.text("SELECT id, code, module FROM permissions")).fetchall()
    perm_map = {row.code: row.id for row in perm_rows}

    role_rows = bind.execute(sa.text("SELECT id, code FROM roles")).fetchall()
    role_map = {row.code: row.id for row in role_rows}

    role_perms_data = []

    # Helper: grant to role
    def grant(role_code: str, perm_code: str, scope: str = "all"):
        if role_code in role_map and perm_code in perm_map:
            role_perms_data.append(
                {
                    "role_id": role_map[role_code],
                    "permission_id": perm_map[perm_code],
                    "scope": scope,
                }
            )

    def grant_prefix(role_code: str, prefix: str, scope: str = "all"):
        for code in perm_map:
            if code.startswith(prefix):
                grant(role_code, code, scope)

    # 1. Admin: ALL permissions with scope 'all'
    for code in perm_map:
        grant("admin", code, "all")

    # 2. Sales Manager (department scope for CRM and sales documents)
    crm_sales_prefixes = [
        "customer:",
        "contact:",
        "lead:",
        "opportunity:",
        "activity:",
        "quote:",
        "sales_order:",
        "customer_statement:",
    ]
    for prefix in crm_sales_prefixes:
        grant_prefix("sales_manager", prefix, "department")
    # Read-only lookups
    grant("sales_manager", "invoice:read", "department")
    grant("sales_manager", "product:read", "all")
    grant("sales_manager", "category:read", "all")
    grant("sales_manager", "tax_rate:read", "all")
    grant("sales_manager", "inventory:read", "all")
    grant("sales_manager", "report:sales", "department")

    # 3. Sales Representative (own scope)
    grant("sales_rep", "customer:read", "own")
    grant("sales_rep", "customer:create", "own")
    grant("sales_rep", "customer:update", "own")
    grant("sales_rep", "contact:read", "own")
    grant("sales_rep", "contact:create", "own")
    grant("sales_rep", "contact:update", "own")
    grant("sales_rep", "lead:read", "own")
    grant("sales_rep", "lead:create", "own")
    grant("sales_rep", "lead:update", "own")
    grant("sales_rep", "lead:convert", "own")
    grant("sales_rep", "lead:disqualify", "own")
    grant("sales_rep", "opportunity:read", "own")
    grant("sales_rep", "opportunity:create", "own")
    grant("sales_rep", "opportunity:update", "own")
    grant("sales_rep", "opportunity:close", "own")
    grant("sales_rep", "activity:read", "own")
    grant("sales_rep", "activity:create", "own")
    grant("sales_rep", "activity:update", "own")
    grant("sales_rep", "quote:read", "own")
    grant("sales_rep", "quote:create", "own")
    grant("sales_rep", "quote:update", "own")
    grant("sales_rep", "quote:send", "own")
    grant("sales_rep", "sales_order:read", "own")
    grant("sales_rep", "sales_order:create", "own")
    grant("sales_rep", "product:read", "all")
    grant("sales_rep", "category:read", "all")
    grant("sales_rep", "tax_rate:read", "all")
    grant("sales_rep", "inventory:read", "all")

    # 4. Finance (all scope for billing, invoices, credit notes, payments, suppliers bills)
    grant_prefix("finance", "invoice:", "all")
    grant_prefix("finance", "credit_note:", "all")
    grant_prefix("finance", "payment:", "all")
    grant_prefix("finance", "supplier_invoice:", "all")
    grant_prefix("finance", "supplier_payment:", "all")
    grant("finance", "customer:read", "all")
    grant("finance", "supplier:read", "all")
    grant("finance", "sales_order:read", "all")
    grant("finance", "purchase_order:read", "all")
    grant("finance", "customer_statement:read", "all")
    grant("finance", "supplier_statement:read", "all")
    grant_prefix("finance", "tax_rate:", "all")
    grant("finance", "report:financial", "all")

    # 5. Warehouse Staff (all scope for inventory, shipments, receipts, transfers)
    grant("warehouse_staff", "inventory:read", "all")
    grant("warehouse_staff", "warehouse:read", "all")
    grant_prefix("warehouse_staff", "shipment:", "all")
    grant_prefix("warehouse_staff", "goods_receipt:", "all")
    grant_prefix("warehouse_staff", "stock_adjustment:", "all")
    grant_prefix("warehouse_staff", "stock_transfer:", "all")
    grant("warehouse_staff", "product:read", "all")
    grant("warehouse_staff", "category:read", "all")
    grant("warehouse_staff", "report:inventory", "all")

    # 6. Purchasing (all scope for procurement)
    grant_prefix("purchasing", "supplier:", "all")
    grant_prefix("purchasing", "purchase_order:", "all")
    grant("purchasing", "goods_receipt:read", "all")
    grant("purchasing", "supplier_invoice:read", "all")
    grant("purchasing", "inventory:read", "all")
    grant("purchasing", "product:read", "all")
    grant("purchasing", "category:read", "all")
    grant("purchasing", "report:purchasing", "all")

    # 7. Management (read-only all)
    for code in perm_map:
        if code.endswith(":read"):
            grant("management", code, "all")
    grant_prefix("management", "report:", "all")

    if role_perms_data:
        op.bulk_insert(role_permissions_table, role_perms_data)

    # 8. Assign 'admin' role to any existing superuser
    admin_role_id = role_map.get("admin")
    if admin_role_id:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_roles (user_id, role_id)
                SELECT id, :admin_role_id
                FROM users
                WHERE is_superuser = true
                ON CONFLICT (user_id, role_id) DO NOTHING
                """
            ),
            {"admin_role_id": admin_role_id},
        )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.execute("DROP TRIGGER IF EXISTS trg_roles_updated_at ON roles;")
    op.drop_table("roles")
    op.drop_table("permissions")
