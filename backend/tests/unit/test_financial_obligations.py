from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import ControllableClock
from app.core.database import Base
from app.core.errors import AppException, BusinessRuleError
from app.core.numbering import DocumentSequence
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer, CustomerAddress
from app.modules.identity.models import User
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import (
    CreditNoteCreatePayload,
    CreditNoteItemCreatePayload,
    InvoiceCreateFromOrderPayload,
    InvoiceItemCreatePayload,
    LineItemPayload,
    PaymentAllocationCreatePayload,
    PaymentCreatePayload,
    SalesOrderCreatePayload,
)
from app.modules.sales.service import SalesService


@pytest.fixture
def fin_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session: Session = session_factory()

    # Seed sequences
    seqs = [
        DocumentSequence(doc_type="quote", prefix="QT", include_year=True, padding=6, next_value=1),
        DocumentSequence(
            doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="invoice", prefix="INV", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="payment", prefix="PAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="credit_note", prefix="CN", include_year=True, padding=6, next_value=1
        ),
    ]
    session.add_all(seqs)

    # Seed tax rates
    tr12 = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    tr0 = TaxRate(
        code="VAT0", name="VAT 0%", rate=Decimal("0.0000"), is_default=False, is_active=True
    )
    session.add_all([tr12, tr0])

    # Seed test user
    user = User(
        email="accountant@example.com",
        password_hash="fakehash",
        full_name="Accountant",
        is_active=True,
    )
    session.add(user)
    session.flush()

    # Seed category & product
    cat = ProductCategory(name="Materials")
    session.add(cat)
    session.flush()

    prod = Product(
        sku="MAT-001",
        name="Steel Beam",
        category_id=cat.id,
        uom="pc",
        list_price=Decimal("1000.00"),
        tax_rate_id=tr12.id,
        is_active=True,
    )
    session.add(prod)

    # Seed customer
    cust = Customer(
        customer_no="CUST-001",
        name="Acme Construction Corp",
        tin="123-456-789-000",
        payment_terms_days=30,
        status="active",
        credit_limit=Decimal("100000.00"),
    )
    session.add(cust)
    session.flush()

    addr = CustomerAddress(
        customer_id=cust.id,
        address_type="billing",
        line1="123 Builder St",
        city="Makati",
        is_default=True,
        is_active=True,
    )
    session.add(addr)

    session.commit()
    yield session
    session.close()


def test_invoice_creation_and_issuance_completes_order(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    # 1. Create and confirm Sales Order (10 units @ 1000 = 10,000 + 12% VAT = 11,200)
    so_payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        order_date=date(2026, 10, 8),
        items=[
            LineItemPayload(
                product_id=prod.id,
                quantity=Decimal("10.000"),
                unit_price=Decimal("1000.0000"),
            )
        ],
    )
    so = service.create_sales_order(so_payload, current_user_id=1)
    so = service.confirm_sales_order(so.id, current_user_id=1)
    assert so.status == "confirmed"

    # 2. Create invoice from order
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    assert inv.status == "draft"
    assert inv.invoice_no is None
    assert inv.grand_total == Decimal("11200.00")
    assert inv.balance_due == Decimal("11200.00")
    assert inv.amount_paid == Decimal("0.00")

    # 3. Issue invoice
    inv = service.issue_invoice(inv.id, current_user_id=1)
    assert inv.status == "issued"
    assert inv.invoice_no == "INV-2026-000001"
    assert inv.customer_name_snapshot == "Acme Construction Corp"
    assert inv.customer_tin_snapshot == "123-456-789-000"
    assert "123 Builder St" in (inv.billing_address_snapshot or "")
    assert inv.due_date == date(2026, 11, 7)  # +30 days

    # Verify SO line quantity_invoiced and auto-completion
    fin_db.refresh(so)
    assert so.items[0].quantity_invoiced == Decimal("10.000")
    assert so.status == "completed"


def test_partial_invoicing_workflow(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    so_payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        order_date=date(2026, 10, 8),
        items=[
            LineItemPayload(
                product_id=prod.id,
                quantity=Decimal("10.000"),
                unit_price=Decimal("1000.0000"),
            )
        ],
    )
    so = service.create_sales_order(so_payload, current_user_id=1)
    so = service.confirm_sales_order(so.id, current_user_id=1)
    so_item = so.items[0]

    # Partial invoice: 4 units
    part1_payload = InvoiceCreateFromOrderPayload(
        items=[
            InvoiceItemCreatePayload(
                sales_order_item_id=so_item.id,
                quantity=Decimal("4.000"),
                unit_price=so_item.unit_price,
            )
        ]
    )
    inv1 = service.create_invoice_from_order(so.id, payload=part1_payload, current_user_id=1)
    inv1 = service.issue_invoice(inv1.id, current_user_id=1)
    assert inv1.invoice_no == "INV-2026-000001"

    fin_db.refresh(so)
    assert so.items[0].quantity_invoiced == Decimal("4.000")
    assert so.status == "confirmed"  # Not completed yet

    # Try to invoice 7 units (which exceeds remaining 6 units) -> raises BusinessRuleError
    over_payload = InvoiceCreateFromOrderPayload(
        items=[
            InvoiceItemCreatePayload(
                sales_order_item_id=so_item.id,
                quantity=Decimal("7.000"),
                unit_price=so_item.unit_price,
            )
        ]
    )
    with pytest.raises(BusinessRuleError, match="exceeds remaining uninvoiced"):
        service.create_invoice_from_order(so.id, payload=over_payload, current_user_id=1)

    # Invoice remaining 6 units
    inv2 = service.create_invoice_from_order(so.id, current_user_id=1)
    assert inv2.items[0].quantity == Decimal("6.000")
    inv2 = service.issue_invoice(inv2.id, current_user_id=1)
    assert inv2.invoice_no == "INV-2026-000002"

    fin_db.refresh(so)
    assert so.items[0].quantity_invoiced == Decimal("10.000")
    assert so.status == "completed"


def test_payment_allocations_and_derived_invoice_status(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    # Create and confirm order: 10 units @ 1000 = 10,000 net, 11,200 gross
    so = service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("10.000"), unit_price=Decimal("1000.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    so = service.confirm_sales_order(so.id, current_user_id=1)
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    inv = service.issue_invoice(inv.id, current_user_id=1)
    assert inv.balance_due == Decimal("11200.00")

    # 1. Create a payment for ₱15,000 (overpayment)
    pay = service.create_payment(
        PaymentCreatePayload(
            customer_id=cust.id,
            method="bank_transfer",
            reference_no="BDO-TXN-9988",
            amount=Decimal("15000.00"),
        ),
        current_user_id=1,
    )
    assert pay.payment_no == "PAY-2026-000001"
    assert pay.amount == Decimal("15000.00")
    assert pay.amount_allocated == Decimal("0.00")

    # 2. Allocate partial ₱5,000
    alloc1 = service.allocate_payment(pay.id, inv.id, Decimal("5000.00"), current_user_id=1)
    assert alloc1.amount == Decimal("5000.00")

    fin_db.refresh(pay)
    fin_db.refresh(inv)
    assert pay.amount_allocated == Decimal("5000.00")
    assert inv.amount_paid == Decimal("5000.00")
    assert inv.balance_due == Decimal("6200.00")
    assert inv.status == "partially_paid"

    # 3. Allocate remaining ₱6,200
    service.allocate_payment(pay.id, inv.id, Decimal("6200.00"), current_user_id=1)
    fin_db.refresh(pay)
    fin_db.refresh(inv)
    assert pay.amount_allocated == Decimal("11200.00")
    assert inv.amount_paid == Decimal("11200.00")
    assert inv.balance_due == Decimal("0.00")
    assert inv.status == "paid"

    # Unallocated credit remaining on payment = 15,000 - 11,200 = 3,800
    unallocated = pay.amount - pay.amount_allocated
    assert unallocated == Decimal("3800.00")

    # 4. Attempt to allocate to already paid invoice raises BusinessRuleError
    with pytest.raises(BusinessRuleError, match="status 'paid'"):
        service.allocate_payment(pay.id, inv.id, Decimal("100.00"), current_user_id=1)


def test_void_payment_restores_invoice_balance(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    so = service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("1.000"), unit_price=Decimal("1000.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    so = service.confirm_sales_order(so.id, current_user_id=1)
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    inv = service.issue_invoice(inv.id, current_user_id=1)
    assert inv.grand_total == Decimal("1120.00")

    # Pay full
    pay = service.create_payment(
        PaymentCreatePayload(
            customer_id=cust.id,
            method="cash",
            amount=Decimal("1120.00"),
            allocations=[
                PaymentAllocationCreatePayload(invoice_id=inv.id, amount=Decimal("1120.00"))
            ],
        ),
        current_user_id=1,
    )
    fin_db.refresh(inv)
    assert inv.status == "paid"
    assert inv.balance_due == Decimal("0.00")

    # Void payment
    pay = service.void_payment(pay.id, reason="Check bounced", current_user_id=1)
    assert pay.status == "void"
    assert pay.amount_allocated == Decimal("0.00")

    fin_db.refresh(inv)
    assert inv.status == "issued"
    assert inv.amount_paid == Decimal("0.00")
    assert inv.balance_due == Decimal("1120.00")


def test_credit_note_reduces_balance(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    so = service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("2.000"), unit_price=Decimal("1000.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    so = service.confirm_sales_order(so.id, current_user_id=1)
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    inv = service.issue_invoice(inv.id, current_user_id=1)
    assert inv.grand_total == Decimal("2240.00")

    # Issue credit note for 1 unit damaged item (1,000 + 12% = 1,120)
    inv_item = inv.items[0]
    cn_payload = CreditNoteCreatePayload(
        invoice_id=inv.id,
        reason="damaged",
        items=[
            CreditNoteItemCreatePayload(
                invoice_item_id=inv_item.id,
                quantity=Decimal("1.000"),
                unit_price=inv_item.unit_price,
            )
        ],
    )
    cn = service.create_credit_note(cn_payload, current_user_id=1)
    assert cn.credit_note_no == "CN-2026-000001"
    assert cn.grand_total == Decimal("1120.00")

    fin_db.refresh(inv)
    assert inv.amount_credited == Decimal("1120.00")
    assert inv.balance_due == Decimal("1120.00")
    assert inv.status == "issued"

    # Issue another credit note settling remaining balance
    cn2 = service.create_credit_note(
        CreditNoteCreatePayload(invoice_id=inv.id, reason="discount"),
        current_user_id=1,
    )
    assert cn2.credit_note_no == "CN-2026-000002"
    fin_db.refresh(inv)
    assert inv.amount_credited == Decimal("2240.00")
    assert inv.balance_due == Decimal("0.00")
    assert inv.status == "paid"


def test_void_invoice_and_order_reversion(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    so = service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("1.000"), unit_price=Decimal("1000.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    so = service.confirm_sales_order(so.id, current_user_id=1)
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    inv = service.issue_invoice(inv.id, current_user_id=1)

    fin_db.refresh(so)
    assert so.status == "completed"

    # Void the invoice
    inv = service.void_invoice(inv.id, reason="Issued in error", current_user_id=1)
    assert inv.status == "void"
    assert inv.balance_due == Decimal("0.00")

    fin_db.refresh(so)
    assert so.items[0].quantity_invoiced == Decimal("0.000")
    assert so.status == "confirmed"


def test_idempotency_replay_and_conflict(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    # Initial check (not found)
    is_cached, status_code, body = service.check_idempotency(
        user_id=1, key="idem-key-123", request_hash="hash-aaa"
    )
    assert is_cached is False

    # Record result
    service.record_idempotency_result(
        user_id=1,
        key="idem-key-123",
        method="POST",
        path="/payments",
        request_hash="hash-aaa",
        status_code=201,
        response_body={"payment_no": "PAY-2026-000001"},
    )

    # Replay with same hash
    is_cached, status_code, body = service.check_idempotency(
        user_id=1, key="idem-key-123", request_hash="hash-aaa"
    )
    assert is_cached is True
    assert status_code == 201
    assert body == {"payment_no": "PAY-2026-000001"}

    # Replay with DIFFERENT hash raises 422 IDEMPOTENCY_CONFLICT
    with pytest.raises(AppException) as exc_info:
        service.check_idempotency(user_id=1, key="idem-key-123", request_hash="hash-bbb")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


def test_customer_statement_reconciliation(fin_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    service = SalesService(fin_db, clock=clock)

    cust = fin_db.query(Customer).first()
    prod = fin_db.query(Product).first()

    # Invoice 1: 10 units = ₱11,200
    so = service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("10.000"), unit_price=Decimal("1000.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    so = service.confirm_sales_order(so.id, current_user_id=1)
    inv = service.create_invoice_from_order(so.id, current_user_id=1)
    inv = service.issue_invoice(inv.id, current_user_id=1)

    # Payment: ₱15,000 (₱11,200 allocated to invoice, ₱3,800 unallocated credit)
    service.create_payment(
        PaymentCreatePayload(
            customer_id=cust.id,
            method="bank_transfer",
            amount=Decimal("15000.00"),
            allocations=[
                PaymentAllocationCreatePayload(invoice_id=inv.id, amount=Decimal("11200.00"))
            ],
        ),
        current_user_id=1,
    )

    stmt = service.get_customer_statement(cust.id)
    assert Decimal(stmt.total_invoiced) == Decimal("11200.00")
    assert Decimal(stmt.total_paid) == Decimal("15000.00")
    assert Decimal(stmt.unallocated_credit) == Decimal("3800.00")
    # Net AR = 0 invoice balance - 3,800 customer credit = -3,800
    assert Decimal(stmt.open_ar_balance) == Decimal("-3800.00")
    assert len(stmt.transactions) == 2
