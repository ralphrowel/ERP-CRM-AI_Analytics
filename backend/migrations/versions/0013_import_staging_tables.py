"""V1.0 schema: Import Batches and Staging Tables

Revision ID: 0013_import_staging_tables
Revises: 0012_reporting_permissions
Create Date: 2026-10-11 16:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_import_staging_tables"
down_revision: str | None = "0012_reporting_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    json_type = postgresql.JSONB() if dialect == "postgresql" else sa.JSON()

    # 1. import_batches
    op.create_table(
        "import_batches",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True) if dialect == "postgresql" else None,
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_label", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="uploaded", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("committed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "entity_type IN ('customer', 'product', 'contact')",
            name="ck_import_batches_entity_type",
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'validated', 'committed', 'failed', 'cancelled')",
            name="ck_import_batches_status",
        ),
    )
    op.create_index("ix_import_batches_entity_type", "import_batches", ["entity_type"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])

    # 2. import_staging_customers
    op.create_table(
        "import_staging_customers",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True) if dialect == "postgresql" else None,
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", json_type, nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("tin", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("customer_type", sa.Text(), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("credit_limit", sa.Text(), nullable=True),
        sa.Column("validation_errors", json_type, nullable=True),
        sa.Column("committed_customer_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["committed_customer_id"], ["customers.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_import_staging_customers_batch_id", "import_staging_customers", ["batch_id"]
    )

    # 3. import_staging_products
    op.create_table(
        "import_staging_products",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True) if dialect == "postgresql" else None,
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", json_type, nullable=False),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Text(), nullable=True),
        sa.Column("product_type", sa.Text(), nullable=True),
        sa.Column("uom", sa.Text(), nullable=True),
        sa.Column("list_price", sa.Text(), nullable=True),
        sa.Column("reorder_point", sa.Text(), nullable=True),
        sa.Column("tax_rate_id", sa.Text(), nullable=True),
        sa.Column("validation_errors", json_type, nullable=True),
        sa.Column("committed_product_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["committed_product_id"], ["products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_import_staging_products_batch_id", "import_staging_products", ["batch_id"])

    # 4. import_staging_contacts
    op.create_table(
        "import_staging_contacts",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True) if dialect == "postgresql" else None,
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", json_type, nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("validation_errors", json_type, nullable=True),
        sa.Column("committed_contact_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["committed_contact_id"], ["contacts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_import_staging_contacts_batch_id", "import_staging_contacts", ["batch_id"])

    # 5. Seed import permissions
    existing_perms = {
        row[0] for row in bind.execute(sa.text("SELECT code FROM permissions")).fetchall()
    }

    new_permissions = [
        {
            "code": "import:read",
            "description": "View import batches and staging status",
            "module": "imports",
        },
        {
            "code": "import:upload",
            "description": "Upload CSV files to import staging",
            "module": "imports",
        },
        {
            "code": "import:commit",
            "description": "Commit validated staged records into operational ERP",
            "module": "imports",
        },
    ]

    for perm in new_permissions:
        if perm["code"] not in existing_perms:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (code, description, module) "
                    "VALUES (:code, :description, :module)"
                ),
                perm,
            )

    # 6. Fetch updated permission IDs and role IDs
    perm_rows = bind.execute(sa.text("SELECT id, code FROM permissions")).fetchall()
    perm_map = {row[1]: row[0] for row in perm_rows}

    role_rows = bind.execute(sa.text("SELECT id, code FROM roles")).fetchall()
    role_map = {row[1]: row[0] for row in role_rows}

    def grant_if_missing(role_code: str, perm_code: str, scope: str = "all"):
        if role_code not in role_map or perm_code not in perm_map:
            return
        role_id = role_map[role_code]
        perm_id = perm_map[perm_code]

        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :perm_id"
            ),
            {"role_id": role_id, "perm_id": perm_id},
        ).fetchone()

        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, scope) "
                    "VALUES (:role_id, :perm_id, :scope)"
                ),
                {"role_id": role_id, "perm_id": perm_id, "scope": scope},
            )

    # Admin
    grant_if_missing("admin", "import:read", "all")
    grant_if_missing("admin", "import:upload", "all")
    grant_if_missing("admin", "import:commit", "all")

    # Management
    grant_if_missing("management", "import:read", "all")
    grant_if_missing("management", "import:upload", "all")
    grant_if_missing("management", "import:commit", "all")

    # Sales Manager
    grant_if_missing("sales_manager", "import:read", "all")
    grant_if_missing("sales_manager", "import:upload", "all")
    grant_if_missing("sales_manager", "import:commit", "all")

    # Inventory Manager
    grant_if_missing("inventory_manager", "import:read", "all")
    grant_if_missing("inventory_manager", "import:upload", "all")
    grant_if_missing("inventory_manager", "import:commit", "all")

    # Sales Rep
    grant_if_missing("sales_rep", "import:read", "own")


def downgrade() -> None:
    bind = op.get_bind()

    # Remove role permissions
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN ("
            "SELECT id FROM permissions WHERE code IN ('import:read', 'import:upload', 'import:commit'))"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM permissions WHERE code IN ('import:read', 'import:upload', 'import:commit')"
        )
    )

    op.drop_table("import_staging_contacts")
    op.drop_table("import_staging_products")
    op.drop_table("import_staging_customers")
    op.drop_table("import_batches")
