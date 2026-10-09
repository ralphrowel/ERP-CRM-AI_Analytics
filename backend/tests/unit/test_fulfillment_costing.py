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
from app.modules.crm.models import Customer, CustomerAddress
from app.modules.identity.models import User
from app.modules.inventory.models import InventoryBalance, InventoryTransaction, Warehouse
from app.modules.inventory.schemas import (
    OpeningBalanceItemPayload,
    OpeningBalancesCreatePayload,
    ShipmentCreatePayload,
    ShipmentItemCreatePayload,
    StockAdjustmentCreatePayload,
    StockAdjustmentItemCreatePayload,
    StockTransferCreatePayload,
    StockTransferItemCreatePayload,
)
from app.modules.inventory.service import InventoryService
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import (
    LineItemPayload,
    PaymentAllocationCreatePayload,
    PaymentCreatePayload,
    SalesOrderCreatePayload,
)
from app.modules.sales.service import SalesService


@pytest.fixture
def ful_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session: Session = session_factory()

    # Seed sequences
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
            doc_type="payment", prefix="PAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="credit_note", prefix="CN", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="shipment", prefix="SHP", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="stock_adjustment", prefix="ADJ", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="stock_transfer", prefix="TRF", include_year=True, padding=6, next_value=1
        ),
    ]
    session.add_all(seqs)

    # Seed tax rates
    tr12 = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    session.add(tr12)

    # Seed user
    user = User(
        email="warehouse@example.com",
        password_hash="hash",
        full_name="Warehouse Ops",
        is_active=True,
    )
    session.add(user)
    session.flush()

    # Seed warehouses
    wh_main = Warehouse(
        code="WH-MAIN", name="Main Warehouse Manila", is_active=True, is_default=True
    )
    wh_cebu = Warehouse(code="WH-CEBU", name="Regional Hub Cebu", is_active=True, is_default=False)
    session.add_all([wh_main, wh_cebu])
    session.flush()

    # Seed catalog
    cat = ProductCategory(name="Hardware")
    session.add(cat)
    session.flush()

    p_stock = Product(
        sku="HDW-001",
        name="Heavy Bolt",
        category_id=cat.id,
        uom="box",
        list_price=Decimal("200.00"),
        tax_rate_id=tr12.id,
        product_type="stock",
        is_active=True,
    )
    p_service = Product(
        sku="SRV-001",
        name="Installation Service",
        category_id=cat.id,
        uom="hr",
        list_price=Decimal("500.00"),
        tax_rate_id=tr12.id,
        product_type="service",
        is_active=True,
    )
    session.add_all([p_stock, p_service])
    session.flush()

    # Seed customers (one credit, one prepaid)
    cust_credit = Customer(
        customer_no="CUST-CREDIT",
        name="Credit Construction Corp",
        tin="111-222-333-000",
        payment_terms_days=30,
        credit_limit=Decimal("50000.00"),
        status="active",
    )
    cust_prepaid = Customer(
        customer_no="CUST-PREPAID",
        name="Prepaid Builders Inc",
        tin="444-555-666-000",
        payment_terms_days=0,
        credit_limit=Decimal("0.00"),
        status="active",
    )
    session.add_all([cust_credit, cust_prepaid])
    session.flush()

    addr = CustomerAddress(
        customer_id=cust_credit.id,
        address_type="billing",
        line1="100 Business St",
        city="Manila",
        is_default=True,
        is_active=True,
    )
    session.add(addr)

    session.commit()
    yield session
    session.close()


def test_shipment_lifecycle_and_cogs_snapshot(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    # 1. Establish opening stock: 100 boxes @ 120.00 WAC
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("100.000"),
                    unit_cost=Decimal("120.0000"),
                )
            ],
        ),
        user_id=1,
    )

    # 2. Create and confirm Sales Order: 20 boxes
    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("20.000"),
                    unit_price=Decimal("200.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    # Verify reservation: on_hand=100, reserved=20, available=80
    bal = ful_db.query(InventoryBalance).filter_by(product_id=p_stock.id, warehouse_id=wh.id).one()
    assert bal.qty_on_hand == Decimal("100.000")
    assert bal.qty_reserved == Decimal("20.000")
    assert bal.qty_available == Decimal("80.000")

    # 3. Create draft shipment
    shipment = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )
    assert shipment.status == "draft"
    assert shipment.shipment_no is None
    assert len(shipment.items) == 1
    assert shipment.items[0].quantity == Decimal("20.000")
    assert shipment.items[0].unit_cost is None
    assert shipment.items[0].cogs_amount is None

    # 4. Post shipment
    posted_shp = inv_service.post_shipment(shipment.id, current_user_id=1)
    assert posted_shp.status == "posted"
    assert posted_shp.shipment_no == "SHP-2026-000001"
    assert posted_shp.shipped_at == clock.now()
    assert posted_shp.items[0].unit_cost == Decimal("120.0000")
    assert posted_shp.items[0].cogs_amount == Decimal("2400.00")  # 20 * 120 = 2400
    assert posted_shp.total_cogs == Decimal("2400.00")

    # 5. Check balances: on_hand=80, reserved=0, available=80
    ful_db.refresh(bal)
    assert bal.qty_on_hand == Decimal("80.000")
    assert bal.qty_reserved == Decimal("0.000")
    assert bal.qty_available == Decimal("80.000")

    # 6. Check ledger row
    txn = (
        ful_db.query(InventoryTransaction)
        .filter_by(source_type="shipment", source_id=posted_shp.id)
        .one()
    )
    assert txn.txn_type == "issue"
    assert txn.quantity == Decimal("-20.000")
    assert txn.unit_cost == Decimal("120.0000")
    assert txn.total_cost == Decimal("-2400.00")
    assert txn.qty_on_hand_after == Decimal("80.000")
    assert txn.avg_cost_after == Decimal("120.0000")

    # 7. Check sales order status transitioned to "shipped"
    ful_db.refresh(so)
    assert so.items[0].quantity_shipped == Decimal("20.000")
    assert so.status == "shipped"


def test_partial_shipment_workflow(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    # 50 units @ 100.00
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("50.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("30.000"),
                    unit_price=Decimal("200.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)
    so_item = so.items[0]

    # Partial shipment #1: 10 units
    shp1 = inv_service.create_shipment(
        ShipmentCreatePayload(
            sales_order_id=so.id,
            items=[
                ShipmentItemCreatePayload(
                    sales_order_item_id=so_item.id, quantity=Decimal("10.000")
                )
            ],
        ),
        current_user_id=1,
    )
    inv_service.post_shipment(shp1.id, current_user_id=1)

    ful_db.refresh(so)
    assert so.status == "partially_shipped"
    assert so.items[0].quantity_shipped == Decimal("10.000")

    # Partial shipment #2: Remaining 20 units
    shp2 = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )
    assert shp2.items[0].quantity == Decimal("20.000")
    inv_service.post_shipment(shp2.id, current_user_id=1)

    ful_db.refresh(so)
    assert so.status == "shipped"
    assert so.items[0].quantity_shipped == Decimal("30.000")

    # Attempting to create another shipment fails because all items are fulfilled
    with pytest.raises(BusinessRuleError) as exc:
        inv_service.create_shipment(ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1)
    assert exc.value.code == "ORDER_ALREADY_FULFILLED"


def test_prepaid_rule_enforcement(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust_prepaid = ful_db.query(Customer).filter_by(customer_no="CUST-PREPAID").first()

    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("50.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust_prepaid.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id, quantity=Decimal("5.000"), unit_price=Decimal("200.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)
    assert so.payment_terms_days_snapshot == 0

    shp = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )

    # 1. Attempting to post shipment with NO invoice issued yet fails
    with pytest.raises(BusinessRuleError) as exc:
        inv_service.post_shipment(shp.id, current_user_id=1)
    assert exc.value.code == "PREPAYMENT_REQUIRED"

    # 2. Issue invoice (still unpaid) -> posting shipment still fails
    inv = sales_service.create_invoice_from_order(so.id, current_user_id=1)
    sales_service.issue_invoice(inv.id, current_user_id=1)
    assert inv.status == "issued"

    with pytest.raises(BusinessRuleError) as exc:
        inv_service.post_shipment(shp.id, current_user_id=1)
    assert exc.value.code == "PREPAYMENT_REQUIRED"

    # 3. Pay invoice in full -> posting shipment succeeds!
    sales_service.create_payment(
        PaymentCreatePayload(
            customer_id=cust_prepaid.id,
            method="bank_transfer",
            amount=inv.grand_total,
            allocations=[PaymentAllocationCreatePayload(invoice_id=inv.id, amount=inv.grand_total)],
        ),
        current_user_id=1,
    )
    ful_db.refresh(inv)
    assert inv.status == "paid"

    posted = inv_service.post_shipment(shp.id, current_user_id=1)
    assert posted.status == "posted"

    # Fully shipped and fully invoiced -> order completed!
    ful_db.refresh(so)
    assert so.status == "completed"


def test_cancel_order_blocked_if_shipped(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("20.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("10.000"),
                    unit_price=Decimal("200.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    shp = inv_service.create_shipment(
        ShipmentCreatePayload(
            sales_order_id=so.id,
            items=[
                ShipmentItemCreatePayload(
                    sales_order_item_id=so.items[0].id, quantity=Decimal("3.000")
                )
            ],
        ),
        current_user_id=1,
    )
    inv_service.post_shipment(shp.id, current_user_id=1)

    # Attempting to cancel sales order fails
    with pytest.raises(BusinessRuleError) as exc:
        sales_service.cancel_sales_order(so.id, reason="Customer cancelled", current_user_id=1)
    assert exc.value.code == "ORDER_ALREADY_SHIPPED"


def test_draft_shipment_cancellation(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("10.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id, quantity=Decimal("5.000"), unit_price=Decimal("200.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    shp = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )
    cancelled = inv_service.cancel_shipment(shp.id, current_user_id=1)
    assert cancelled.status == "cancelled"

    # Attempting to post cancelled shipment fails
    with pytest.raises(BusinessRuleError) as exc:
        inv_service.post_shipment(shp.id, current_user_id=1)
    assert exc.value.code == "INVALID_TRANSITION"


def test_stock_adjustment_positive_and_negative(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()

    # Initial opening: 10 units @ 100.0000 = 1000.00
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("10.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    # 1. Positive adjustment: found 5 units @ 130.0000
    # New avg = (10*100 + 5*130) / (10+5) = (1000 + 650) / 15 = 1650 / 15 = 110.0000
    adj_pos = inv_service.create_stock_adjustment(
        StockAdjustmentCreatePayload(
            warehouse_id=wh.id,
            reason="found",
            items=[
                StockAdjustmentItemCreatePayload(
                    product_id=p_stock.id,
                    quantity_change=Decimal("5.000"),
                    unit_cost=Decimal("130.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    posted_pos = inv_service.post_stock_adjustment(adj_pos.id, current_user_id=1)
    assert posted_pos.status == "posted"
    assert posted_pos.adjustment_no == "ADJ-2026-000001"

    bal = ful_db.query(InventoryBalance).filter_by(product_id=p_stock.id, warehouse_id=wh.id).one()
    assert bal.qty_on_hand == Decimal("15.000")
    assert bal.avg_unit_cost == Decimal("110.0000")

    # 2. Negative adjustment: 3 units damaged
    # Should use current avg 110.0000 without altering avg
    adj_neg = inv_service.create_stock_adjustment(
        StockAdjustmentCreatePayload(
            warehouse_id=wh.id,
            reason="damage",
            items=[
                StockAdjustmentItemCreatePayload(
                    product_id=p_stock.id, quantity_change=Decimal("-3.000")
                )
            ],
        ),
        current_user_id=1,
    )
    posted_neg = inv_service.post_stock_adjustment(adj_neg.id, current_user_id=1)
    assert posted_neg.status == "posted"

    ful_db.refresh(bal)
    assert bal.qty_on_hand == Decimal("12.000")
    assert bal.avg_unit_cost == Decimal("110.0000")

    # 3. Negative adjustment exceeding available stock (let's reserve 10 units first)
    bal.qty_reserved = Decimal("10.000")
    ful_db.commit()

    # on_hand=12, reserved=10 -> available is 2. Attempting to reduce by 3 should fail
    adj_fail = inv_service.create_stock_adjustment(
        StockAdjustmentCreatePayload(
            warehouse_id=wh.id,
            reason="loss",
            items=[
                StockAdjustmentItemCreatePayload(
                    product_id=p_stock.id, quantity_change=Decimal("-3.000")
                )
            ],
        ),
        current_user_id=1,
    )
    with pytest.raises(BusinessRuleError) as exc:
        inv_service.post_stock_adjustment(adj_fail.id, current_user_id=1)
    assert exc.value.code == "ADJUSTMENT_EXCEEDS_AVAILABLE"


def test_stock_transfer_between_warehouses(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)

    wh_main = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    wh_cebu = ful_db.query(Warehouse).filter_by(code="WH-CEBU").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()

    # 1. Opening balance in Manila: 20 units @ 100.00
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh_main.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("20.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )
    # Opening balance in Cebu: 10 units @ 160.00
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh_cebu.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("10.000"), unit_cost=Decimal("160.0000")
                )
            ],
        ),
        user_id=1,
    )

    # 2. Transfer 10 units from Manila to Cebu
    # Source unit cost is 100.00
    # Destination has 10 @ 160 = 1600. Receiving 10 @ 100 = 1000.
    # New Cebu avg = (1600 + 1000) / 20 = 2600 / 20 = 130.0000!
    trf = inv_service.create_stock_transfer(
        StockTransferCreatePayload(
            from_warehouse_id=wh_main.id,
            to_warehouse_id=wh_cebu.id,
            items=[
                StockTransferItemCreatePayload(product_id=p_stock.id, quantity=Decimal("10.000"))
            ],
        ),
        current_user_id=1,
    )
    assert trf.status == "draft"

    posted_trf = inv_service.post_stock_transfer(trf.id, current_user_id=1)
    assert posted_trf.status == "posted"
    assert posted_trf.transfer_no == "TRF-2026-000001"
    assert posted_trf.items[0].unit_cost == Decimal("100.0000")

    # Verify Manila balances
    bal_main = (
        ful_db.query(InventoryBalance)
        .filter_by(product_id=p_stock.id, warehouse_id=wh_main.id)
        .one()
    )
    assert bal_main.qty_on_hand == Decimal("10.000")
    assert bal_main.avg_unit_cost == Decimal("100.0000")

    # Verify Cebu balances
    bal_cebu = (
        ful_db.query(InventoryBalance)
        .filter_by(product_id=p_stock.id, warehouse_id=wh_cebu.id)
        .one()
    )
    assert bal_cebu.qty_on_hand == Decimal("20.000")
    assert bal_cebu.avg_unit_cost == Decimal("130.0000")

    # 3. Test transferring identical warehouse rejection
    with pytest.raises(BusinessRuleError) as exc:
        inv_service.create_stock_transfer(
            StockTransferCreatePayload(
                from_warehouse_id=wh_main.id,
                to_warehouse_id=wh_main.id,
                items=[
                    StockTransferItemCreatePayload(product_id=p_stock.id, quantity=Decimal("1.000"))
                ],
            ),
            current_user_id=1,
        )
    assert exc.value.code == "IDENTICAL_WAREHOUSES"


def test_order_completion_when_fully_shipped_and_fully_invoiced(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("50.000"), unit_cost=Decimal("100.0000")
                )
            ],
        ),
        user_id=1,
    )

    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("10.000"),
                    unit_price=Decimal("200.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    # 1. Post shipment for all items -> status is "shipped" (not yet invoiced)
    shp = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )
    inv_service.post_shipment(shp.id, current_user_id=1)

    ful_db.refresh(so)
    assert so.status == "shipped"

    # 2. Issue invoice for all items -> transitions to "completed"
    inv = sales_service.create_invoice_from_order(so.id, current_user_id=1)
    sales_service.issue_invoice(inv.id, current_user_id=1)

    ful_db.refresh(so)
    assert so.status == "completed"


def test_ledger_reconciliation_integrity(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    p_stock = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    # 1. Opening balance
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=p_stock.id, quantity=Decimal("100.000"), unit_cost=Decimal("50.0000")
                )
            ],
        ),
        user_id=1,
    )

    # 2. Sales order and shipment
    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=p_stock.id,
                    quantity=Decimal("25.000"),
                    unit_price=Decimal("100.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    shp = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id), current_user_id=1
    )
    inv_service.post_shipment(shp.id, current_user_id=1)

    # 3. Stock adjustment
    adj = inv_service.create_stock_adjustment(
        StockAdjustmentCreatePayload(
            warehouse_id=wh.id,
            reason="damage",
            items=[
                StockAdjustmentItemCreatePayload(
                    product_id=p_stock.id, quantity_change=Decimal("-5.000")
                )
            ],
        ),
        current_user_id=1,
    )
    inv_service.post_stock_adjustment(adj.id, current_user_id=1)

    # Run reconciliation
    rec = inv_service.get_inventory_reconciliation()
    assert rec.total_items_checked >= 1
    assert rec.discrepant_count == 0
    for it in rec.items:
        assert it.is_reconciled is True


def test_fulfillment_service_end_to_end_flow(ful_db: Session):
    clock = ControllableClock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=UTC))
    inv_service = InventoryService(ful_db, clock=clock)
    sales_service = SalesService(ful_db, clock=clock)

    wh1 = ful_db.query(Warehouse).filter_by(code="WH-MAIN").first()
    wh2 = ful_db.query(Warehouse).filter_by(code="WH-CEBU").first()
    prod = ful_db.query(Product).filter_by(sku="HDW-001").first()
    cust = ful_db.query(Customer).filter_by(customer_no="CUST-CREDIT").first()

    # 1. Opening balance
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=wh1.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=prod.id, quantity=Decimal("100.000"), unit_cost=Decimal("50.0000")
                )
            ],
        ),
        user_id=1,
    )

    # 2. Stock adjustment flow
    adj = inv_service.create_stock_adjustment(
        StockAdjustmentCreatePayload(
            warehouse_id=wh1.id,
            reason="count_correction",
            notes="Annual count",
            items=[
                StockAdjustmentItemCreatePayload(
                    product_id=prod.id,
                    quantity_change=Decimal("10.000"),
                    unit_cost=Decimal("60.0000"),
                )
            ],
        ),
        current_user_id=1,
    )
    assert adj.status == "draft"

    list_adj = inv_service.list_stock_adjustments(warehouse_id=wh1.id)
    assert len(list_adj) >= 1

    posted_adj = inv_service.post_stock_adjustment(adj.id, current_user_id=1)
    assert posted_adj.status == "posted"
    assert posted_adj.adjustment_no.startswith("ADJ-")

    # 3. Stock transfer flow
    trf = inv_service.create_stock_transfer(
        StockTransferCreatePayload(
            from_warehouse_id=wh1.id,
            to_warehouse_id=wh2.id,
            notes="Replenish Cebu",
            items=[StockTransferItemCreatePayload(product_id=prod.id, quantity=Decimal("20.000"))],
        ),
        current_user_id=1,
    )
    assert trf.status == "draft"

    list_trf = inv_service.list_stock_transfers(warehouse_id=wh1.id)
    assert len(list_trf) >= 1

    posted_trf = inv_service.post_stock_transfer(trf.id, current_user_id=1)
    assert posted_trf.status == "posted"
    assert posted_trf.transfer_no.startswith("TRF-")

    # 4. Shipment flow
    so = sales_service.create_sales_order(
        SalesOrderCreatePayload(
            customer_id=cust.id,
            warehouse_id=wh1.id,
            order_date=date(2026, 10, 8),
            items=[
                LineItemPayload(
                    product_id=prod.id, quantity=Decimal("15.000"), unit_price=Decimal("100.0000")
                )
            ],
        ),
        current_user_id=1,
    )
    sales_service.confirm_sales_order(so.id, current_user_id=1)

    shp = inv_service.create_shipment(
        ShipmentCreatePayload(sales_order_id=so.id, carrier="LBC", tracking_no="TRK123"),
        current_user_id=1,
    )
    assert shp.status == "draft"

    list_shp = inv_service.list_shipments(warehouse_id=wh1.id)
    assert len(list_shp) >= 1

    posted_shp = inv_service.post_shipment(shp.id, current_user_id=1)
    assert posted_shp.status == "posted"
    assert posted_shp.shipment_no.startswith("SHP-")
    assert posted_shp.total_cogs is not None
