from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccountType = Literal["asset", "liability", "equity", "revenue", "expense"]
NormalBalance = Literal["debit", "credit"]
PeriodStatus = Literal["open", "closed"]
JournalStatus = Literal["draft", "posted", "reversed"]


class AccountCreatePayload(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., min_length=2, max_length=255)
    account_type: AccountType
    normal_balance: NormalBalance
    description: str | None = None
    parent_id: int | None = None
    is_reconcilable: bool = False


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    account_type: str
    normal_balance: str
    description: str | None = None
    parent_id: int | None = None
    is_active: bool
    is_reconcilable: bool
    created_at: datetime


class FiscalPeriodCreatePayload(BaseModel):
    period_name: str = Field(..., min_length=2, max_length=50)
    start_date: date
    end_date: date


class FiscalPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_name: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime


class JournalEntryLinePayload(BaseModel):
    account_id: int
    debit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    description: str | None = None


class JournalEntryLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_no: int
    account_id: int
    account_code: str | None = None
    account_name: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None = None


class JournalEntryCreatePayload(BaseModel):
    posting_date: date
    description: str = Field(..., min_length=3)
    source_document_type: str | None = None
    source_document_id: int | None = None
    lines: list[JournalEntryLinePayload] = Field(..., min_length=2)


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_no: str
    posting_date: date
    fiscal_period_id: int | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    status: str
    total_debit: Decimal
    total_credit: Decimal
    description: str
    reversal_of_id: int | None = None
    lines: list[JournalEntryLineResponse]
    created_at: datetime


class JournalEntryReversePayload(BaseModel):
    reason: str = Field(..., min_length=3)


class TrialBalanceAccountRow(BaseModel):
    account_id: int
    code: str
    name: str
    account_type: str
    normal_balance: str
    total_debit: Decimal
    total_credit: Decimal
    net_balance: Decimal


class TrialBalanceReport(BaseModel):
    as_of_date: date
    rows: list[TrialBalanceAccountRow]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool


class FinancialStatementItem(BaseModel):
    account_id: int
    code: str
    name: str
    amount: Decimal


class BalanceSheetReport(BaseModel):
    as_of_date: date
    assets: list[FinancialStatementItem]
    total_assets: Decimal
    liabilities: list[FinancialStatementItem]
    total_liabilities: Decimal
    equity: list[FinancialStatementItem]
    current_period_net_income: Decimal
    total_equity: Decimal
    total_liabilities_and_equity: Decimal
    is_balanced: bool


class IncomeStatementReport(BaseModel):
    start_date: date
    end_date: date
    revenue_items: list[FinancialStatementItem]
    total_revenue: Decimal
    cogs_items: list[FinancialStatementItem]
    total_cogs: Decimal
    gross_profit: Decimal
    expense_items: list[FinancialStatementItem]
    total_expenses: Decimal
    net_income: Decimal


# --- Multi-Currency & FX Schemas (Milestone V2.3) ---


class CurrencyCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    name: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=10)
    decimal_places: int = Field(default=2, ge=0, le=4)
    is_base: bool = False
    is_active: bool = True


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    symbol: str
    decimal_places: int
    is_base: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExchangeRateCreate(BaseModel):
    from_currency_code: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    to_currency_code: str = Field(default="PHP", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    effective_date: date
    rate: Decimal = Field(..., gt=Decimal("0.000000"))
    source: str = Field(default="manual", max_length=50)


class ExchangeRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_currency_code: str
    to_currency_code: str
    effective_date: date
    rate: Decimal
    source: str
    created_at: datetime
    updated_at: datetime


class FxConversionRequest(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(default="PHP", min_length=3, max_length=3)
    as_of_date: date | None = None


class FxConversionResponse(BaseModel):
    original_amount: Decimal
    from_currency: str
    to_currency: str
    rate: Decimal
    converted_amount: Decimal
    as_of_date: date
