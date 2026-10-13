"""Unit & Integration Tests for Automated Subledger-to-GL Posting and Financial Statements (Milestone V2.2)

Validates:
1. Sales Invoice issuance automatically creates balanced GL journal entries (Dr AR / Cr Revenue + VAT).
2. Sales Invoice voiding automatically posts offsetting counter-reversals.
3. Customer payment allocation automatically posts GL entries (Dr Bank / Cr AR).
4. Sales Credit Note issuance automatically posts GL entries (Dr Discount + VAT / Cr AR).
5. Supplier Bill approval automatically posts GL entries (Dr GRNI + Input VAT / Cr AP).
6. Supplier Payment disbursement automatically posts GL entries (Dr AP / Cr Bank).
7. Balance Sheet generation proves accounting equality: Total Assets == Total Liabilities + Total Equity.
8. Income Statement generation calculates Net Income = Revenue - COGS - Operating Expenses.
9. REST API endpoints & RBAC security for Balance Sheet and Income Statement reports.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.accounting.models import JournalEntry
from app.modules.accounting.service import GLService
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer
from app.modules.identity.dependencies import get_current_user_and_session
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.modules.inventory.models import Warehouse
from app.modules.purchasing.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItemPayload,
    SupplierCreate,
    SupplierInvoiceCreate,
    SupplierInvoiceItemPayload,
    SupplierPaymentAllocationItem,
    SupplierPaymentCreate,
)
from app.modules.purchasing.service import PurchasingService
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import (
    CreditNoteCreatePayload,
    LineItemPayload,
    PaymentAllocationCreatePayload,
    PaymentCreatePayload,
    SalesOrderCreatePayload,
)
from app.modules.sales.service import SalesService


@pytest.fixture
def subledger_db() -> Session:
    """Sets up an in-memory SQLite database with master data and numbering sequences."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Numbering sequences
    seqs = [
        DocumentSequence(
            doc_type="customer", prefix="CUS", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(doc_type="quote", prefix="QT", include_year=True, padding=6, next_value=1),
        DocumentSequence(
            doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="invoice", prefix="INV", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="credit_note", prefix="CN", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="payment", prefix="PAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="supplier", prefix="SUP", include_year=False, padding=5, next_value=1
        ),
        DocumentSequence(
            doc_type="purchase_order", prefix="PO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="goods_receipt", prefix="GR", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="supplier_invoice", prefix="BILL", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="supplier_payment", prefix="SPAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="journal_entry", prefix="JV", include_year=True, padding=6, next_value=1
        ),
    ]
    session.add_all(seqs)

    # Master Data
    wh = Warehouse(code="MNL-MAIN", name="Manila Main", is_active=True, is_default=True)
    session.add(wh)

    tax_vat = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    tax_zero = TaxRate(
        code="VAT0", name="VAT 0%", rate=Decimal("0.0000"), is_default=False, is_active=True
    )
    session.add_all([tax_vat, tax_zero])

    cat = ProductCategory(name="Electronics", is_active=True)
    session.add(cat)
    session.flush()

    prod = Product(
        sku="LAPTOP-PRO",
        name="Enterprise Pro Laptop",
        category_id=cat.id,
        product_type="service",
        uom="pc",
        list_price=Decimal("50000.00"),
        tax_rate_id=tax_vat.id,
        is_active=True,
    )
    session.add(prod)

    # Seed default Chart of Accounts
    gl = GLService(session)
    gl.seed_default_chart_of_accounts()

    # Permissions
    report_perm = Permission(
        code="accounting:report:read", description="Read financial reports", module="accounting"
    )
    admin_perm = Permission(
        code="accounting:manage", description="Manage accounting", module="accounting"
    )
    session.add_all([report_perm, admin_perm])
    session.flush()

    role_finance = Role(code="finance", name="Finance Analyst")
    session.add(role_finance)
    session.flush()
    session.add(RolePermission(role_id=role_finance.id, permission_id=report_perm.id, scope="all"))

    session.commit()
    return session


@pytest.fixture
def sales_svc(subledger_db: Session) -> SalesService:
    return SalesService(subledger_db)


@pytest.fixture
def purchasing_svc(subledger_db: Session) -> PurchasingService:
    return PurchasingService(subledger_db)


@pytest.fixture
def gl_svc(subledger_db: Session) -> GLService:
    return GLService(subledger_db)


# =============================================================================
# 1. Sales Invoice to GL Posting & Void Reversal
# =============================================================================


def test_sales_invoice_issuance_and_voiding_gl_lifecycle(
    subledger_db: Session, sales_svc: SalesService, gl_svc: GLService
):
    # Create Customer
    customer = Customer(
        customer_no="CUS-000001",
        name="Acme Technology Inc.",
        status="active",
        credit_limit=Decimal("500000.00"),
        payment_terms_days=30,
    )
    subledger_db.add(customer)
    subledger_db.commit()

    prod = subledger_db.query(Product).filter(Product.sku == "LAPTOP-PRO").one()
    vat = subledger_db.query(TaxRate).filter(TaxRate.code == "VAT12").one()

    # Create Sales Order
    so = sales_svc.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=customer.id,
            items=[
                LineItemPayload(
                    product_id=prod.id,
                    quantity=Decimal("2.000"),
                    unit_price=Decimal("50000.00"),
                    discount_amount=Decimal("0.00"),
                    tax_rate_id=vat.id,
                )
            ],
        )
    )
    sales_svc.confirm_sales_order(so.id)

    # Create & Issue Invoice: Subtotal 100,000 + Tax 12,000 = Grand Total 112,000
    inv = sales_svc.create_invoice_from_order(so.id)
    issued_inv = sales_svc.issue_invoice(inv.id)
    assert issued_inv.status == "issued"

    # Verify Journal Entry was created and posted
    je = (
        subledger_db.query(JournalEntry)
        .filter(
            JournalEntry.source_document_type == "invoice",
            JournalEntry.source_document_id == inv.id,
        )
        .one()
    )
    assert je.status == "posted"
    assert je.total_debit == Decimal("112000.00")
    assert je.total_credit == Decimal("112000.00")

    lines = {line.account.code: line for line in je.lines}
    assert lines["1200"].debit_amount == Decimal("112000.00")  # AR
    assert lines["4100"].credit_amount == Decimal("100000.00")  # Sales Revenue
    assert lines["2210"].credit_amount == Decimal("12000.00")  # Output VAT

    # Void the invoice and verify counter-entry reversal
    sales_svc.void_invoice(inv.id, reason="Customer cancelled project")

    subledger_db.refresh(je)
    assert je.status == "reversed"

    reversal_je = (
        subledger_db.query(JournalEntry).filter(JournalEntry.reversal_of_id == je.id).one()
    )
    assert reversal_je.status == "posted"
    rev_lines = {line.account.code: line for line in reversal_je.lines}
    assert rev_lines["1200"].credit_amount == Decimal("112000.00")
    assert rev_lines["4100"].debit_amount == Decimal("100000.00")


# =============================================================================
# 2. Customer Payment Allocation & Credit Note Posting
# =============================================================================


def test_payment_and_credit_note_gl_posting(
    subledger_db: Session, sales_svc: SalesService, gl_svc: GLService
):
    customer = Customer(
        customer_no="CUS-000002",
        name="Global Solutions Corp.",
        status="active",
        credit_limit=Decimal("500000.00"),
        payment_terms_days=30,
    )
    subledger_db.add(customer)
    subledger_db.commit()

    prod = subledger_db.query(Product).filter(Product.sku == "LAPTOP-PRO").one()
    vat = subledger_db.query(TaxRate).filter(TaxRate.code == "VAT12").one()

    # Order & Invoice: 100,000 + 12,000 = 112,000
    so = sales_svc.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=customer.id,
            items=[
                LineItemPayload(
                    product_id=prod.id,
                    quantity=Decimal("2.000"),
                    unit_price=Decimal("50000.00"),
                    tax_rate_id=vat.id,
                )
            ],
        )
    )
    sales_svc.confirm_sales_order(so.id)
    inv = sales_svc.create_invoice_from_order(so.id)
    sales_svc.issue_invoice(inv.id)

    # 1. Payment received and allocated: ₱60,000
    payment = sales_svc.create_payment(
        PaymentCreatePayload(
            customer_id=customer.id,
            payment_date=date(2026, 4, 15),
            amount=Decimal("60000.00"),
            method="bank_transfer",
            allocations=[
                PaymentAllocationCreatePayload(invoice_id=inv.id, amount=Decimal("60000.00"))
            ],
        )
    )

    pay_je = (
        subledger_db.query(JournalEntry)
        .filter(
            JournalEntry.source_document_type == "payment",
            JournalEntry.source_document_id == payment.id,
        )
        .one()
    )
    assert pay_je.status == "posted"
    pay_lines = {line.account.code: line for line in pay_je.lines}
    assert pay_lines["1120"].debit_amount == Decimal("60000.00")  # Bank
    assert pay_lines["1200"].credit_amount == Decimal("60000.00")  # AR

    # 2. Credit Note issued for balance: ₱52,000 (Remaining balance)
    cn = sales_svc.create_credit_note(
        CreditNoteCreatePayload(
            invoice_id=inv.id,
            reason="discount",
        )
    )

    cn_je = (
        subledger_db.query(JournalEntry)
        .filter(
            JournalEntry.source_document_type == "credit_note",
            JournalEntry.source_document_id == cn.id,
        )
        .one()
    )
    assert cn_je.status == "posted"
    cn_lines = {line.account.code: line for line in cn_je.lines}
    assert cn_lines["4200"].debit_amount == Decimal("52000.00")  # Sales Discounts
    assert cn_lines["1200"].credit_amount == Decimal("52000.00")  # AR


# =============================================================================
# 3. Purchasing: Supplier Bill Approval & Disbursement Posting
# =============================================================================


def test_supplier_bill_and_payment_gl_posting(
    subledger_db: Session, purchasing_svc: PurchasingService, gl_svc: GLService
):
    supplier = purchasing_svc.create_supplier(
        SupplierCreate(name="Mega Supply Corp.", payment_terms_days=30)
    )
    prod = subledger_db.query(Product).filter(Product.sku == "LAPTOP-PRO").one()
    vat = subledger_db.query(TaxRate).filter(TaxRate.code == "VAT12").one()

    wh = subledger_db.query(Warehouse).filter(Warehouse.code == "MNL-MAIN").one()
    # Create PO
    po = purchasing_svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=supplier.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=prod.id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("30000.00"),
                    tax_rate_id=vat.id,
                )
            ],
        )
    )
    purchasing_svc.send_purchase_order(po.id)

    # Create Supplier Bill (subtotal 300,000 + tax 36,000 = 336,000)
    bill = purchasing_svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="INV-SUP-88991",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("30000.00"),
                )
            ],
        )
    )
    # Approve bill
    app_bill = purchasing_svc.approve_supplier_invoice(bill.id)
    assert app_bill.status == "approved"

    # Verify Bill GL Entry
    bill_je = (
        subledger_db.query(JournalEntry)
        .filter(
            JournalEntry.source_document_type == "supplier_invoice",
            JournalEntry.source_document_id == bill.id,
        )
        .one()
    )
    assert bill_je.status == "posted"
    b_lines = {line.account.code: line for line in bill_je.lines}
    assert b_lines["2150"].debit_amount == Decimal("300000.00")  # GRNI / Accrual
    assert b_lines["1400"].debit_amount == Decimal("36000.00")  # Input VAT
    assert b_lines["2100"].credit_amount == Decimal("336000.00")  # Accounts Payable

    # Record Supplier Payment: ₱336,000
    spay = purchasing_svc.create_supplier_payment(
        SupplierPaymentCreate(
            supplier_id=supplier.id,
            amount=Decimal("336000.00"),
            payment_method="bank_transfer",
            allocations=[
                SupplierPaymentAllocationItem(
                    supplier_invoice_id=bill.id, amount=Decimal("336000.00")
                )
            ],
        )
    )

    spay_je = (
        subledger_db.query(JournalEntry)
        .filter(
            JournalEntry.source_document_type == "supplier_payment",
            JournalEntry.source_document_id == spay.id,
        )
        .one()
    )
    assert spay_je.status == "posted"
    sp_lines = {line.account.code: line for line in spay_je.lines}
    assert sp_lines["2100"].debit_amount == Decimal("336000.00")  # AP Cleared
    assert sp_lines["1120"].credit_amount == Decimal("336000.00")  # Bank Disbursed


# =============================================================================
# 4. Financial Statements (Balance Sheet & Income Statement)
# =============================================================================


def test_balance_sheet_and_income_statement_parity(subledger_db: Session, gl_svc: GLService):
    cash = gl_svc.get_account_by_code("1110")
    capital = gl_svc.get_account_by_code("3100")
    ar = gl_svc.get_account_by_code("1200")
    sales = gl_svc.get_account_by_code("4100")
    cogs = gl_svc.get_account_by_code("5100")
    ap = gl_svc.get_account_by_code("2100")
    opex = gl_svc.get_account_by_code("6100")

    # 1. Owner contributes ₱500,000 capital (Dr Cash / Cr Capital)
    gl_svc.create_journal_entry(
        MagicMock(
            posting_date=date(2026, 1, 1),
            description="Capital injection",
            source_document_type=None,
            source_document_id=None,
            lines=[
                MagicMock(
                    account_id=cash.id,
                    debit_amount=Decimal("500000.00"),
                    credit_amount=Decimal("0.00"),
                    description=None,
                ),
                MagicMock(
                    account_id=capital.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("500000.00"),
                    description=None,
                ),
            ],
        ),
        auto_post=True,
    )

    # 2. Sales of ₱200,000 on account (Dr AR / Cr Sales)
    gl_svc.create_journal_entry(
        MagicMock(
            posting_date=date(2026, 1, 15),
            description="Sales",
            source_document_type=None,
            source_document_id=None,
            lines=[
                MagicMock(
                    account_id=ar.id,
                    debit_amount=Decimal("200000.00"),
                    credit_amount=Decimal("0.00"),
                    description=None,
                ),
                MagicMock(
                    account_id=sales.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("200000.00"),
                    description=None,
                ),
            ],
        ),
        auto_post=True,
    )

    # 3. Cost of goods sold ₱80,000 (Dr COGS / Cr AP)
    gl_svc.create_journal_entry(
        MagicMock(
            posting_date=date(2026, 1, 20),
            description="COGS on account",
            source_document_type=None,
            source_document_id=None,
            lines=[
                MagicMock(
                    account_id=cogs.id,
                    debit_amount=Decimal("80000.00"),
                    credit_amount=Decimal("0.00"),
                    description=None,
                ),
                MagicMock(
                    account_id=ap.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("80000.00"),
                    description=None,
                ),
            ],
        ),
        auto_post=True,
    )

    # 4. Operating expense ₱30,000 paid from Cash (Dr OpEx / Cr Cash)
    gl_svc.create_journal_entry(
        MagicMock(
            posting_date=date(2026, 1, 25),
            description="Office rent & utilities",
            source_document_type=None,
            source_document_id=None,
            lines=[
                MagicMock(
                    account_id=opex.id,
                    debit_amount=Decimal("30000.00"),
                    credit_amount=Decimal("0.00"),
                    description=None,
                ),
                MagicMock(
                    account_id=cash.id,
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("30000.00"),
                    description=None,
                ),
            ],
        ),
        auto_post=True,
    )

    # Generate Income Statement for Jan 2026
    pnl = gl_svc.generate_income_statement(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert pnl.total_revenue == Decimal("200000.00")
    assert pnl.total_cogs == Decimal("80000.00")
    assert pnl.gross_profit == Decimal("120000.00")
    assert pnl.total_expenses == Decimal("30000.00")
    assert pnl.net_income == Decimal("90000.00")  # 120,000 - 30,000

    # Generate Balance Sheet as of Jan 31, 2026
    bs = gl_svc.generate_balance_sheet(as_of_date=date(2026, 1, 31))
    assert bs.is_balanced is True
    # Assets = Cash (500,000 - 30,000 = 470,000) + AR (200,000) = 670,000
    assert bs.total_assets == Decimal("670000.00")
    # Liabilities = AP (80,000)
    assert bs.total_liabilities == Decimal("80000.00")
    # Equity = Capital (500,000) + Net Income (90,000) = 590,000
    assert bs.current_period_net_income == Decimal("90000.00")
    assert bs.total_equity == Decimal("590000.00")
    # Liabilities + Equity = 80,000 + 590,000 = 670,000
    assert bs.total_liabilities_and_equity == Decimal("670000.00")


# =============================================================================
# 5. REST API Security & Financial Report Endpoints
# =============================================================================


def test_financial_report_api_endpoints(subledger_db: Session):
    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: subledger_db

    # Create authorized user
    user = User(
        email="analyst@finance.com",
        password_hash=hash_password("Pass123!"),
        full_name="Financial Analyst",
        is_active=True,
        is_superuser=False,
    )
    subledger_db.add(user)
    subledger_db.flush()

    role = subledger_db.query(Role).filter(Role.code == "finance").one()
    subledger_db.add(UserRole(user_id=user.id, role_id=role.id))
    subledger_db.commit()

    mock_session = MagicMock()
    app.dependency_overrides[get_current_user_and_session] = lambda: (user, mock_session)

    # 1. Balance Sheet endpoint
    res_bs = client.get("/api/v1/accounting/reports/balance-sheet?as_of_date=2026-12-31")
    assert res_bs.status_code == 200
    bs_data = res_bs.json()
    assert "is_balanced" in bs_data
    assert "total_assets" in bs_data
    assert "total_liabilities_and_equity" in bs_data

    # 2. Income Statement endpoint
    res_is = client.get(
        "/api/v1/accounting/reports/income-statement?start_date=2026-01-01&end_date=2026-12-31"
    )
    assert res_is.status_code == 200
    is_data = res_is.json()
    assert "total_revenue" in is_data
    assert "net_income" in is_data
    assert "gross_profit" in is_data

    # Cleanup
    app.dependency_overrides.clear()
