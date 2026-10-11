"""V1.1 schema: Provision Read-Only etl_reader Role

Revision ID: 0014_etl_reader_role
Revises: 0013_import_staging_tables
Create Date: 2026-10-11 17:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_etl_reader_role"
down_revision: str | None = "0013_import_staging_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'etl_reader') THEN
                    CREATE ROLE etl_reader WITH LOGIN PASSWORD 'etl_reader_password';
                END IF;
            END
            $$;
            """
        )
        op.execute("GRANT USAGE ON SCHEMA public TO etl_reader;")
        op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO etl_reader;")
        op.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO etl_reader;"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM etl_reader;"
        )
        op.execute("REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM etl_reader;")
        op.execute("REVOKE USAGE ON SCHEMA public FROM etl_reader;")
        op.execute("DROP ROLE IF EXISTS etl_reader;")
