"""V0.9 schema: Reporting permissions and role mappings

Revision ID: 0012_reporting_permissions
Revises: 0011_audit_log
Create Date: 2026-10-11 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_reporting_permissions"
down_revision: str | None = "0011_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Ensure report:read exists in permissions table
    existing_perms = {
        row[0] for row in bind.execute(sa.text("SELECT code FROM permissions")).fetchall()
    }

    new_permissions = [
        {
            "code": "report:read",
            "description": "View executive reporting dashboard and high-level KPI summaries",
            "module": "reporting",
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

    # 2. Fetch updated permission IDs and role IDs
    perm_rows = bind.execute(sa.text("SELECT id, code FROM permissions")).fetchall()
    perm_map = {row[1]: row[0] for row in perm_rows}

    role_rows = bind.execute(sa.text("SELECT id, code FROM roles")).fetchall()
    role_map = {row[1]: row[0] for row in role_rows}

    # Helper to check if role_permission already exists
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

    # 3. Grant report permissions across roles
    # Admin has all permissions
    grant_if_missing("admin", "report:read", "all")

    # Management has read access across all domains
    grant_if_missing("management", "report:read", "all")
    grant_if_missing("management", "report:sales", "all")
    grant_if_missing("management", "report:financial", "all")
    grant_if_missing("management", "report:inventory", "all")
    grant_if_missing("management", "report:purchasing", "all")

    # Finance
    grant_if_missing("finance", "report:read", "all")
    grant_if_missing("finance", "report:financial", "all")

    # Sales Manager
    grant_if_missing("sales_manager", "report:read", "department")
    grant_if_missing("sales_manager", "report:sales", "department")

    # Sales Rep
    grant_if_missing("sales_rep", "report:read", "own")
    grant_if_missing("sales_rep", "report:sales", "own")

    # Warehouse Staff
    grant_if_missing("warehouse_staff", "report:read", "all")
    grant_if_missing("warehouse_staff", "report:inventory", "all")

    # Purchasing Specialist
    grant_if_missing("purchasing", "report:read", "all")
    grant_if_missing("purchasing", "report:purchasing", "all")


def downgrade() -> None:
    bind = op.get_bind()
    # Remove role_permissions for report:read
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN ("
            "SELECT id FROM permissions WHERE code = 'report:read')"
        )
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = 'report:read'"))
