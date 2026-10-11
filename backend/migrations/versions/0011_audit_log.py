"""V0.8 schema: Full Audit Log and Activity Feed

Revision ID: 0011_audit_log
Revises: 0010_workflow_approvals
Create Date: 2026-10-11 12:50:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0011_audit_log"
down_revision = "0010_workflow_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    ip_type = postgresql.INET() if dialect == "postgresql" else sa.String(length=45)
    json_type = postgresql.JSONB() if dialect == "postgresql" else sa.JSON()

    # 1. Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("changes", json_type, nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("ip_address", ip_type, nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action IN ('create','update','transition','login','login_failed','logout','permission_change','export','ai_tool_call')",
            name="ck_audit_log_action",
        ),
    )
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["entity_type", "entity_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_log_actor",
        "audit_log",
        ["actor_user_id", "occurred_at"],
    )

    # 2. Tamper resistance: erp_app has INSERT, SELECT only (REVOKE UPDATE, DELETE)
    if dialect == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'erp_app') THEN
                    GRANT SELECT, INSERT ON audit_log TO erp_app;
                    REVOKE UPDATE, DELETE ON audit_log FROM erp_app;
                END IF;
            END $$;
            """
        )

    # 3. Seed audit:read permission
    perm_table = sa.table(
        "permissions",
        sa.column("id", sa.BigInteger),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("module", sa.String),
    )
    op.bulk_insert(
        perm_table,
        [
            {
                "code": "audit:read",
                "description": "View tamper-resistant audit logs and activity feeds",
                "module": "audit",
            }
        ],
    )

    # 4. Grant audit:read to administrator and director roles
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.BigInteger),
        sa.column("code", sa.String),
    )
    role_perms_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.BigInteger),
        sa.column("permission_id", sa.BigInteger),
        sa.column("scope", sa.String),
    )

    audit_perm_id = bind.execute(
        sa.select(perm_table.c.id).where(perm_table.c.code == "audit:read")
    ).scalar()

    if audit_perm_id:
        admin_roles = bind.execute(
            sa.select(roles_table.c.id).where(
                roles_table.c.code.in_(["admin", "director", "super_admin"])
            )
        ).fetchall()

        for (r_id,) in admin_roles:
            op.bulk_insert(
                role_perms_table,
                [
                    {
                        "role_id": r_id,
                        "permission_id": audit_perm_id,
                        "scope": "all",
                    }
                ],
            )


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DELETE FROM permissions WHERE code = 'audit:read'")
