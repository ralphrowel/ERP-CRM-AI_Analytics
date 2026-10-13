from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin


class Account(Base, AuditMixin):
    """
    Chart of Accounts master (Roadmap §V2.1).
    Classifies all financial activity into Assets, Liabilities, Equity, Revenue, and Expenses.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')",
            name="ck_accounts_account_type",
        ),
        CheckConstraint(
            "normal_balance IN ('debit', 'credit')",
            name="ck_accounts_normal_balance",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    normal_balance: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_reconcilable: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    parent: Mapped["Account | None"] = relationship("Account", remote_side="Account.id")


class FiscalPeriod(Base, AuditMixin):
    """
    Accounting period defining financial boundaries for posting and closing.
    """

    __tablename__ = "fiscal_periods"
    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_fiscal_periods_dates"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_fiscal_periods_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    period_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open", nullable=False
    )


class JournalEntry(Base, AuditMixin, VersionMixin):
    """
    Double-entry General Ledger journal voucher (Roadmap §V2.1).
    Strict balance constraint: SUM(debits) == SUM(credits).
    Once posted, an entry is permanently immutable.
    """

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'posted', 'reversed')",
            name="ck_journal_entries_status",
        ),
        CheckConstraint(
            "total_debit >= 0 AND total_credit >= 0",
            name="ck_journal_entries_totals_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    entry_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    posting_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    fiscal_period_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fiscal_periods.id", ondelete="RESTRICT"), nullable=True
    )
    source_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", nullable=False
    )
    total_debit: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    total_credit: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reversal_of_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )

    fiscal_period: Mapped["FiscalPeriod | None"] = relationship("FiscalPeriod")
    reversal_of: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", remote_side="JournalEntry.id"
    )
    lines: Mapped[list["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.line_no",
    )


class JournalEntryLine(Base):
    """
    Individual debit or credit posting leg within a journal entry.
    """

    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="ck_journal_lines_debit_non_negative"),
        CheckConstraint("credit_amount >= 0", name="ck_journal_lines_credit_non_negative"),
        CheckConstraint(
            "debit_amount > 0 OR credit_amount > 0",
            name="ck_journal_lines_has_amount",
        ),
        UniqueConstraint("journal_entry_id", "line_no", name="uq_journal_entry_lines_line"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["Account"] = relationship("Account")


class Currency(Base, AuditMixin):
    """
    ISO-4217 Currency Master (Roadmap §V2.3).
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # 'PHP', 'USD', 'EUR', etc.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger, default=2, server_default="2", nullable=False
    )
    is_base: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )


class ExchangeRate(Base, AuditMixin):
    """
    Historical and spot foreign exchange rates (Roadmap §V2.3).
    """

    __tablename__ = "fx_rates"
    __table_args__ = (
        CheckConstraint("rate > 0", name="ck_fx_rates_rate_positive"),
        UniqueConstraint(
            "from_currency_code",
            "to_currency_code",
            "effective_date",
            name="uq_fx_rates_pair_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    from_currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    to_currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="manual", server_default="manual", nullable=False
    )

    from_currency: Mapped["Currency"] = relationship("Currency", foreign_keys=[from_currency_code])
    to_currency: Mapped["Currency"] = relationship("Currency", foreign_keys=[to_currency_code])
