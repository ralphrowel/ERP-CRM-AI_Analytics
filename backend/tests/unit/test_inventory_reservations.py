from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.clock import ControllableClock
from app.core.errors import BusinessRuleError, ConflictError
from app.modules.catalog.models import Product
from app.modules.crm.models import Customer
from app.modules.inventory.models import (
    InventoryBalance,
    StockReservation,
    Warehouse,
)
from app.modules.inventory.schemas import (
    OpeningBalanceItemPayload,
    OpeningBalancesCreatePayload,
    WarehouseCreatePayload,
)
from app.modules.inventory.service import InventoryService
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import LineItemPayload, SalesOrderCreatePayload
from app.modules.sales.service import SalesService


@pytest.fixture
def clock():
    return ControllableClock()


@pytest.fixture
def inv_service(db_session, clock):
    return InventoryService(db_session, clock)


@pytest.fixture
def sales_service(db_session, clock):
    return SalesService(db_session, clock)


@pytest.fixture
def default_warehouse(db_session):
    stmt = select(Warehouse).where(Warehouse.is_default.is_(True))
    wh = db_session.execute(stmt).scalar_one_or_none()
    if not wh:
        wh = Warehouse(
            code="WH-TEST-01",
            name="Test Central Warehouse",
            address="Test District, Manila",
            is_active=True,
            is_default=True,
        )
        db_session.add(wh)
        db_session.flush()
    return wh


@pytest.fixture
def default_tax_rate(db_session):
    stmt = select(TaxRate).where(TaxRate.code == "VAT12")
    tr = db_session.execute(stmt).scalar_one_or_none()
    if not tr:
        tr = TaxRate(
            code="VAT12",
            name="Value-Added Tax 12%",
            rate=Decimal("0.1200"),
            is_default=True,
            is_active=True,
        )
        db_session.add(tr)
        db_session.flush()
    return tr


@pytest.fixture
def sample_customer(db_session):
    stmt = select(Customer).where(Customer.customer_no == "CUS-INV-001")
    c = db_session.execute(stmt).scalar_one_or_none()
    if not c:
        c = Customer(
            customer_no="CUS-INV-001",
            name="Acme Logistics Corp",
            status="active",
            tin="123-456-789-000",
            payment_terms_days=30,
            credit_limit=Decimal("500000.00"),
        )
        db_session.add(c)
        db_session.flush()
    return c


@pytest.fixture
def sample_stock_product(db_session, default_tax_rate):
    stmt = select(Product).where(Product.sku == "SKU-WIDGET-01")
    p = db_session.execute(stmt).scalar_one_or_none()
    if not p:
        p = Product(
            sku="SKU-WIDGET-01",
            name="Industrial Widget A",
            product_type="stock",
            uom="pc",
            list_price=Decimal("150.0000"),
            reorder_point=Decimal("5.000"),
            tax_rate_id=default_tax_rate.id,
            is_active=True,
        )
        db_session.add(p)
        db_session.flush()
    return p


@pytest.fixture
def sample_service_product(db_session, default_tax_rate):
    stmt = select(Product).where(Product.sku == "SKU-SRV-INSTALL")
    p = db_session.execute(stmt).scalar_one_or_none()
    if not p:
        p = Product(
            sku="SKU-SRV-INSTALL",
            name="On-site Installation Service",
            product_type="service",
            uom="hr",
            list_price=Decimal("500.0000"),
            tax_rate_id=default_tax_rate.id,
            is_active=True,
        )
        db_session.add(p)
        db_session.flush()
    return p


def test_warehouse_creation_and_default_handling(inv_service, db_session):
    # Create warehouse 1
    wh1 = inv_service.create_warehouse(
        WarehouseCreatePayload(
            code="CEB-01",
            name="Cebu Regional Depot",
            address="Mandaue City, Cebu",
            is_default=False,
        )
    )
    assert wh1.code == "CEB-01"
    assert wh1.is_default is False

    # Duplicate code should fail
    with pytest.raises(ConflictError):
        inv_service.create_warehouse(
            WarehouseCreatePayload(
                code="ceb-01",
                name="Duplicate Cebu",
            )
        )


def test_opening_balances_posting_and_ledger(
    inv_service, db_session, default_warehouse, sample_stock_product, sample_service_product
):
    # Post opening balance of 20 units @ ₱80.00
    payload = OpeningBalancesCreatePayload(
        warehouse_id=default_warehouse.id,
        items=[
            OpeningBalanceItemPayload(
                product_id=sample_stock_product.id,
                quantity=Decimal("20.000"),
                unit_cost=Decimal("80.0000"),
            )
        ],
    )
    balances = inv_service.post_opening_balances(payload)
    assert len(balances) == 1
    bal_out = balances[0]
    assert bal_out.qty_on_hand == Decimal("20.000")
    assert bal_out.qty_reserved == Decimal("0.000")
    assert bal_out.qty_available == Decimal("20.000")
    assert bal_out.avg_unit_cost == Decimal("80.0000")
    assert bal_out.total_value == Decimal("1600.00")
    assert bal_out.is_below_reorder is False

    # Check ledger row
    txns = inv_service.list_inventory_transactions(
        warehouse_id=default_warehouse.id, product_id=sample_stock_product.id
    )
    assert len(txns) >= 1
    latest_txn = txns[0]
    assert latest_txn.txn_type == "opening"
    assert latest_txn.quantity == Decimal("20.000")
    assert latest_txn.unit_cost == Decimal("80.0000")
    assert latest_txn.qty_on_hand_after == Decimal("20.000")

    # Posting again when stock exists should raise ConflictError
    with pytest.raises(ConflictError):
        inv_service.post_opening_balances(payload)

    # Attempting to post opening balance for a service product should raise BusinessRuleError
    srv_payload = OpeningBalancesCreatePayload(
        warehouse_id=default_warehouse.id,
        items=[
            OpeningBalanceItemPayload(
                product_id=sample_service_product.id,
                quantity=Decimal("10.000"),
                unit_cost=Decimal("100.0000"),
            )
        ],
    )
    with pytest.raises(BusinessRuleError):
        inv_service.post_opening_balances(srv_payload)


def _get_or_create_stock_product(db_session, sku: str, name: str, tax_rate_id: int) -> Product:
    stmt = select(Product).where(Product.sku == sku)
    p = db_session.execute(stmt).scalar_one_or_none()
    if not p:
        p = Product(
            sku=sku,
            name=name,
            product_type="stock",
            uom="pc",
            list_price=Decimal("150.0000"),
            reorder_point=Decimal("5.000"),
            tax_rate_id=tax_rate_id,
            is_active=True,
        )
        db_session.add(p)
        db_session.flush()
    return p


def test_order_confirmation_reserves_stock_concurrency(
    inv_service,
    sales_service,
    db_session,
    default_warehouse,
    sample_customer,
    default_tax_rate,
):
    prod = _get_or_create_stock_product(
        db_session, "SKU-ORD-01", "Order Concurrency Widget", default_tax_rate.id
    )
    bal = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    if not bal:
        inv_service.post_opening_balances(
            OpeningBalancesCreatePayload(
                warehouse_id=default_warehouse.id,
                items=[
                    OpeningBalanceItemPayload(
                        product_id=prod.id,
                        quantity=Decimal("15.000"),
                        unit_cost=Decimal("75.0000"),
                    )
                ],
            )
        )

    # Create draft sales order for 6 units
    so_payload = SalesOrderCreatePayload(
        customer_id=sample_customer.id,
        warehouse_id=default_warehouse.id,
        items=[
            LineItemPayload(
                product_id=prod.id,
                description="Order Concurrency Widget",
                uom="pc",
                quantity=Decimal("6.000"),
                unit_price=Decimal("150.0000"),
            )
        ],
    )
    so = sales_service.create_sales_order(so_payload)
    assert so.status == "draft"

    # Confirm order -> triggers stock reservation
    so_confirmed = sales_service.confirm_sales_order(so.id)
    assert so_confirmed.status == "confirmed"

    # Verify inventory balance reserved qty
    db_session.expire_all()
    updated_bal = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    assert updated_bal.qty_on_hand == Decimal("15.000")
    assert updated_bal.qty_reserved == Decimal("6.000")
    assert updated_bal.qty_available == Decimal("9.000")

    # Verify reservation record
    res_stmt = select(StockReservation).where(
        StockReservation.product_id == prod.id,
        StockReservation.warehouse_id == default_warehouse.id,
        StockReservation.status == "active",
    )
    res = db_session.execute(res_stmt).scalar_one()
    assert res.quantity == Decimal("6.000")
    assert res.quantity_consumed == Decimal("0.000")


def test_insufficient_stock_rejection(
    inv_service,
    sales_service,
    db_session,
    default_warehouse,
    sample_customer,
    default_tax_rate,
):
    prod = _get_or_create_stock_product(
        db_session, "SKU-INSUFF-01", "Insufficient Stock Widget", default_tax_rate.id
    )
    bal = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    if not bal:
        inv_service.post_opening_balances(
            OpeningBalancesCreatePayload(
                warehouse_id=default_warehouse.id,
                items=[
                    OpeningBalanceItemPayload(
                        product_id=prod.id,
                        quantity=Decimal("4.000"),
                        unit_cost=Decimal("75.0000"),
                    )
                ],
            )
        )

    # Create draft order requesting 10 units (exceeds available 4)
    so_payload = SalesOrderCreatePayload(
        customer_id=sample_customer.id,
        warehouse_id=default_warehouse.id,
        items=[
            LineItemPayload(
                product_id=prod.id,
                description="Insufficient Stock Widget",
                uom="pc",
                quantity=Decimal("10.000"),
                unit_price=Decimal("150.0000"),
            )
        ],
    )
    so = sales_service.create_sales_order(so_payload)

    # Attempt to confirm: must fail with INSUFFICIENT_STOCK
    with pytest.raises(BusinessRuleError) as exc_info:
        sales_service.confirm_sales_order(so.id)
    assert exc_info.value.code == "INSUFFICIENT_STOCK"

    # Verify balance was NOT touched
    db_session.expire_all()
    bal_after = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    assert bal_after.qty_reserved == Decimal("0.000")
    assert bal_after.qty_available == Decimal("4.000")


def test_service_product_bypasses_reservation(
    sales_service,
    db_session,
    default_warehouse,
    sample_customer,
    sample_service_product,
):
    # Create order with only service items (which have no inventory balances)
    so_payload = SalesOrderCreatePayload(
        customer_id=sample_customer.id,
        warehouse_id=default_warehouse.id,
        items=[
            LineItemPayload(
                product_id=sample_service_product.id,
                description="On-site Installation Service",
                uom="hr",
                quantity=Decimal("8.000"),
                unit_price=Decimal("500.0000"),
            )
        ],
    )
    so = sales_service.create_sales_order(so_payload)
    so_confirmed = sales_service.confirm_sales_order(so.id)
    assert so_confirmed.status == "confirmed"


def test_cancel_order_releases_reservations(
    inv_service,
    sales_service,
    db_session,
    default_warehouse,
    sample_customer,
    default_tax_rate,
):
    prod = _get_or_create_stock_product(
        db_session, "SKU-CANCEL-01", "Cancellable Widget", default_tax_rate.id
    )
    bal = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    if not bal:
        inv_service.post_opening_balances(
            OpeningBalancesCreatePayload(
                warehouse_id=default_warehouse.id,
                items=[
                    OpeningBalanceItemPayload(
                        product_id=prod.id,
                        quantity=Decimal("20.000"),
                        unit_cost=Decimal("75.0000"),
                    )
                ],
            )
        )

    # Create and confirm order for 5 units
    so_payload = SalesOrderCreatePayload(
        customer_id=sample_customer.id,
        warehouse_id=default_warehouse.id,
        items=[
            LineItemPayload(
                product_id=prod.id,
                description="Cancellable Widget",
                uom="pc",
                quantity=Decimal("5.000"),
                unit_price=Decimal("150.0000"),
            )
        ],
    )
    so = sales_service.create_sales_order(so_payload)
    sales_service.confirm_sales_order(so.id)

    # Check reserved = 5
    db_session.expire_all()
    bal_mid = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    assert bal_mid.qty_reserved == Decimal("5.000")

    # Cancel sales order
    so_cancelled = sales_service.cancel_sales_order(so.id, reason="Customer cancelled project")
    assert so_cancelled.status == "cancelled"

    # Check reservation was released
    db_session.expire_all()
    bal_after = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    assert bal_after.qty_reserved == Decimal("0.000")
    assert bal_after.qty_available == Decimal("20.000")

    # Check reservation record status
    res = db_session.execute(
        select(StockReservation).where(StockReservation.sales_order_item_id == so.items[0].id)
    ).scalar_one()
    assert res.status == "released"
    assert res.released_at is not None


def test_reconciliation_integrity(inv_service, db_session, default_warehouse, default_tax_rate):
    prod = _get_or_create_stock_product(
        db_session, "SKU-RECON-01", "Reconciled Product", default_tax_rate.id
    )
    bal = db_session.get(InventoryBalance, (prod.id, default_warehouse.id))
    if not bal:
        inv_service.post_opening_balances(
            OpeningBalancesCreatePayload(
                warehouse_id=default_warehouse.id,
                items=[
                    OpeningBalanceItemPayload(
                        product_id=prod.id,
                        quantity=Decimal("25.000"),
                        unit_cost=Decimal("50.0000"),
                    )
                ],
            )
        )

    recon = inv_service.get_inventory_reconciliation()
    assert recon.discrepant_count == 0
    assert recon.total_items_checked >= 1
    for item in recon.items:
        assert item.is_reconciled is True
        assert item.qty_discrepancy == Decimal("0.000")
        assert item.cost_discrepancy == Decimal("0.0000")
