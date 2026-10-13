from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.core.errors import NotFoundException
from app.modules.accounting.models import JournalEntry
from app.modules.accounting.schemas import (
    AccountCreatePayload,
    AccountResponse,
    BalanceSheetReport,
    CurrencyCreate,
    CurrencyOut,
    ExchangeRateCreate,
    ExchangeRateOut,
    FiscalPeriodCreatePayload,
    FiscalPeriodResponse,
    FxConversionRequest,
    FxConversionResponse,
    IncomeStatementReport,
    JournalEntryCreatePayload,
    JournalEntryLineResponse,
    JournalEntryResponse,
    JournalEntryReversePayload,
    TrialBalanceReport,
)
from app.modules.accounting.service import GLService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/accounting", tags=["General Ledger & Accounting"])


def get_gl_service(db: Annotated[Session, Depends(get_db)]) -> GLService:
    return GLService(db)


def format_journal_response(entry: JournalEntry) -> JournalEntryResponse:
    lines_out = []
    for line in entry.lines:
        lines_out.append(
            JournalEntryLineResponse(
                id=line.id,
                line_no=line.line_no,
                account_id=line.account_id,
                account_code=line.account.code if line.account else None,
                account_name=line.account.name if line.account else None,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                description=line.description,
            )
        )
    return JournalEntryResponse(
        id=entry.id,
        entry_no=entry.entry_no,
        posting_date=entry.posting_date,
        fiscal_period_id=entry.fiscal_period_id,
        source_document_type=entry.source_document_type,
        source_document_id=entry.source_document_id,
        status=entry.status,
        total_debit=entry.total_debit,
        total_credit=entry.total_credit,
        description=entry.description,
        reversal_of_id=entry.reversal_of_id,
        lines=lines_out,
        created_at=entry.created_at,
    )


# -----------------------------------------------------------------------------
# Chart of Accounts
# -----------------------------------------------------------------------------


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create General Ledger Account",
)
def create_account(
    payload: AccountCreatePayload,
    service: Annotated[GLService, Depends(get_gl_service)],
    user: Annotated[User, Depends(get_current_user)],
    _: Annotated[ScopeContext, Depends(require("accounting:manage"))],
) -> AccountResponse:
    account = service.create_account(payload, creator_id=user.id)
    return AccountResponse.model_validate(account)


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
    summary="List General Ledger Accounts",
)
def list_accounts(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:read"))],
    is_active: bool | None = Query(default=None),
) -> list[AccountResponse]:
    accounts = service.list_accounts(is_active=is_active)
    return [AccountResponse.model_validate(a) for a in accounts]


# -----------------------------------------------------------------------------
# Fiscal Periods
# -----------------------------------------------------------------------------


@router.post(
    "/fiscal-periods",
    response_model=FiscalPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Fiscal Period",
)
def create_fiscal_period(
    payload: FiscalPeriodCreatePayload,
    service: Annotated[GLService, Depends(get_gl_service)],
    user: Annotated[User, Depends(get_current_user)],
    _: Annotated[ScopeContext, Depends(require("accounting:manage"))],
) -> FiscalPeriodResponse:
    period = service.create_fiscal_period(payload, creator_id=user.id)
    return FiscalPeriodResponse.model_validate(period)


# -----------------------------------------------------------------------------
# Journal Entries
# -----------------------------------------------------------------------------


@router.post(
    "/journal-entries",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Journal Entry (Draft)",
)
def create_journal_entry(
    payload: JournalEntryCreatePayload,
    service: Annotated[GLService, Depends(get_gl_service)],
    user: Annotated[User, Depends(get_current_user)],
    _: Annotated[ScopeContext, Depends(require("accounting:entry:create"))],
    auto_post: bool = Query(default=False),
) -> JournalEntryResponse:
    entry = service.create_journal_entry(payload, user_id=user.id, auto_post=auto_post)
    return format_journal_response(entry)


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryResponse,
    summary="Post Journal Entry",
)
def post_journal_entry(
    entry_id: int,
    service: Annotated[GLService, Depends(get_gl_service)],
    user: Annotated[User, Depends(get_current_user)],
    _: Annotated[ScopeContext, Depends(require("accounting:entry:post"))],
) -> JournalEntryResponse:
    entry = service.post_journal_entry(entry_id, user_id=user.id)
    return format_journal_response(entry)


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryResponse,
    summary="Reverse Journal Entry",
)
def reverse_journal_entry(
    entry_id: int,
    payload: JournalEntryReversePayload,
    service: Annotated[GLService, Depends(get_gl_service)],
    user: Annotated[User, Depends(get_current_user)],
    _: Annotated[ScopeContext, Depends(require("accounting:entry:reverse"))],
) -> JournalEntryResponse:
    reversal = service.reverse_journal_entry(entry_id, reason=payload.reason, user_id=user.id)
    return format_journal_response(reversal)


@router.get(
    "/journal-entries/{entry_id}",
    response_model=JournalEntryResponse,
    summary="Get Journal Entry by ID",
)
def get_journal_entry(
    entry_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[ScopeContext, Depends(require("accounting:read"))],
) -> JournalEntryResponse:
    entry = db.get(JournalEntry, entry_id)
    if not entry:
        raise NotFoundException(detail="Journal entry not found.")
    return format_journal_response(entry)


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------


@router.get(
    "/reports/trial-balance",
    response_model=TrialBalanceReport,
    summary="Generate Trial Balance Report",
)
def get_trial_balance(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:report:read"))],
    as_of_date: date = Query(default_factory=date.today),
) -> TrialBalanceReport:
    return service.generate_trial_balance(as_of_date)


@router.get(
    "/reports/balance-sheet",
    response_model=BalanceSheetReport,
    summary="Generate Balance Sheet (Statement of Financial Position)",
)
def get_balance_sheet(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:report:read"))],
    as_of_date: date = Query(default_factory=date.today),
) -> BalanceSheetReport:
    return service.generate_balance_sheet(as_of_date)


@router.get(
    "/reports/income-statement",
    response_model=IncomeStatementReport,
    summary="Generate Income Statement (P&L / Statement of Comprehensive Income)",
)
def get_income_statement(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:report:read"))],
    start_date: date = Query(...),
    end_date: date = Query(...),
) -> IncomeStatementReport:
    return service.generate_income_statement(start_date=start_date, end_date=end_date)


# -----------------------------------------------------------------------------
# Currencies & Foreign Exchange (FX) Endpoints (Milestone V2.3)
# -----------------------------------------------------------------------------


@router.get(
    "/currencies",
    response_model=list[CurrencyOut],
    summary="List Currencies",
)
def list_currencies(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:read"))],
    is_active: bool | None = Query(default=None),
) -> list[CurrencyOut]:
    return [CurrencyOut.model_validate(c) for c in service.list_currencies(is_active=is_active)]


@router.post(
    "/currencies",
    response_model=CurrencyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register Currency",
)
def create_currency(
    payload: CurrencyCreate,
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:manage"))],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CurrencyOut:
    return CurrencyOut.model_validate(service.create_currency(payload, creator_id=current_user.id))


@router.get(
    "/fx-rates",
    summary="Get Prevailing Exchange Rate",
)
def get_exchange_rate(
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:read"))],
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(default="PHP", min_length=3, max_length=3),
    as_of_date: date | None = Query(default=None),
):
    rate = service.get_exchange_rate(from_currency, to_currency, as_of_date=as_of_date)
    return {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "rate": rate,
        "as_of_date": as_of_date or date.today(),
    }


@router.post(
    "/fx-rates",
    response_model=ExchangeRateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Set Exchange Rate",
)
def set_exchange_rate(
    payload: ExchangeRateCreate,
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:manage"))],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExchangeRateOut:
    fx = service.set_exchange_rate(
        from_currency=payload.from_currency_code,
        to_currency=payload.to_currency_code,
        rate=payload.rate,
        effective_date=payload.effective_date,
        source=payload.source,
        user_id=current_user.id,
    )
    return ExchangeRateOut.model_validate(fx)


@router.post(
    "/fx-rates/convert",
    response_model=FxConversionResponse,
    summary="Convert Amount via FX Rate",
)
def convert_fx_amount(
    payload: FxConversionRequest,
    service: Annotated[GLService, Depends(get_gl_service)],
    _: Annotated[ScopeContext, Depends(require("accounting:read"))],
) -> FxConversionResponse:
    converted, rate = service.convert_amount(
        amount=payload.amount,
        from_currency=payload.from_currency,
        to_currency=payload.to_currency,
        as_of_date=payload.as_of_date,
    )
    return FxConversionResponse(
        original_amount=payload.amount,
        from_currency=payload.from_currency.upper(),
        to_currency=payload.to_currency.upper(),
        rate=rate,
        converted_amount=converted,
        as_of_date=payload.as_of_date or date.today(),
    )
