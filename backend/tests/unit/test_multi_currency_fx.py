"""Unit and Integration Tests for Multi-Currency Operations & FX Engine (Milestone V2.3)

Validates:
1. ISO-4217 Currency registry (seeding, CRUD, single base currency constraint).
2. Date-effective exchange rate resolution (direct, reciprocal inverse, history).
3. Decimal rounding and monetary conversion calculations.
4. Multi-currency invoice posting to GL in base PHP currency.
5. Multi-currency payment settlement with automated Realized FX Gain (account 4300).
6. Multi-currency payment settlement with automated Realized FX Loss (account 5300).
7. Financial statement integrity (Income Statement & Balance Sheet equilibrium with FX).
8. REST API endpoints and RBAC authorization controls.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.errors import BusinessRuleException
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.accounting.schemas import (
    CurrencyCreate,
)
from app.modules.accounting.service import GLService
from app.modules.identity.dependencies import get_current_user_and_session
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


@pytest.fixture
def fx_db() -> Session:
    """Creates an in-memory SQLite database seeded with sequences and permissions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Numbering sequences
    session.add(
        DocumentSequence(
            doc_type="journal_entry",
            prefix="JV",
            include_year=True,
            padding=6,
            next_value=1,
        )
    )

    # Seed permissions
    accounting_perms = [
        Permission(
            code="accounting:read", description="View accounting records", module="accounting"
        ),
        Permission(
            code="accounting:manage", description="Manage COA and periods", module="accounting"
        ),
        Permission(
            code="accounting:entry:create", description="Draft journal entries", module="accounting"
        ),
        Permission(
            code="accounting:entry:post", description="Post journal entries", module="accounting"
        ),
        Permission(
            code="accounting:entry:reverse",
            description="Reverse journal entries",
            module="accounting",
        ),
        Permission(
            code="accounting:report:read", description="View financial reports", module="accounting"
        ),
    ]
    session.add_all(accounting_perms)
    session.flush()

    # Accountant role
    role_accountant = Role(code="accountant", name="Staff Accountant")
    session.add(role_accountant)
    session.flush()
    for p in accounting_perms:
        session.add(RolePermission(role_id=role_accountant.id, permission_id=p.id, scope="all"))

    # Viewer role
    role_viewer = Role(code="viewer", name="Accounting Viewer")
    session.add(role_viewer)
    session.flush()
    perm_read = next(p for p in accounting_perms if p.code == "accounting:read")
    perm_rep = next(p for p in accounting_perms if p.code == "accounting:report:read")
    session.add(RolePermission(role_id=role_viewer.id, permission_id=perm_read.id, scope="all"))
    session.add(RolePermission(role_id=role_viewer.id, permission_id=perm_rep.id, scope="all"))

    # Users
    u_acc = User(
        email="accountant@test.local",
        full_name="FX Accountant",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    u_view = User(
        email="viewer@test.local",
        full_name="FX Viewer",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    session.add_all([u_acc, u_view])
    session.flush()

    session.add(UserRole(user_id=u_acc.id, role_id=role_accountant.id))
    session.add(UserRole(user_id=u_view.id, role_id=role_viewer.id))

    session.commit()
    return session


@pytest.fixture
def gl_service(fx_db: Session) -> GLService:
    service = GLService(fx_db)
    service.seed_default_chart_of_accounts()
    service.seed_default_currencies()
    return service


# =============================================================================
# 1. Currency Registry Tests
# =============================================================================


def test_seed_default_currencies(gl_service: GLService):
    """Verifies default currency baseline is properly initialized."""
    currencies = gl_service.list_currencies()
    codes = {c.code for c in currencies}
    assert "PHP" in codes
    assert "USD" in codes
    assert "EUR" in codes
    assert "SGD" in codes
    assert "JPY" in codes

    php = gl_service.get_currency("PHP")
    assert php.is_base is True
    assert php.symbol == "₱"
    assert php.decimal_places == 2

    usd = gl_service.get_currency("USD")
    assert usd.is_base is False
    assert usd.symbol == "$"


def test_register_new_currency(gl_service: GLService):
    """Registers a new foreign currency (GBP) and prevents duplicates."""
    gbp = gl_service.create_currency(
        CurrencyCreate(
            code="GBP",
            name="British Pound Sterling",
            symbol="£",
            decimal_places=2,
            is_base=False,
        )
    )
    assert gbp.code == "GBP"
    assert gbp.name == "British Pound Sterling"

    # Duplicate code rejection
    with pytest.raises(BusinessRuleException) as exc_info:
        gl_service.create_currency(
            CurrencyCreate(
                code="GBP",
                name="Duplicate Pound",
                symbol="£",
                decimal_places=2,
            )
        )
    assert exc_info.value.code == "CURRENCY_ALREADY_EXISTS"


def test_single_base_currency_constraint(gl_service: GLService):
    """Prevents registering a second base currency when PHP is already base."""
    with pytest.raises(BusinessRuleException) as exc_info:
        gl_service.create_currency(
            CurrencyCreate(
                code="CAD",
                name="Canadian Dollar",
                symbol="C$",
                decimal_places=2,
                is_base=True,
            )
        )
    assert exc_info.value.code == "BASE_CURRENCY_EXISTS"


# =============================================================================
# 2. Exchange Rate Resolution & Conversion Tests
# =============================================================================


def test_exchange_rate_setting_and_effective_dates(gl_service: GLService):
    """Tests rate creation, updates, and chronological resolution."""
    d1 = date(2026, 10, 1)
    d2 = date(2026, 10, 10)

    # Set rate on Oct 1: 1 USD = 56.000000 PHP
    gl_service.set_exchange_rate(
        "USD", "PHP", Decimal("56.000000"), effective_date=d1, source="BSP"
    )
    # Set rate on Oct 10: 1 USD = 57.500000 PHP
    gl_service.set_exchange_rate(
        "USD", "PHP", Decimal("57.500000"), effective_date=d2, source="BSP"
    )

    # Rate on Oct 5 should resolve to Oct 1 rate (56.000000)
    rate_oct5 = gl_service.get_exchange_rate("USD", "PHP", as_of_date=date(2026, 10, 5))
    assert rate_oct5 == Decimal("56.000000")

    # Rate on Oct 12 should resolve to Oct 10 rate (57.500000)
    rate_oct12 = gl_service.get_exchange_rate("USD", "PHP", as_of_date=date(2026, 10, 12))
    assert rate_oct12 == Decimal("57.500000")

    # Identical currency resolution is always 1.0
    assert gl_service.get_exchange_rate("USD", "USD") == Decimal("1.000000")
    assert gl_service.get_exchange_rate("PHP", "PHP") == Decimal("1.000000")


def test_reciprocal_rate_resolution(gl_service: GLService):
    """Resolves reciprocal rate when only direct pair exists."""
    gl_service.set_exchange_rate(
        "USD", "PHP", Decimal("50.000000"), effective_date=date(2026, 10, 1)
    )

    # PHP to USD should be 1 / 50.0 = 0.020000
    reciprocal = gl_service.get_exchange_rate("PHP", "USD", as_of_date=date(2026, 10, 2))
    assert reciprocal == Decimal("0.020000")


def test_missing_exchange_rate_raises(gl_service: GLService):
    """Raises error if no rate exists on or before requested date."""
    with pytest.raises(BusinessRuleException) as exc_info:
        gl_service.get_exchange_rate("EUR", "PHP", as_of_date=date(2026, 10, 1))
    assert exc_info.value.code == "EXCHANGE_RATE_NOT_FOUND"


def test_convert_amount_calculations(gl_service: GLService):
    """Tests amount conversion with precise monetary rounding."""
    gl_service.set_exchange_rate(
        "USD", "PHP", Decimal("56.250000"), effective_date=date(2026, 10, 1)
    )

    converted, rate = gl_service.convert_amount(
        Decimal("1000.00"), from_currency="USD", to_currency="PHP", as_of_date=date(2026, 10, 2)
    )
    assert rate == Decimal("56.250000")
    assert converted == Decimal("56250.00")

    # Fractional centavo rounding
    converted2, _ = gl_service.convert_amount(
        Decimal("123.45"), from_currency="USD", to_currency="PHP", as_of_date=date(2026, 10, 2)
    )
    # 123.45 * 56.25 = 6944.0625 -> rounds to 6944.06
    assert converted2 == Decimal("6944.06")


# =============================================================================
# 3. Subledger-to-GL Multi-Currency Invoicing & Settlements
# =============================================================================


def test_post_invoice_to_gl_foreign_currency(gl_service: GLService):
    """Posts a foreign currency invoice (USD) converted to base PHP at prevailing rate."""
    today = date(2026, 10, 5)
    gl_service.set_exchange_rate("USD", "PHP", Decimal("56.000000"), effective_date=today)

    entry = gl_service.post_invoice_to_gl(
        invoice_id=901,
        invoice_no="INV-FX-001",
        customer_name="Global Corp USA",
        posting_date=today,
        subtotal=Decimal("892.86"),
        tax_total=Decimal("107.14"),
        grand_total=Decimal("1000.00"),
        currency_code="USD",
        exchange_rate=Decimal("56.000000"),
    )

    assert entry is not None
    assert entry.status == "posted"
    assert "USD 1000.00 @ 56.000000" in entry.description

    # Base amount: 1000 * 56 = 56,000.00 PHP
    ar_line = next(line for line in entry.lines if line.account.code == "1200")
    assert ar_line.debit_amount == Decimal("56000.00")
    assert ar_line.credit_amount == Decimal("0.00")

    # Equilibrium check
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)
    assert total_debits == total_credits == Decimal("56000.00")


def test_post_payment_with_realized_fx_gain(gl_service: GLService):
    """
    Settles a USD invoice when exchange rate strengthens (PHP weakens).
    Original invoice: 1,000 USD @ ₱56.00 = ₱56,000.00 AR.
    Payment received: 1,000 USD @ ₱58.00 = ₱58,000.00 Bank.
    Gain: ₱2,000.00 -> Cr Realized Foreign Exchange Gain (4300).
    """
    today = date(2026, 10, 15)
    entry = gl_service.post_payment_to_gl(
        payment_id=801,
        payment_no="PAY-FX-001",
        posting_date=today,
        amount_allocated=Decimal("1000.00"),
        customer_name="Global Corp USA",
        payment_currency_code="USD",
        payment_exchange_rate=Decimal("58.000000"),
        invoice_exchange_rate=Decimal("56.000000"),
    )

    assert entry is not None
    assert entry.status == "posted"

    # Dr Bank (1120): ₱58,000.00
    bank_line = next(line for line in entry.lines if line.account.code == "1120")
    assert bank_line.debit_amount == Decimal("58000.00")
    assert bank_line.credit_amount == Decimal("0.00")

    # Cr AR (1200): ₱56,000.00 (settles AR at original base rate)
    ar_line = next(line for line in entry.lines if line.account.code == "1200")
    assert ar_line.debit_amount == Decimal("0.00")
    assert ar_line.credit_amount == Decimal("56000.00")

    # Cr Realized FX Gain (4300): ₱2,000.00
    gain_line = next(line for line in entry.lines if line.account.code == "4300")
    assert gain_line.debit_amount == Decimal("0.00")
    assert gain_line.credit_amount == Decimal("2000.00")

    # Perfect balance
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)
    assert total_debits == total_credits == Decimal("58000.00")


def test_post_payment_with_realized_fx_loss(gl_service: GLService):
    """
    Settles a USD invoice when exchange rate drops (PHP strengthens).
    Original invoice: 1,000 USD @ ₱56.00 = ₱56,000.00 AR.
    Payment received: 1,000 USD @ ₱55.00 = ₱55,000.00 Bank.
    Loss: ₱1,000.00 -> Dr Realized Foreign Exchange Loss (5300).
    """
    today = date(2026, 10, 16)
    entry = gl_service.post_payment_to_gl(
        payment_id=802,
        payment_no="PAY-FX-002",
        posting_date=today,
        amount_allocated=Decimal("1000.00"),
        customer_name="Global Corp USA",
        payment_currency_code="USD",
        payment_exchange_rate=Decimal("55.000000"),
        invoice_exchange_rate=Decimal("56.000000"),
    )

    assert entry is not None
    assert entry.status == "posted"

    # Dr Bank (1120): ₱55,000.00
    bank_line = next(line for line in entry.lines if line.account.code == "1120")
    assert bank_line.debit_amount == Decimal("55000.00")
    assert bank_line.credit_amount == Decimal("0.00")

    # Dr Realized FX Loss (5300): ₱1,000.00
    loss_line = next(line for line in entry.lines if line.account.code == "5300")
    assert loss_line.debit_amount == Decimal("1000.00")
    assert loss_line.credit_amount == Decimal("0.00")

    # Cr AR (1200): ₱56,000.00
    ar_line = next(line for line in entry.lines if line.account.code == "1200")
    assert ar_line.debit_amount == Decimal("0.00")
    assert ar_line.credit_amount == Decimal("56000.00")

    # Equilibrium
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)
    assert total_debits == total_credits == Decimal("56000.00")


# =============================================================================
# 4. Financial Statement Equilibrium with Realized FX
# =============================================================================


def test_financial_statement_equilibrium_with_fx(gl_service: GLService):
    """
    Verifies that FX gain flows to Income Statement and folded Balance Sheet retains equilibrium.
    """
    start_date = date(2026, 10, 1)
    end_date = date(2026, 10, 31)

    # 1. Invoice USD 1,000 @ 56.00
    gl_service.post_invoice_to_gl(
        invoice_id=999,
        invoice_no="INV-FX-BAL",
        customer_name="Acme Corp",
        posting_date=date(2026, 10, 5),
        subtotal=Decimal("892.86"),
        tax_total=Decimal("107.14"),
        grand_total=Decimal("1000.00"),
        currency_code="USD",
        exchange_rate=Decimal("56.000000"),
    )

    # 2. Payment USD 1,000 @ 58.00 (₱2,000 Realized FX Gain)
    gl_service.post_payment_to_gl(
        payment_id=888,
        payment_no="PAY-FX-BAL",
        posting_date=date(2026, 10, 20),
        amount_allocated=Decimal("1000.00"),
        customer_name="Acme Corp",
        payment_currency_code="USD",
        payment_exchange_rate=Decimal("58.000000"),
        invoice_exchange_rate=Decimal("56.000000"),
    )

    # Check Trial Balance
    tb = gl_service.generate_trial_balance(as_of_date=end_date)
    assert tb.is_balanced is True
    assert tb.total_debits == tb.total_credits

    # Check Income Statement
    is_report = gl_service.generate_income_statement(start_date=start_date, end_date=end_date)
    # Total revenue includes Sales Revenue (₱50,000.16) + Realized FX Gain (₱2,000.00) = ₱52,000.16
    assert is_report.total_revenue == Decimal("52000.16")

    # Check Balance Sheet
    bs = gl_service.generate_balance_sheet(as_of_date=end_date)
    assert bs.is_balanced is True
    assert bs.total_assets == bs.total_liabilities_and_equity


# =============================================================================
# 5. REST API Endpoints & RBAC Authorization
# =============================================================================


def test_api_currencies_and_fx_rates(fx_db: Session, gl_service: GLService):
    """Tests /api/v1/accounting/currencies and /fx-rates endpoints with auth."""
    accountant = fx_db.query(User).filter(User.email == "accountant@test.local").first()
    viewer = fx_db.query(User).filter(User.email == "viewer@test.local").first()

    app.dependency_overrides[get_db] = lambda: fx_db

    # Authenticate as accountant
    app.dependency_overrides[get_current_user_and_session] = lambda: (accountant, None)
    client = TestClient(app)

    # 1. List currencies
    res = client.get("/api/v1/accounting/currencies")
    assert res.status_code == 200
    codes = [c["code"] for c in res.json()]
    assert "PHP" in codes
    assert "USD" in codes

    # 2. Register custom currency (SGD already exists, let's register AUD)
    res = client.post(
        "/api/v1/accounting/currencies",
        json={
            "code": "AUD",
            "name": "Australian Dollar",
            "symbol": "A$",
            "decimal_places": 2,
            "is_base": False,
        },
    )
    assert res.status_code == 201
    assert res.json()["code"] == "AUD"

    # 3. Set exchange rate
    res = client.post(
        "/api/v1/accounting/fx-rates",
        json={
            "from_currency_code": "AUD",
            "to_currency_code": "PHP",
            "effective_date": "2026-10-12",
            "rate": "37.500000",
            "source": "manual",
        },
    )
    assert res.status_code == 201
    assert Decimal(res.json()["rate"]) == Decimal("37.500000")

    # 4. Get exchange rate
    res = client.get(
        "/api/v1/accounting/fx-rates?from_currency=AUD&to_currency=PHP&as_of_date=2026-10-12"
    )
    assert res.status_code == 200
    assert Decimal(res.json()["rate"]) == Decimal("37.500000")

    # 5. Convert amount endpoint
    res = client.post(
        "/api/v1/accounting/fx-rates/convert",
        json={
            "amount": "200.00",
            "from_currency": "AUD",
            "to_currency": "PHP",
            "as_of_date": "2026-10-12",
        },
    )
    assert res.status_code == 200
    # 200 * 37.5 = 7500.00
    assert Decimal(res.json()["converted_amount"]) == Decimal("7500.00")

    # 6. Switch to Viewer (Read-only) -> Trying to POST /fx-rates should fail (403)
    app.dependency_overrides[get_current_user_and_session] = lambda: (viewer, None)
    res_forbidden = client.post(
        "/api/v1/accounting/fx-rates",
        json={
            "from_currency_code": "AUD",
            "to_currency_code": "PHP",
            "effective_date": "2026-10-13",
            "rate": "38.000000",
        },
    )
    assert res_forbidden.status_code == 403

    app.dependency_overrides.clear()
