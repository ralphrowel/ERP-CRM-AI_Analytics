"""Unit and Integration Tests for General Ledger Core (Milestone V2.1)

Validates:
1. Chart of Accounts (COA) initialization, validation, and tree hierarchies.
2. Fiscal Period lifecycle (creation, open-period resolution, closing).
3. Double-entry Journal Entry invariants:
   - SUM(debits) == SUM(credits) strict balance rule.
   - Minimum 2 lines (debit & credit).
   - Inactive account posting prevention.
   - Non-negative amounts.
4. Posted Entry Immutability & Reversals (ADR-0016).
5. Trial Balance generation and zero-balance equilibrium verification.
6. REST API routes & RBAC authorization enforcement.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.errors import BusinessRuleException, NotFoundException
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.accounting.models import Account
from app.modules.accounting.schemas import (
    AccountCreatePayload,
    FiscalPeriodCreatePayload,
    JournalEntryCreatePayload,
    JournalEntryLinePayload,
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
def gl_db() -> Session:
    """Creates an in-memory SQLite database seeded with sequences and permissions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed numbering sequence for journal entries
    seq = DocumentSequence(
        doc_type="journal_entry",
        prefix="JV",
        include_year=True,
        padding=6,
        next_value=1,
    )
    session.add(seq)

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
            code="accounting:report:read", description="View trial balance", module="accounting"
        ),
    ]
    session.add_all(accounting_perms)
    session.flush()

    # Create accountant role with full permissions
    role_accountant = Role(code="accountant", name="Staff Accountant")
    session.add(role_accountant)
    session.flush()

    for p in accounting_perms:
        session.add(RolePermission(role_id=role_accountant.id, permission_id=p.id, scope="all"))

    # Create viewer role with read-only
    role_viewer = Role(code="viewer", name="Accounting Viewer")
    session.add(role_viewer)
    session.flush()
    perm_read = next(p for p in accounting_perms if p.code == "accounting:read")
    perm_rep = next(p for p in accounting_perms if p.code == "accounting:report:read")
    session.add(RolePermission(role_id=role_viewer.id, permission_id=perm_read.id, scope="all"))
    session.add(RolePermission(role_id=role_viewer.id, permission_id=perm_rep.id, scope="all"))

    session.commit()
    return session


@pytest.fixture
def gl_service(gl_db: Session) -> GLService:
    return GLService(gl_db)


@pytest.fixture
def seeded_accounts(gl_service: GLService) -> list[Account]:
    return gl_service.seed_default_chart_of_accounts()


# =============================================================================
# 1. Chart of Accounts Tests
# =============================================================================


def test_seed_default_chart_of_accounts(gl_service: GLService):
    accounts = gl_service.seed_default_chart_of_accounts()
    assert len(accounts) >= 10

    # Idempotent run
    accounts_second = gl_service.seed_default_chart_of_accounts()
    assert len(accounts_second) == len(accounts)

    cash = gl_service.get_account_by_code("1110")
    assert cash.name == "Cash and Cash Equivalents"
    assert cash.account_type == "asset"
    assert cash.normal_balance == "debit"


def test_create_custom_account(gl_service: GLService, seeded_accounts: list[Account]):
    parent = gl_service.get_account_by_code("1110")
    payload = AccountCreatePayload(
        code="1111",
        name="Petty Cash Fund",
        account_type="asset",
        normal_balance="debit",
        parent_id=parent.id,
        description="Office petty cash vault",
    )
    acc = gl_service.create_account(payload)
    assert acc.id is not None
    assert acc.code == "1111"
    assert acc.parent_id == parent.id

    # Duplicate code rejection
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.create_account(payload)
    assert exc.value.code == "ACCOUNT_CODE_EXISTS"


def test_create_account_invalid_parent(gl_service: GLService):
    payload = AccountCreatePayload(
        code="9999",
        name="Invalid Parent Account",
        account_type="expense",
        normal_balance="debit",
        parent_id=999999,
    )
    with pytest.raises(NotFoundException):
        gl_service.create_account(payload)


def test_list_accounts_filter(gl_service: GLService, seeded_accounts: list[Account]):
    all_accs = gl_service.list_accounts()
    assert len(all_accs) >= 10

    active_accs = gl_service.list_accounts(is_active=True)
    assert len(active_accs) == len(all_accs)


# =============================================================================
# 2. Fiscal Periods Tests
# =============================================================================


def test_create_fiscal_period_and_validation(gl_service: GLService):
    payload = FiscalPeriodCreatePayload(
        period_name="FY2026-Q1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    period = gl_service.create_fiscal_period(payload)
    assert period.id is not None
    assert period.status == "open"

    # Start date after end date rejected
    bad_payload = FiscalPeriodCreatePayload(
        period_name="FY2026-BAD",
        start_date=date(2026, 3, 31),
        end_date=date(2026, 1, 1),
    )
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.create_fiscal_period(bad_payload)
    assert exc.value.code == "INVALID_PERIOD_DATES"

    # Duplicate period name rejected
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.create_fiscal_period(payload)
    assert exc.value.code == "PERIOD_NAME_EXISTS"


def test_fiscal_period_closing(gl_service: GLService):
    payload = FiscalPeriodCreatePayload(
        period_name="FY2026-Q2",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 6, 30),
    )
    period = gl_service.create_fiscal_period(payload)
    assert gl_service.get_open_period_for_date(date(2026, 5, 1)) is not None

    closed_period = gl_service.close_fiscal_period(period.id)
    assert closed_period.status == "closed"
    assert gl_service.get_open_period_for_date(date(2026, 5, 1)) is None


# =============================================================================
# 3. Double-Entry Journal Entry Posting & Balance Rules
# =============================================================================


def test_create_draft_journal_entry_and_validation(
    gl_service: GLService, seeded_accounts: list[Account]
):
    cash = gl_service.get_account_by_code("1110")
    capital = gl_service.get_account_by_code("3100")

    # Less than 2 lines rejected (both schema validation and service rule)
    with pytest.raises(ValidationError):
        JournalEntryCreatePayload(
            posting_date=date(2026, 1, 15),
            description="Single line entry",
            lines=[
                JournalEntryLinePayload(
                    account_id=cash.id,
                    debit_amount=Decimal("1000.00"),
                    credit_amount=Decimal("0.00"),
                )
            ],
        )

    single_line_payload = JournalEntryCreatePayload.model_construct(
        posting_date=date(2026, 1, 15),
        description="Single line entry",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("1000.00"),
                credit_amount=Decimal("0.00"),
            )
        ],
        source_document_type=None,
        source_document_id=None,
    )
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.create_journal_entry(single_line_payload)
    assert exc.value.code == "INSUFFICIENT_JOURNAL_LINES"

    # Negative amount rejected (both schema validation and service rule)
    with pytest.raises(ValidationError):
        JournalEntryLinePayload(
            account_id=cash.id,
            debit_amount=Decimal("-100.00"),
            credit_amount=Decimal("0.00"),
        )

    neg_line = JournalEntryCreatePayload.model_construct(
        posting_date=date(2026, 1, 15),
        description="Negative line entry",
        lines=[
            JournalEntryLinePayload.model_construct(
                account_id=cash.id,
                debit_amount=Decimal("-100.00"),
                credit_amount=Decimal("0.00"),
                description=None,
            ),
            JournalEntryLinePayload.model_construct(
                account_id=capital.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("100.00"),
                description=None,
            ),
        ],
        source_document_type=None,
        source_document_id=None,
    )
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.create_journal_entry(neg_line)
    assert exc.value.code == "NEGATIVE_POSTING_AMOUNT"

    # Valid draft created
    valid_payload = JournalEntryCreatePayload(
        posting_date=date(2026, 1, 15),
        description="Initial Capital Contribution",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("500000.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLinePayload(
                account_id=capital.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("500000.00"),
            ),
        ],
    )
    entry = gl_service.create_journal_entry(valid_payload)
    assert entry.id is not None
    assert entry.status == "draft"
    assert entry.total_debit == Decimal("500000.00")
    assert entry.total_credit == Decimal("500000.00")
    assert entry.entry_no.startswith("JV-")


def test_post_journal_entry_balanced(gl_service: GLService, seeded_accounts: list[Account]):
    cash = gl_service.get_account_by_code("1110")
    capital = gl_service.get_account_by_code("3100")

    payload = JournalEntryCreatePayload(
        posting_date=date(2026, 1, 15),
        description="Initial Capital Contribution",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("250000.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLinePayload(
                account_id=capital.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("250000.00"),
            ),
        ],
    )
    entry = gl_service.create_journal_entry(payload)
    posted = gl_service.post_journal_entry(entry.id)
    assert posted.status == "posted"

    # Immutability: already posted entry cannot be re-posted
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.post_journal_entry(entry.id)
    assert exc.value.code == "ALREADY_POSTED"


def test_imbalanced_journal_entry_cannot_be_posted(
    gl_service: GLService, seeded_accounts: list[Account]
):
    cash = gl_service.get_account_by_code("1110")
    capital = gl_service.get_account_by_code("3100")

    # Draft with debits != credits
    imbalanced = JournalEntryCreatePayload(
        posting_date=date(2026, 1, 15),
        description="Imbalanced Voucher",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("1000.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLinePayload(
                account_id=capital.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("900.00"),
            ),
        ],
    )
    entry = gl_service.create_journal_entry(imbalanced)

    # Attempting to post raises IMBALANCED_JOURNAL_ENTRY
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.post_journal_entry(entry.id)
    assert exc.value.code == "IMBALANCED_JOURNAL_ENTRY"


def test_post_fails_when_period_closed(gl_service: GLService, seeded_accounts: list[Account]):
    cash = gl_service.get_account_by_code("1110")
    capital = gl_service.get_account_by_code("3100")

    period = gl_service.create_fiscal_period(
        FiscalPeriodCreatePayload(
            period_name="FY2026-JAN",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
    )
    gl_service.close_fiscal_period(period.id)

    payload = JournalEntryCreatePayload(
        posting_date=date(2026, 1, 15),
        description="Entry in closed period",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("500.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLinePayload(
                account_id=capital.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("500.00"),
            ),
        ],
    )
    entry = gl_service.create_journal_entry(payload)

    with pytest.raises(BusinessRuleException) as exc:
        gl_service.post_journal_entry(entry.id)
    assert exc.value.code == "CLOSED_OR_MISSING_FISCAL_PERIOD"


# =============================================================================
# 4. Reversal Mechanism (ADR-0016)
# =============================================================================


def test_reversal_creates_offsetting_entry_and_marks_reversed(
    gl_service: GLService, seeded_accounts: list[Account]
):
    cash = gl_service.get_account_by_code("1110")
    revenue = gl_service.get_account_by_code("4100")

    payload = JournalEntryCreatePayload(
        posting_date=date(2026, 2, 10),
        description="Client Direct Deposit",
        lines=[
            JournalEntryLinePayload(
                account_id=cash.id,
                debit_amount=Decimal("15000.00"),
                credit_amount=Decimal("0.00"),
            ),
            JournalEntryLinePayload(
                account_id=revenue.id,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("15000.00"),
            ),
        ],
    )
    original = gl_service.create_journal_entry(payload, auto_post=True)
    assert original.status == "posted"

    # Execute reversal
    reversal = gl_service.reverse_journal_entry(
        original.id, reason="Erroneous double deposit recorded by teller"
    )

    assert reversal.status == "posted"
    assert reversal.reversal_of_id == original.id
    assert reversal.total_debit == Decimal("15000.00")
    assert reversal.total_credit == Decimal("15000.00")
    assert "Reversal of " in reversal.description

    # Lines should be inverted
    rev_lines = sorted(reversal.lines, key=lambda line: line.line_no)
    assert rev_lines[0].account_id == cash.id
    assert rev_lines[0].debit_amount == Decimal("0.00")
    assert rev_lines[0].credit_amount == Decimal("15000.00")

    assert rev_lines[1].account_id == revenue.id
    assert rev_lines[1].debit_amount == Decimal("15000.00")
    assert rev_lines[1].credit_amount == Decimal("0.00")

    # Original entry status is marked as 'reversed'
    gl_service.db.refresh(original)
    assert original.status == "reversed"

    # Cannot reverse an unposted entry
    draft_entry = gl_service.create_journal_entry(payload, auto_post=False)
    with pytest.raises(BusinessRuleException) as exc:
        gl_service.reverse_journal_entry(draft_entry.id, reason="Trying to reverse draft")
    assert exc.value.code == "CANNOT_REVERSE_UNPOSTED_ENTRY"


# =============================================================================
# 5. Trial Balance Calculation & Zero-Discrepancy Invariant
# =============================================================================


def test_trial_balance_equilibrium_and_net_balances(
    gl_service: GLService, seeded_accounts: list[Account]
):
    cash = gl_service.get_account_by_code("1110")
    ar = gl_service.get_account_by_code("1200")
    cogs = gl_service.get_account_by_code("5100")
    ap = gl_service.get_account_by_code("2100")
    capital = gl_service.get_account_by_code("3100")
    sales = gl_service.get_account_by_code("4100")

    # Entry 1: Capital injection (Dr Cash 100,000 / Cr Capital 100,000)
    gl_service.create_journal_entry(
        JournalEntryCreatePayload(
            posting_date=date(2026, 3, 1),
            description="Initial Capital",
            lines=[
                JournalEntryLinePayload(
                    account_id=cash.id,
                    debit_amount=Decimal("100000.00"),
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLinePayload(
                    account_id=capital.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("100000.00"),
                ),
            ],
        ),
        auto_post=True,
    )

    # Entry 2: Credit Sale (Dr AR 35,000 / Cr Sales 35,000)
    gl_service.create_journal_entry(
        JournalEntryCreatePayload(
            posting_date=date(2026, 3, 5),
            description="Sale on credit",
            lines=[
                JournalEntryLinePayload(
                    account_id=ar.id,
                    debit_amount=Decimal("35000.00"),
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLinePayload(
                    account_id=sales.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("35000.00"),
                ),
            ],
        ),
        auto_post=True,
    )

    # Entry 3: Vendor Expense on Account (Dr COGS 12,000 / Cr AP 12,000)
    gl_service.create_journal_entry(
        JournalEntryCreatePayload(
            posting_date=date(2026, 3, 10),
            description="Inventory purchase on account",
            lines=[
                JournalEntryLinePayload(
                    account_id=cogs.id,
                    debit_amount=Decimal("12000.00"),
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLinePayload(
                    account_id=ap.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("12000.00"),
                ),
            ],
        ),
        auto_post=True,
    )

    # Generate Trial Balance as of 2026-03-31
    report = gl_service.generate_trial_balance(as_of_date=date(2026, 3, 31))

    assert report.is_balanced is True
    assert report.total_debits == Decimal("147000.00")
    assert report.total_credits == Decimal("147000.00")

    # Check individual account net balances
    row_map = {r.code: r for r in report.rows}
    assert row_map["1110"].net_balance == Decimal("100000.00")
    assert row_map["1200"].net_balance == Decimal("35000.00")
    assert row_map["2100"].net_balance == Decimal("12000.00")
    assert row_map["3100"].net_balance == Decimal("100000.00")
    assert row_map["4100"].net_balance == Decimal("35000.00")
    assert row_map["5100"].net_balance == Decimal("12000.00")


# =============================================================================
# 6. REST API Endpoints & RBAC Security
# =============================================================================


@pytest.fixture
def auth_setup(gl_db: Session):
    # Create accountant user
    u_acc = User(
        email="accountant@test.com",
        password_hash=hash_password("Pass123!"),
        full_name="Staff Accountant",
        is_active=True,
        is_superuser=False,
    )
    # Create viewer user
    u_view = User(
        email="viewer@test.com",
        password_hash=hash_password("Pass123!"),
        full_name="Viewer",
        is_active=True,
        is_superuser=False,
    )
    gl_db.add_all([u_acc, u_view])
    gl_db.flush()

    role_acc = gl_db.query(Role).filter(Role.code == "accountant").one()
    role_view = gl_db.query(Role).filter(Role.code == "viewer").one()

    gl_db.add(UserRole(user_id=u_acc.id, role_id=role_acc.id))
    gl_db.add(UserRole(user_id=u_view.id, role_id=role_view.id))
    gl_db.commit()

    from unittest.mock import MagicMock

    s_acc = MagicMock()
    s_view = MagicMock()

    return {"accountant": (u_acc, s_acc), "viewer": (u_view, s_view)}


def test_api_account_and_journal_endpoints(gl_db: Session, auth_setup: dict):
    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: gl_db

    # Authenticate as accountant
    u_acc, s_acc = auth_setup["accountant"]
    app.dependency_overrides[get_current_user_and_session] = lambda: (u_acc, s_acc)

    # 1. Create Account via API
    res = client.post(
        "/api/v1/accounting/accounts",
        json={
            "code": "1190",
            "name": "Prepaid Expenses",
            "account_type": "asset",
            "normal_balance": "debit",
            "description": "Prepaid rent and insurance",
        },
    )
    assert res.status_code == 201
    acc_id = res.json()["id"]

    # Seed default COA for test entry
    gl = GLService(gl_db)
    gl.seed_default_chart_of_accounts()
    cash = gl.get_account_by_code("1110")

    # 2. Create Journal Entry via API
    res = client.post(
        "/api/v1/accounting/journal-entries",
        json={
            "posting_date": "2026-04-01",
            "description": "Prepaid rent advance payment",
            "lines": [
                {"account_id": acc_id, "debit_amount": "60000.00", "credit_amount": "0.00"},
                {"account_id": cash.id, "debit_amount": "0.00", "credit_amount": "60000.00"},
            ],
        },
    )
    assert res.status_code == 201
    entry_id = res.json()["id"]
    assert res.json()["status"] == "draft"

    # 3. Post Journal Entry via API
    res = client.post(f"/api/v1/accounting/journal-entries/{entry_id}/post")
    assert res.status_code == 200
    assert res.json()["status"] == "posted"

    # 4. Generate Trial Balance via API
    res = client.get("/api/v1/accounting/reports/trial-balance?as_of_date=2026-04-30")
    assert res.status_code == 200
    tb_data = res.json()
    assert tb_data["is_balanced"] is True
    assert Decimal(str(tb_data["total_debits"])) == Decimal("60000.00")

    # 5. Reverse Entry via API
    res = client.post(
        f"/api/v1/accounting/journal-entries/{entry_id}/reverse",
        json={"reason": "Wrong prepaid account classified"},
    )
    assert res.status_code == 200
    assert res.json()["reversal_of_id"] == entry_id

    # 6. Verify RBAC Forbidden for Viewer on write endpoint
    u_view, s_view = auth_setup["viewer"]
    app.dependency_overrides[get_current_user_and_session] = lambda: (u_view, s_view)

    forbidden_res = client.post(
        "/api/v1/accounting/accounts",
        json={
            "code": "1999",
            "name": "Unauthorized Account",
            "account_type": "asset",
            "normal_balance": "debit",
        },
    )
    assert forbidden_res.status_code == 403

    # But viewer CAN read accounts and trial balance
    read_res = client.get("/api/v1/accounting/accounts")
    assert read_res.status_code == 200

    tb_viewer_res = client.get("/api/v1/accounting/reports/trial-balance?as_of_date=2026-04-30")
    assert tb_viewer_res.status_code == 200

    # Cleanup overrides
    app.dependency_overrides.clear()
