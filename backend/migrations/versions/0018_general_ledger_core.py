"""V2.1 schema: General Ledger core (Chart of Accounts, Fiscal Periods, Journal Entries)

Revision ID: 0018_general_ledger_core
Revises: 0017_events_notifications_outbox
Create Date: 2026-10-13 11:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_general_ledger_core"
down_revision: str | None = "0017_events_notifications_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. accounts table (Chart of Accounts)
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(30), nullable=False),
        sa.Column("normal_balance", sa.String(10), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_reconcilable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')",
            name="ck_accounts_account_type",
        ),
        sa.CheckConstraint(
            "normal_balance IN ('debit', 'credit')",
            name="ck_accounts_normal_balance",
        ),
    )
    op.create_index("ix_accounts_code", "accounts", ["code"])
    op.create_index("ix_accounts_type", "accounts", ["account_type"])

    # 2. fiscal_periods table
    op.create_table(
        "fiscal_periods",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("period_name", sa.String(50), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("start_date <= end_date", name="ck_fiscal_periods_dates"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_fiscal_periods_status"),
    )
    op.create_index("ix_fiscal_periods_dates", "fiscal_periods", ["start_date", "end_date"])

    # 3. journal_entries table
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("entry_no", sa.String(50), nullable=False, unique=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column(
            "fiscal_period_id",
            sa.BigInteger(),
            sa.ForeignKey("fiscal_periods.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("source_document_type", sa.String(50), nullable=True),
        sa.Column("source_document_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("total_debit", sa.Numeric(19, 2), server_default="0.00", nullable=False),
        sa.Column("total_credit", sa.Numeric(19, 2), server_default="0.00", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "reversal_of_id",
            sa.BigInteger(),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'posted', 'reversed')", name="ck_journal_entries_status"
        ),
        sa.CheckConstraint(
            "total_debit >= 0 AND total_credit >= 0", name="ck_journal_entries_totals_non_negative"
        ),
    )
    op.create_index("ix_journal_entries_entry_no", "journal_entries", ["entry_no"])
    op.create_index("ix_journal_entries_posting_date", "journal_entries", ["posting_date"])
    op.create_index(
        "ix_journal_entries_source",
        "journal_entries",
        ["source_document_type", "source_document_id"],
    )

    # 4. journal_entry_lines table
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "journal_entry_id",
            sa.BigInteger(),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("debit_amount", sa.Numeric(19, 2), server_default="0.00", nullable=False),
        sa.Column("credit_amount", sa.Numeric(19, 2), server_default="0.00", nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.CheckConstraint("debit_amount >= 0", name="ck_journal_lines_debit_non_negative"),
        sa.CheckConstraint("credit_amount >= 0", name="ck_journal_lines_credit_non_negative"),
        sa.CheckConstraint(
            "debit_amount > 0 OR credit_amount > 0", name="ck_journal_lines_has_amount"
        ),
        sa.UniqueConstraint("journal_entry_id", "line_no", name="uq_journal_entry_lines_line"),
    )
    op.create_index("ix_journal_lines_entry_id", "journal_entry_lines", ["journal_entry_id"])
    op.create_index("ix_journal_lines_account_id", "journal_entry_lines", ["account_id"])


def downgrade() -> None:
    op.drop_table("journal_entry_lines")
    op.drop_table("journal_entries")
    op.drop_table("fiscal_periods")
    op.drop_table("accounts")
