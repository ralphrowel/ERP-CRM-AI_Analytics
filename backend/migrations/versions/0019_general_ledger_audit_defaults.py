"""V2.2 fix: Ensure server_default CURRENT_TIMESTAMP on GL audit columns

Revision ID: 0019_gl_audit_defaults
Revises: 0018_general_ledger_core
Create Date: 2026-10-13 14:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_gl_audit_defaults"
down_revision: str | None = "0018_general_ledger_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Set server_default for accounts
    op.alter_column(
        "accounts",
        "created_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "accounts",
        "updated_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )

    # Set server_default for fiscal_periods
    op.alter_column(
        "fiscal_periods",
        "created_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "fiscal_periods",
        "updated_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )

    # Set server_default for journal_entries
    op.alter_column(
        "journal_entries",
        "created_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "journal_entries",
        "updated_at",
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    for table in ("journal_entries", "fiscal_periods", "accounts"):
        op.alter_column(
            table,
            "created_at",
            server_default=None,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        op.alter_column(
            table,
            "updated_at",
            server_default=None,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
