"""V1.7 schema: AI Assistant permissions (assistant:use) for ERP Copilot

Revision ID: 0016_assistant_permissions
Revises: 0015_analytics_permissions
Create Date: 2026-10-12 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_assistant_permissions"
down_revision: str | None = "0015_analytics_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Ensure assistant:use exists in permissions table
    existing_perms = {
        row[0] for row in bind.execute(sa.text("SELECT code FROM permissions")).fetchall()
    }

    if "assistant:use" not in existing_perms:
        bind.execute(
            sa.text(
                "INSERT INTO permissions (code, description, module) "
                "VALUES (:code, :description, :module)"
            ),
            {
                "code": "assistant:use",
                "description": "Access ERP AI Copilot assistant, record summaries, and drafting",
                "module": "assistant",
            },
        )

    # 2. Fetch permission ID and role IDs
    perm_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'assistant:use'")
    ).fetchone()
    if not perm_row:
        return
    perm_id = perm_row[0]

    role_rows = bind.execute(sa.text("SELECT id, code FROM roles")).fetchall()
    role_map = {row[1]: row[0] for row in role_rows}

    def grant_if_missing(role_code: str, scope: str = "all"):
        if role_code not in role_map:
            return
        role_id = role_map[role_code]

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

    # 3. Grant assistant:use to all operational and business roles
    grant_if_missing("admin", "all")
    grant_if_missing("management", "all")
    grant_if_missing("sales", "own")
    grant_if_missing("finance", "all")
    grant_if_missing("inventory", "all")
    grant_if_missing("purchasing", "all")


def downgrade() -> None:
    bind = op.get_bind()
    perm_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'assistant:use'")
    ).fetchone()
    if perm_row:
        perm_id = perm_row[0]
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :perm_id"),
            {"perm_id": perm_id},
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE id = :perm_id"),
            {"perm_id": perm_id},
        )
