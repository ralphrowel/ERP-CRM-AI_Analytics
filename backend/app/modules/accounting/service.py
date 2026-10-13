"""General Ledger Service Layer (Roadmap §V2.1)
Manages Chart of Accounts, Fiscal Periods, Double-Entry Journal Entries, and Trial Balance generation.
Strict Invariants:
1. SUM(debit) == SUM(credit) enforced for all posted entries.
2. Posted journal entries are strictly immutable (ADR-0016).
3. Reversals must be executed via distinct counter-entries.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, SystemClock
from app.core.errors import BusinessRuleException, NotFoundException
from app.core.money import round_money
from app.core.numbering import generate_next_number
from app.modules.accounting.models import (
    Account,
    FiscalPeriod,
    JournalEntry,
    JournalEntryLine,
)
from app.modules.accounting.schemas import (
    AccountCreatePayload,
    BalanceSheetReport,
    FinancialStatementItem,
    FiscalPeriodCreatePayload,
    IncomeStatementReport,
    JournalEntryCreatePayload,
    JournalEntryLinePayload,
    TrialBalanceAccountRow,
    TrialBalanceReport,
)

DEFAULT_COA = [
    {"code": "1110", "name": "Cash and Cash Equivalents", "type": "asset", "normal": "debit"},
    {"code": "1120", "name": "Cash in Bank - Operating", "type": "asset", "normal": "debit"},
    {
        "code": "1200",
        "name": "Accounts Receivable",
        "type": "asset",
        "normal": "debit",
        "reconcilable": True,
    },
    {"code": "1300", "name": "Merchandise Inventory", "type": "asset", "normal": "debit"},
    {"code": "1400", "name": "Input VAT (12%)", "type": "asset", "normal": "debit"},
    {
        "code": "2100",
        "name": "Accounts Payable",
        "type": "liability",
        "normal": "credit",
        "reconcilable": True,
    },
    {
        "code": "2150",
        "name": "Goods Received Not Invoiced (GRNI)",
        "type": "liability",
        "normal": "credit",
    },
    {"code": "2210", "name": "Output VAT Payable (12%)", "type": "liability", "normal": "credit"},
    {"code": "3100", "name": "Owner's Equity / Capital", "type": "equity", "normal": "credit"},
    {"code": "3200", "name": "Retained Earnings", "type": "equity", "normal": "credit"},
    {"code": "4100", "name": "Sales Revenue", "type": "revenue", "normal": "credit"},
    {"code": "4200", "name": "Sales Discounts", "type": "revenue", "normal": "debit"},
    {"code": "5100", "name": "Cost of Goods Sold (COGS)", "type": "expense", "normal": "debit"},
    {"code": "6100", "name": "Operating Expenses", "type": "expense", "normal": "debit"},
]


class GLService:
    """Service orchestrating double-entry General Ledger operations."""

    def __init__(self, db: Session, clock: Clock | None = None):
        self.db = db
        self.clock = clock or SystemClock()

    # =========================================================================
    # 1. Chart of Accounts Management
    # =========================================================================

    def seed_default_chart_of_accounts(self, creator_id: int | None = None) -> list[Account]:
        """Seeds standard enterprise Philippine Chart of Accounts baseline."""
        accounts = []
        now = self.clock.now()
        for def_acc in DEFAULT_COA:
            existing = self.db.execute(
                select(Account).where(Account.code == def_acc["code"])
            ).scalar_one_or_none()
            if not existing:
                acc = Account(
                    code=def_acc["code"],
                    name=def_acc["name"],
                    account_type=def_acc["type"],
                    normal_balance=def_acc["normal"],
                    is_reconcilable=def_acc.get("reconcilable", False),
                    is_active=True,
                    created_by=creator_id,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(acc)
                accounts.append(acc)
            else:
                accounts.append(existing)
        self.db.commit()
        return accounts

    def create_account(self, data: AccountCreatePayload, creator_id: int | None = None) -> Account:
        """Creates a new General Ledger account."""
        existing = self.db.execute(
            select(Account).where(Account.code == data.code)
        ).scalar_one_or_none()
        if existing:
            raise BusinessRuleException(
                code="ACCOUNT_CODE_EXISTS",
                detail=f"Account with code '{data.code}' already exists.",
            )

        if data.parent_id:
            parent = self.db.get(Account, data.parent_id)
            if not parent:
                raise NotFoundException(detail="Parent account not found.")

        now = self.clock.now()
        account = Account(
            code=data.code,
            name=data.name,
            account_type=data.account_type,
            normal_balance=data.normal_balance,
            description=data.description,
            parent_id=data.parent_id,
            is_reconcilable=data.is_reconcilable,
            is_active=True,
            created_by=creator_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def get_account_by_code(self, code: str) -> Account:
        """Finds account by code or raises NotFoundException."""
        acc = self.db.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
        if not acc:
            raise NotFoundException(detail=f"Account with code '{code}' not found.")
        return acc

    def list_accounts(self, is_active: bool | None = None) -> list[Account]:
        """Lists accounts ordered by account code."""
        stmt = select(Account)
        if is_active is not None:
            stmt = stmt.where(Account.is_active == is_active)
        stmt = stmt.order_by(Account.code)
        return list(self.db.execute(stmt).scalars().all())

    # =========================================================================
    # 2. Fiscal Periods
    # =========================================================================

    def create_fiscal_period(
        self, data: FiscalPeriodCreatePayload, creator_id: int | None = None
    ) -> FiscalPeriod:
        """Creates a fiscal period."""
        if data.start_date > data.end_date:
            raise BusinessRuleException(
                code="INVALID_PERIOD_DATES",
                detail="Period start date must be before or equal to end date.",
            )

        existing = self.db.execute(
            select(FiscalPeriod).where(FiscalPeriod.period_name == data.period_name)
        ).scalar_one_or_none()
        if existing:
            raise BusinessRuleException(
                code="PERIOD_NAME_EXISTS",
                detail=f"Fiscal period '{data.period_name}' already exists.",
            )

        now = self.clock.now()
        period = FiscalPeriod(
            period_name=data.period_name,
            start_date=data.start_date,
            end_date=data.end_date,
            status="open",
            created_by=creator_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(period)
        self.db.commit()
        self.db.refresh(period)
        return period

    def get_open_period_for_date(self, dt: date) -> FiscalPeriod | None:
        """Finds open fiscal period containing date."""
        stmt = select(FiscalPeriod).where(
            FiscalPeriod.start_date <= dt,
            FiscalPeriod.end_date >= dt,
            FiscalPeriod.status == "open",
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def close_fiscal_period(self, period_id: int, user_id: int | None = None) -> FiscalPeriod:
        """Closes fiscal period, preventing new postings."""
        period = self.db.get(FiscalPeriod, period_id)
        if not period:
            raise NotFoundException(detail="Fiscal period not found.")
        period.status = "closed"
        period.updated_by = user_id
        self.db.commit()
        self.db.refresh(period)
        return period

    # =========================================================================
    # 3. Double-Entry Journal Entries
    # =========================================================================

    def create_journal_entry(
        self,
        data: JournalEntryCreatePayload,
        user_id: int | None = None,
        auto_post: bool = False,
    ) -> JournalEntry:
        """Creates a new journal entry voucher in draft or posted status."""
        if len(data.lines) < 2:
            raise BusinessRuleException(
                code="INSUFFICIENT_JOURNAL_LINES",
                detail="Journal entry must contain at least two posting lines (debit and credit).",
            )

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")

        # Validate lines and calculate totals
        line_objects = []
        for idx, line_data in enumerate(data.lines, start=1):
            acc = self.db.get(Account, line_data.account_id)
            if not acc:
                raise NotFoundException(detail=f"Account id {line_data.account_id} not found.")
            if not acc.is_active:
                raise BusinessRuleException(
                    code="ACCOUNT_INACTIVE",
                    detail=f"Account '{acc.code} - {acc.name}' is inactive and cannot receive postings.",
                )

            d_amt = round_money(line_data.debit_amount)
            c_amt = round_money(line_data.credit_amount)

            if d_amt < Decimal("0.00") or c_amt < Decimal("0.00"):
                raise BusinessRuleException(
                    code="NEGATIVE_POSTING_AMOUNT",
                    detail="Debit and credit amounts must be non-negative.",
                )

            if d_amt == Decimal("0.00") and c_amt == Decimal("0.00"):
                raise BusinessRuleException(
                    code="ZERO_POSTING_AMOUNT",
                    detail=f"Line {idx} must have either a debit or credit amount greater than 0.00.",
                )

            total_debit += d_amt
            total_credit += c_amt

            line_obj = JournalEntryLine(
                line_no=idx,
                account_id=acc.id,
                debit_amount=d_amt,
                credit_amount=c_amt,
                description=line_data.description or data.description,
            )
            line_objects.append(line_obj)

        entry_no = generate_next_number(self.db, "journal_entry", clock=self.clock)

        now = self.clock.now()
        entry = JournalEntry(
            entry_no=entry_no,
            posting_date=data.posting_date,
            source_document_type=data.source_document_type,
            source_document_id=data.source_document_id,
            status="draft",
            total_debit=round_money(total_debit),
            total_credit=round_money(total_credit),
            description=data.description,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        entry.lines.extend(line_objects)

        self.db.add(entry)
        self.db.flush()

        if auto_post:
            self._validate_and_post_entry(entry, user_id=user_id)

        self.db.commit()
        self.db.refresh(entry)
        return entry

    def _validate_and_post_entry(self, entry: JournalEntry, user_id: int | None = None) -> None:
        """Internal worker validating balance and posting entry."""
        if entry.status == "posted":
            return

        # 1. Exact balance verification (Roadmap §V2.1 Invariant 1)
        diff = abs(entry.total_debit - entry.total_credit)
        if diff != Decimal("0.00") or entry.total_debit == Decimal("0.00"):
            raise BusinessRuleException(
                code="IMBALANCED_JOURNAL_ENTRY",
                detail=(
                    f"Journal entry is not balanced. "
                    f"Total Debits: {entry.total_debit}, Total Credits: {entry.total_credit} (Difference: {diff})."
                ),
            )

        # 2. Fiscal period validation
        period = self.get_open_period_for_date(entry.posting_date)
        if not period:
            # Fallback check if any open period exists or auto-open current year
            any_period = self.db.execute(select(FiscalPeriod)).first()
            if any_period:
                raise BusinessRuleException(
                    code="CLOSED_OR_MISSING_FISCAL_PERIOD",
                    detail=f"No open fiscal period found for posting date {entry.posting_date}.",
                )
        else:
            entry.fiscal_period_id = period.id

        entry.status = "posted"
        entry.updated_by = user_id

    def post_journal_entry(self, entry_id: int, user_id: int | None = None) -> JournalEntry:
        """Posts a draft journal entry. Once posted, entry becomes immutable."""
        entry = self.db.get(JournalEntry, entry_id)
        if not entry:
            raise NotFoundException(detail="Journal entry not found.")

        if entry.status == "posted":
            raise BusinessRuleException(
                code="ALREADY_POSTED",
                detail=f"Journal entry '{entry.entry_no}' is already posted.",
            )

        if entry.status == "reversed":
            raise BusinessRuleException(
                code="ENTRY_REVERSED",
                detail=f"Journal entry '{entry.entry_no}' is reversed and cannot be posted.",
            )

        self._validate_and_post_entry(entry, user_id=user_id)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def reverse_journal_entry(
        self,
        entry_id: int,
        reason: str,
        user_id: int | None = None,
    ) -> JournalEntry:
        """
        Executes formal reversal of a posted entry (ADR-0016).
        Creates an offsetting counter-entry and marks original as 'reversed'.
        """
        original = self.db.get(JournalEntry, entry_id)
        if not original:
            raise NotFoundException(detail="Journal entry not found.")

        if original.status != "posted":
            raise BusinessRuleException(
                code="CANNOT_REVERSE_UNPOSTED_ENTRY",
                detail=f"Only posted journal entries can be reversed. Current status is '{original.status}'.",
            )

        reversal_lines = []
        for line in original.lines:
            reversal_lines.append(
                JournalEntryLinePayload(
                    account_id=line.account_id,
                    debit_amount=line.credit_amount,  # Swapped
                    credit_amount=line.debit_amount,  # Swapped
                    description=f"Reversal of line {line.line_no}: {line.description or ''}".strip(),
                )
            )

        posting_date = self.clock.now().date() if hasattr(self.clock, "now") else date.today()

        reversal_payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Reversal of {original.entry_no}: {reason}",
            source_document_type="journal_entry_reversal",
            source_document_id=original.id,
            lines=reversal_lines,
        )

        reversal_entry = self.create_journal_entry(
            data=reversal_payload,
            user_id=user_id,
            auto_post=True,
        )
        reversal_entry.reversal_of_id = original.id

        original.status = "reversed"
        original.updated_by = user_id
        self.db.commit()
        self.db.refresh(original)
        self.db.refresh(reversal_entry)
        return reversal_entry

    # =========================================================================
    # 4. Financial Reporting & Trial Balance
    # =========================================================================

    def generate_trial_balance(self, as_of_date: date) -> TrialBalanceReport:
        """
        Generates formal Trial Balance aggregating all posted journal entries up to as_of_date.
        Verifies double-entry equilibrium: total debits == total credits.
        """
        # Sum debits and credits per account from posted journal entries
        stmt = (
            select(
                Account.id.label("account_id"),
                Account.code.label("code"),
                Account.name.label("name"),
                Account.account_type.label("account_type"),
                Account.normal_balance.label("normal_balance"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")).label(
                    "total_debit"
                ),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")).label(
                    "total_credit"
                ),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id, isouter=True)
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.status == "posted")
                & (JournalEntry.posting_date <= as_of_date),
                isouter=True,
            )
            .where(Account.is_active == True)  # noqa: E712
            .group_by(
                Account.id, Account.code, Account.name, Account.account_type, Account.normal_balance
            )
            .order_by(Account.code)
        )

        rows_data = self.db.execute(stmt).all()

        report_rows = []
        grand_total_debits = Decimal("0.00")
        grand_total_credits = Decimal("0.00")

        for r in rows_data:
            d_sum = round_money(Decimal(str(r.total_debit)))
            c_sum = round_money(Decimal(str(r.total_credit)))

            # Net balance according to normal balance
            if r.normal_balance == "debit":
                net = d_sum - c_sum
            else:
                net = c_sum - d_sum

            grand_total_debits += d_sum
            grand_total_credits += c_sum

            report_rows.append(
                TrialBalanceAccountRow(
                    account_id=r.account_id,
                    code=r.code,
                    name=r.name,
                    account_type=r.account_type,
                    normal_balance=r.normal_balance,
                    total_debit=d_sum,
                    total_credit=c_sum,
                    net_balance=net,
                )
            )

        diff = abs(grand_total_debits - grand_total_credits)
        is_balanced = diff == Decimal("0.00")

        return TrialBalanceReport(
            as_of_date=as_of_date,
            rows=report_rows,
            total_debits=grand_total_debits,
            total_credits=grand_total_credits,
            is_balanced=is_balanced,
        )

    # =========================================================================
    # 5. Automated Subledger-to-GL Integration (Milestone V2.2)
    # =========================================================================

    def ensure_account(self, code: str) -> Account:
        """Finds account by code, auto-seeding default Philippine COA if needed."""
        acc = self.db.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
        if not acc:
            self.seed_default_chart_of_accounts()
            acc = self.db.execute(select(Account).where(Account.code == code)).scalar_one_or_none()
        if not acc:
            raise NotFoundException(detail=f"Account with code '{code}' not found.")
        return acc

    def post_invoice_to_gl(
        self,
        invoice_id: int,
        invoice_no: str,
        customer_name: str,
        posting_date: date,
        subtotal: Decimal,
        tax_total: Decimal,
        grand_total: Decimal,
        user_id: int | None = None,
    ) -> JournalEntry:
        """
        Subledger hook: posts sales invoice to General Ledger.
        Dr Accounts Receivable (1200): grand_total
        Cr Sales Revenue (4100): subtotal
        Cr Output VAT Payable (2210): tax_total (if > 0)
        """
        existing = self.db.execute(
            select(JournalEntry).where(
                JournalEntry.source_document_type == "invoice",
                JournalEntry.source_document_id == invoice_id,
                JournalEntry.status == "posted",
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        ar = self.ensure_account("1200")
        rev = self.ensure_account("4100")
        vat = self.ensure_account("2210")

        lines = [
            JournalEntryLinePayload(
                account_id=ar.id,
                debit_amount=round_money(grand_total),
                credit_amount=Decimal("0.00"),
                description=f"AR - {customer_name}",
            ),
            JournalEntryLinePayload(
                account_id=rev.id,
                debit_amount=Decimal("0.00"),
                credit_amount=round_money(subtotal),
                description="Sales Revenue",
            ),
        ]
        if round_money(tax_total) > Decimal("0.00"):
            lines.append(
                JournalEntryLinePayload(
                    account_id=vat.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=round_money(tax_total),
                    description="Output VAT (12%)",
                )
            )

        payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Sales Invoice {invoice_no} to {customer_name}",
            source_document_type="invoice",
            source_document_id=invoice_id,
            lines=lines,
        )
        return self.create_journal_entry(payload, user_id=user_id, auto_post=True)

    def post_payment_to_gl(
        self,
        payment_id: int,
        payment_no: str,
        posting_date: date,
        amount_allocated: Decimal,
        customer_name: str | None = None,
        user_id: int | None = None,
    ) -> JournalEntry | None:
        """
        Subledger hook: posts customer payment allocation to General Ledger.
        Dr Cash in Bank (1120): amount_allocated
        Cr Accounts Receivable (1200): amount_allocated
        """
        if round_money(amount_allocated) <= Decimal("0.00"):
            return None

        bank = self.ensure_account("1120")
        ar = self.ensure_account("1200")

        lines = [
            JournalEntryLinePayload(
                account_id=bank.id,
                debit_amount=round_money(amount_allocated),
                credit_amount=Decimal("0.00"),
                description=f"Collection: {payment_no}",
            ),
            JournalEntryLinePayload(
                account_id=ar.id,
                debit_amount=Decimal("0.00"),
                credit_amount=round_money(amount_allocated),
                description=f"AR settlement{f' - {customer_name}' if customer_name else ''}",
            ),
        ]

        payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Payment {payment_no} collection & allocation",
            source_document_type="payment",
            source_document_id=payment_id,
            lines=lines,
        )
        return self.create_journal_entry(payload, user_id=user_id, auto_post=True)

    def post_credit_note_to_gl(
        self,
        credit_note_id: int,
        credit_note_no: str,
        customer_name: str,
        posting_date: date,
        subtotal: Decimal,
        tax_total: Decimal,
        grand_total: Decimal,
        user_id: int | None = None,
    ) -> JournalEntry:
        """
        Subledger hook: posts sales credit note to General Ledger.
        Dr Sales Discounts / Returns (4200): subtotal
        Dr Output VAT Payable (2210): tax_total (if > 0)
        Cr Accounts Receivable (1200): grand_total
        """
        existing = self.db.execute(
            select(JournalEntry).where(
                JournalEntry.source_document_type == "credit_note",
                JournalEntry.source_document_id == credit_note_id,
                JournalEntry.status == "posted",
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        ar = self.ensure_account("1200")
        disc = self.ensure_account("4200")
        vat = self.ensure_account("2210")

        lines = [
            JournalEntryLinePayload(
                account_id=disc.id,
                debit_amount=round_money(subtotal),
                credit_amount=Decimal("0.00"),
                description=f"Credit adjustment - {credit_note_no}",
            ),
        ]
        if round_money(tax_total) > Decimal("0.00"):
            lines.append(
                JournalEntryLinePayload(
                    account_id=vat.id,
                    debit_amount=round_money(tax_total),
                    credit_amount=Decimal("0.00"),
                    description="Output VAT reversal",
                )
            )
        lines.append(
            JournalEntryLinePayload(
                account_id=ar.id,
                debit_amount=Decimal("0.00"),
                credit_amount=round_money(grand_total),
                description=f"AR credit - {customer_name}",
            )
        )

        payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Credit Note {credit_note_no} to {customer_name}",
            source_document_type="credit_note",
            source_document_id=credit_note_id,
            lines=lines,
        )
        return self.create_journal_entry(payload, user_id=user_id, auto_post=True)

    def post_supplier_invoice_to_gl(
        self,
        invoice_id: int,
        invoice_no: str,
        supplier_name: str,
        posting_date: date,
        subtotal: Decimal,
        tax_total: Decimal,
        grand_total: Decimal,
        user_id: int | None = None,
    ) -> JournalEntry:
        """
        Subledger hook: posts approved supplier invoice / bill to General Ledger.
        Dr Goods Received Not Invoiced / Purchases (2150): subtotal
        Dr Input VAT (1400): tax_total (if > 0)
        Cr Accounts Payable (2100): grand_total
        """
        existing = self.db.execute(
            select(JournalEntry).where(
                JournalEntry.source_document_type == "supplier_invoice",
                JournalEntry.source_document_id == invoice_id,
                JournalEntry.status == "posted",
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        grni = self.ensure_account("2150")
        input_vat = self.ensure_account("1400")
        ap = self.ensure_account("2100")

        lines = [
            JournalEntryLinePayload(
                account_id=grni.id,
                debit_amount=round_money(subtotal),
                credit_amount=Decimal("0.00"),
                description=f"Goods/Services Billed - {supplier_name}",
            ),
        ]
        if round_money(tax_total) > Decimal("0.00"):
            lines.append(
                JournalEntryLinePayload(
                    account_id=input_vat.id,
                    debit_amount=round_money(tax_total),
                    credit_amount=Decimal("0.00"),
                    description="Input VAT (12%)",
                )
            )
        lines.append(
            JournalEntryLinePayload(
                account_id=ap.id,
                debit_amount=Decimal("0.00"),
                credit_amount=round_money(grand_total),
                description=f"AP - {supplier_name}",
            )
        )

        payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Supplier Bill {invoice_no} from {supplier_name}",
            source_document_type="supplier_invoice",
            source_document_id=invoice_id,
            lines=lines,
        )
        return self.create_journal_entry(payload, user_id=user_id, auto_post=True)

    def post_supplier_payment_to_gl(
        self,
        payment_id: int,
        payment_no: str,
        supplier_name: str,
        posting_date: date,
        amount: Decimal,
        user_id: int | None = None,
    ) -> JournalEntry | None:
        """
        Subledger hook: posts supplier payment disbursement to General Ledger.
        Dr Accounts Payable (2100): amount
        Cr Cash in Bank (1120): amount
        """
        if round_money(amount) <= Decimal("0.00"):
            return None

        ap = self.ensure_account("2100")
        bank = self.ensure_account("1120")

        lines = [
            JournalEntryLinePayload(
                account_id=ap.id,
                debit_amount=round_money(amount),
                credit_amount=Decimal("0.00"),
                description=f"AP disbursement - {supplier_name}",
            ),
            JournalEntryLinePayload(
                account_id=bank.id,
                debit_amount=Decimal("0.00"),
                credit_amount=round_money(amount),
                description=f"Disbursement {payment_no}",
            ),
        ]

        payload = JournalEntryCreatePayload(
            posting_date=posting_date,
            description=f"Supplier Payment {payment_no} to {supplier_name}",
            source_document_type="supplier_payment",
            source_document_id=payment_id,
            lines=lines,
        )
        return self.create_journal_entry(payload, user_id=user_id, auto_post=True)

    def reverse_source_document_entries(
        self,
        source_document_type: str,
        source_document_id: int,
        reason: str,
        user_id: int | None = None,
    ) -> list[JournalEntry]:
        """Reverses all active posted journal entries for a source document."""
        entries = (
            self.db.execute(
                select(JournalEntry).where(
                    JournalEntry.source_document_type == source_document_type,
                    JournalEntry.source_document_id == source_document_id,
                    JournalEntry.status == "posted",
                )
            )
            .scalars()
            .all()
        )

        reversals = []
        for e in entries:
            rev = self.reverse_journal_entry(e.id, reason=reason, user_id=user_id)
            reversals.append(rev)
        return reversals

    # =========================================================================
    # 6. Financial Reporting: Balance Sheet & Income Statement
    # =========================================================================

    def generate_income_statement(
        self,
        start_date: date,
        end_date: date,
    ) -> IncomeStatementReport:
        """
        Generates formal Income Statement (Statement of Comprehensive Income / P&L)
        for transactions within the specified date range.
        Net Income = Revenue - COGS - Operating Expenses
        """
        stmt = (
            select(
                Account.id.label("account_id"),
                Account.code.label("code"),
                Account.name.label("name"),
                Account.account_type.label("account_type"),
                Account.normal_balance.label("normal_balance"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")).label(
                    "total_debit"
                ),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")).label(
                    "total_credit"
                ),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id, isouter=True)
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.status == "posted")
                & (JournalEntry.posting_date >= start_date)
                & (JournalEntry.posting_date <= end_date),
                isouter=True,
            )
            .where(
                Account.is_active == True,  # noqa: E712
                Account.account_type.in_(["revenue", "expense"]),
            )
            .group_by(
                Account.id, Account.code, Account.name, Account.account_type, Account.normal_balance
            )
            .order_by(Account.code)
        )

        rows = self.db.execute(stmt).all()

        revenue_items: list[FinancialStatementItem] = []
        cogs_items: list[FinancialStatementItem] = []
        expense_items: list[FinancialStatementItem] = []

        total_revenue = Decimal("0.00")
        total_cogs = Decimal("0.00")
        total_expenses = Decimal("0.00")

        for r in rows:
            d_sum = round_money(Decimal(str(r.total_debit)))
            c_sum = round_money(Decimal(str(r.total_credit)))

            if r.account_type == "revenue":
                amount = c_sum - d_sum
                total_revenue += amount
                revenue_items.append(
                    FinancialStatementItem(
                        account_id=r.account_id,
                        code=r.code,
                        name=r.name,
                        amount=amount,
                    )
                )
            elif r.account_type == "expense":
                amount = d_sum - c_sum
                if r.code == "5100" or "COGS" in r.name:
                    total_cogs += amount
                    cogs_items.append(
                        FinancialStatementItem(
                            account_id=r.account_id,
                            code=r.code,
                            name=r.name,
                            amount=amount,
                        )
                    )
                else:
                    total_expenses += amount
                    expense_items.append(
                        FinancialStatementItem(
                            account_id=r.account_id,
                            code=r.code,
                            name=r.name,
                            amount=amount,
                        )
                    )

        gross_profit = total_revenue - total_cogs
        net_income = gross_profit - total_expenses

        return IncomeStatementReport(
            start_date=start_date,
            end_date=end_date,
            revenue_items=revenue_items,
            total_revenue=round_money(total_revenue),
            cogs_items=cogs_items,
            total_cogs=round_money(total_cogs),
            gross_profit=round_money(gross_profit),
            expense_items=expense_items,
            total_expenses=round_money(total_expenses),
            net_income=round_money(net_income),
        )

    def generate_balance_sheet(self, as_of_date: date) -> BalanceSheetReport:
        """
        Generates formal Balance Sheet (Statement of Financial Position) as of target date.
        Strict Invariant: Total Assets == Total Liabilities + Total Equity.
        """
        stmt = (
            select(
                Account.id.label("account_id"),
                Account.code.label("code"),
                Account.name.label("name"),
                Account.account_type.label("account_type"),
                Account.normal_balance.label("normal_balance"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal("0.00")).label(
                    "total_debit"
                ),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal("0.00")).label(
                    "total_credit"
                ),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id, isouter=True)
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.status == "posted")
                & (JournalEntry.posting_date <= as_of_date),
                isouter=True,
            )
            .where(Account.is_active == True)  # noqa: E712
            .group_by(
                Account.id, Account.code, Account.name, Account.account_type, Account.normal_balance
            )
            .order_by(Account.code)
        )

        rows = self.db.execute(stmt).all()

        asset_items: list[FinancialStatementItem] = []
        liability_items: list[FinancialStatementItem] = []
        equity_items: list[FinancialStatementItem] = []

        total_assets = Decimal("0.00")
        total_liabilities = Decimal("0.00")
        total_equity_base = Decimal("0.00")

        total_revenue_to_date = Decimal("0.00")
        total_expense_to_date = Decimal("0.00")

        for r in rows:
            d_sum = round_money(Decimal(str(r.total_debit)))
            c_sum = round_money(Decimal(str(r.total_credit)))

            if r.account_type == "asset":
                amount = d_sum - c_sum
                total_assets += amount
                asset_items.append(
                    FinancialStatementItem(
                        account_id=r.account_id, code=r.code, name=r.name, amount=amount
                    )
                )
            elif r.account_type == "liability":
                amount = c_sum - d_sum
                total_liabilities += amount
                liability_items.append(
                    FinancialStatementItem(
                        account_id=r.account_id, code=r.code, name=r.name, amount=amount
                    )
                )
            elif r.account_type == "equity":
                amount = c_sum - d_sum
                total_equity_base += amount
                equity_items.append(
                    FinancialStatementItem(
                        account_id=r.account_id, code=r.code, name=r.name, amount=amount
                    )
                )
            elif r.account_type == "revenue":
                total_revenue_to_date += c_sum - d_sum
            elif r.account_type == "expense":
                total_expense_to_date += d_sum - c_sum

        current_period_net_income = round_money(total_revenue_to_date - total_expense_to_date)
        total_equity = round_money(total_equity_base + current_period_net_income)
        total_liabilities_and_equity = round_money(total_liabilities + total_equity)
        is_balanced = abs(total_assets - total_liabilities_and_equity) == Decimal("0.00")

        return BalanceSheetReport(
            as_of_date=as_of_date,
            assets=asset_items,
            total_assets=round_money(total_assets),
            liabilities=liability_items,
            total_liabilities=round_money(total_liabilities),
            equity=equity_items,
            current_period_net_income=current_period_net_income,
            total_equity=total_equity,
            total_liabilities_and_equity=total_liabilities_and_equity,
            is_balanced=is_balanced,
        )
