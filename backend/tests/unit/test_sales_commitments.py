from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import ControllableClock
from app.core.database import Base
from app.core.errors import BusinessRuleError
from app.core.numbering import DocumentSequence
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer, CustomerAddress, Opportunity
from app.modules.identity.models import User
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import (
    LineItemPayload,
    QuoteCreatePayload,
    QuoteUpdatePayload,
    SalesOrderCreatePayload,
)
from app.modules.sales.service import SalesService


@pytest.fixture
def test_db():
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
    ]
    session.add_all(seqs)

    # Seed tax rate
    tr12 = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    session.add(tr12)

    # Seed test user
    user = User(
        email="salesrep@example.com",
        password_hash="fakehash",
        full_name="Sales Representative",
        is_active=True,
    )
    session.add(user)
    session.flush()

    # Seed category & product
    cat = ProductCategory(name="Hardware")
    session.add(cat)
    session.flush()

    prod = Product(
        sku="PROD-001",
        name="Enterprise Server Unit",
        category_id=cat.id,
        product_type="stock",
        uom="pc",
        list_price=Decimal("10000.0000"),
        tax_rate_id=tr12.id,
        is_active=True,
    )
    session.add(prod)

    # Seed customer
    cust = Customer(
        customer_no="CUS-000001",
        name="Acme Corp",
        customer_type="company",
        status="prospect",
        payment_terms_days=30,
        credit_limit=Decimal("50000.00"),
    )
    session.add(cust)
    session.flush()

    # Customer addresses
    b_addr = CustomerAddress(
        customer_id=cust.id,
        address_type="billing",
        line1="123 Ayala Ave",
        city="Makati City",
        province="Metro Manila",
        country_code="PH",
        is_default=True,
        is_active=True,
    )
    s_addr = CustomerAddress(
        customer_id=cust.id,
        address_type="shipping",
        line1="456 Warehouse Rd",
        city="Taguig City",
        province="Metro Manila",
        country_code="PH",
        is_default=True,
        is_active=True,
    )
    session.add_all([b_addr, s_addr])
    session.commit()

    yield session
    session.close()


def test_quote_lifecycle_and_snapshots(test_db: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))
    service = SalesService(test_db, clock=clock)

    cust = test_db.query(Customer).first()
    prod = test_db.query(Product).first()

    # 1. Create quote
    payload = QuoteCreatePayload(
        customer_id=cust.id,
        valid_until=date(2026, 3, 31),
        items=[
            LineItemPayload(
                product_id=prod.id,
                quantity=Decimal("3.000"),
                unit_price=Decimal("10000.0000"),
                discount_amount=Decimal("1000.00"),  # 30,000 - 1,000 = 29,000 net
            )
        ],
    )
    quote = service.create_quote(payload, current_user_id=1)

    assert quote.quote_no.startswith("QT-2026-")
    assert quote.status == "draft"
    assert quote.subtotal == Decimal("29000.00")
    # Tax: 29000 * 0.12 = 3480.00
    assert quote.tax_total == Decimal("3480.00")
    # Grand total: 29000 + 3480 = 32480.00
    assert quote.grand_total == Decimal("32480.00")

    # 2. Modify catalog price to test snapshot immutability
    prod.list_price = Decimal("15000.0000")
    test_db.commit()

    reloaded_quote = service.get_quote(quote.id)
    assert reloaded_quote.items[0].unit_price == Decimal("10000.0000")
    assert reloaded_quote.grand_total == Decimal("32480.00")

    # 3. Send quote
    service.send_quote(quote.id, current_user_id=1)
    assert quote.status == "sent"
    assert quote.issue_date == date(2026, 3, 1)

    # 4. Modifying sent quote should be rejected
    with pytest.raises(BusinessRuleError) as exc:
        service.update_quote(
            quote.id,
            QuoteUpdatePayload(
                items=[LineItemPayload(quantity=Decimal("1.000"), unit_price=Decimal("100.0000"))],
                version=quote.version,
            ),
        )
    assert exc.value.code == "QUOTE_IMMUTABLE"

    # 5. Accept quote
    service.accept_quote(quote.id, current_user_id=1)
    assert quote.status == "accepted"


def test_quote_linked_opportunity_auto_win(test_db: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))
    service = SalesService(test_db, clock=clock)

    cust = test_db.query(Customer).first()
    opp = Opportunity(
        opportunity_no="OPP-000001",
        name="Server Upgrade",
        customer_id=cust.id,
        stage="proposal",
        estimated_amount=Decimal("30000.00"),
        probability=Decimal("0.5000"),
    )
    test_db.add(opp)
    test_db.commit()

    # Create quote linked to opportunity
    payload = QuoteCreatePayload(
        customer_id=cust.id,
        opportunity_id=opp.id,
        valid_until=date(2026, 3, 31),
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("30000.0000"),
            )
        ],
    )
    quote = service.create_quote(payload, current_user_id=1)
    service.send_quote(quote.id, current_user_id=1)

    # Accept quote
    service.accept_quote(quote.id, current_user_id=1)

    # Verify opportunity automatically won and customer promoted to active
    test_db.refresh(opp)
    test_db.refresh(cust)
    assert opp.stage == "won"
    assert opp.probability == Decimal("1.0000")
    assert opp.closed_at is not None
    assert cust.status == "active"


def test_quote_expiration_check(test_db: Session):
    clock = ControllableClock(initial_time=datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC))  # April 1
    service = SalesService(test_db, clock=clock)

    cust = test_db.query(Customer).first()
    payload = QuoteCreatePayload(
        customer_id=cust.id,
        valid_until=date(2026, 3, 15),  # Expired in March
        items=[LineItemPayload(quantity=Decimal("1.000"), unit_price=Decimal("5000.0000"))],
    )
    quote = service.create_quote(payload)
    service.send_quote(quote.id)

    with pytest.raises(BusinessRuleError) as exc:
        service.accept_quote(quote.id)
    assert exc.value.code == "QUOTE_EXPIRED"


def test_sales_order_from_quote_and_confirm(test_db: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))
    service = SalesService(test_db, clock=clock)

    cust = test_db.query(Customer).first()
    cust.status = "prospect"
    cust.credit_limit = Decimal("100000.00")
    test_db.commit()

    payload = QuoteCreatePayload(
        customer_id=cust.id,
        items=[LineItemPayload(quantity=Decimal("2.000"), unit_price=Decimal("10000.0000"))],
    )
    quote = service.create_quote(payload)
    service.send_quote(quote.id)
    service.accept_quote(quote.id)

    # Create Sales Order from Quote
    so = service.create_order_from_quote(quote.id, current_user_id=1)
    assert so.order_no.startswith("SO-2026-")
    assert so.status == "draft"
    assert so.grand_total == quote.grand_total
    assert len(so.items) == len(quote.items)

    # Confirm order
    confirmed_so = service.confirm_sales_order(so.id, current_user_id=1)
    assert confirmed_so.status == "confirmed"
    assert "Ayala Ave" in confirmed_so.billing_address_snapshot
    assert "Warehouse Rd" in confirmed_so.shipping_address_snapshot
    assert confirmed_so.payment_terms_days_snapshot == 30

    # Prospect customer should now be active
    test_db.refresh(cust)
    assert cust.status == "active"


def test_credit_limit_exceeded_rejection(test_db: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))
    service = SalesService(test_db, clock=clock)

    cust = test_db.query(Customer).first()
    cust.credit_limit = Decimal("20000.00")  # Limit ₱20,000
    test_db.commit()

    # Create order with ₱25,000 total (25000 + 12% = 28,000)
    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[LineItemPayload(quantity=Decimal("2.500"), unit_price=Decimal("10000.0000"))],
    )
    so = service.create_sales_order(payload)

    # Confirming order should be rejected due to credit limit
    with pytest.raises(BusinessRuleError) as exc:
        service.confirm_sales_order(so.id)
    assert exc.value.code == "CREDIT_LIMIT_EXCEEDED"
