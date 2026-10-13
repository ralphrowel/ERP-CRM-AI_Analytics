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
