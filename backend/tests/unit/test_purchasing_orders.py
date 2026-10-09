from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.core.errors import AppException, ConflictException
from app.core.numbering import DocumentSequence
from app.core.status_history import get_entity_history
from app.modules.catalog.models import Product, ProductCategory
from app.modules.identity.models import User
from app.modules.inventory.models import Warehouse
from app.modules.purchasing.schemas import (
    PurchaseOrderClosePayload,
    PurchaseOrderCreate,
    PurchaseOrderItemPayload,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierUpdate,
)
from app.modules.purchasing.service import PurchasingService
from app.modules.sales.models import TaxRate


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session: Session = session_factory()

    # Seed sequences
    seqs = [
        DocumentSequence(
            doc_type="supplier",
            prefix="SUP",
            include_year=False,
            padding=5,
            next_value=1,
        ),
        DocumentSequence(
            doc_type="purchase_order",
            prefix="PO",
            include_year=True,
            padding=6,
            next_value=1,
        ),
    ]
    session.add_all(seqs)

    # Seed tax rate
    tr12 = TaxRate(
        code="VAT12",
        name="VAT 12%",
        rate=Decimal("0.1200"),
        is_default=True,
        is_active=True,
    )
    session.add(tr12)

    # Seed test user
    user = User(
        email="purchasing@example.com",
        password_hash="fakehash",
        full_name="Purchasing Agent",
        is_active=True,
    )
    session.add(user)

    # Seed warehouse
    wh = Warehouse(
        code="WH-MNL",
        name="Manila Central Warehouse",
        address="100 Pier South, Manila",
        is_active=True,
        is_default=True,
    )
    session.add(wh)

    # Seed category and products
    cat = ProductCategory(name="Raw Materials", is_active=True)
    session.add(cat)
    session.flush()

    p1 = Product(
        sku="STEEL-01",
        name="Industrial Steel Bar",
        category_id=cat.id,
        tax_rate_id=tr12.id,
        product_type="stock",
        uom="pc",
        list_price=Decimal("1500.00"),
        is_active=True,
    )
    p2 = Product(
        sku="ALUM-01",
        name="Aluminum Sheet",
        category_id=cat.id,
        tax_rate_id=tr12.id,
        product_type="stock",
        uom="pc",
        list_price=Decimal("800.00"),
        is_active=True,
    )
    session.add_all([p1, p2])

    session.commit()
    yield session
    session.close()


def test_supplier_crud_and_sequence_numbering(test_db: Session):
    svc = PurchasingService(test_db)

    # 1. Create with auto-generated sequence number
    sup1 = svc.create_supplier(
        SupplierCreate(
            name="Apex Metal Supplies Corp",
            tin="123-456-789-000",
            email="sales@apexmetal.com",
            phone="+63 2 8123 4567",
            address="Valenzuela City, Metro Manila",
            payment_terms_days=30,
        )
    )
    assert sup1.id is not None
    assert sup1.supplier_no == "SUP-00001"
    assert sup1.name == "Apex Metal Supplies Corp"
    assert sup1.version == 1

    # 2. Second supplier increments sequence
    sup2 = svc.create_supplier(SupplierCreate(name="Global Fasteners Inc", payment_terms_days=45))
    assert sup2.supplier_no == "SUP-00002"

    # 3. Create with explicit supplier_no
    sup3 = svc.create_supplier(
        SupplierCreate(supplier_no="SUP-CUSTOM-99", name="Custom Supplier Ltd")
    )
    assert sup3.supplier_no == "SUP-CUSTOM-99"

    # 4. Duplicate supplier_no rejected
    with pytest.raises(AppException) as exc_info:
        svc.create_supplier(SupplierCreate(supplier_no="SUP-CUSTOM-99", name="Duplicate Supplier"))
    assert exc_info.value.code == "DUPLICATE_SUPPLIER_NO"

    # 5. Update supplier & optimistic lock
    updated = svc.update_supplier(
        sup1.id,
        SupplierUpdate(
            payment_terms_days=60,
            notes="Extended credit terms approved",
            version=1,
        ),
    )
    assert updated.payment_terms_days == 60
    assert updated.version == 2

    # Stale version fails with ConflictException
    with pytest.raises(ConflictException):
        svc.update_supplier(sup1.id, SupplierUpdate(payment_terms_days=90, version=1))


def test_supplier_products_catalog(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(SupplierCreate(name="Heavy Industries Co"))
    sup2 = svc.create_supplier(SupplierCreate(name="Alternate Metals Co"))

    prod1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    # 1. Add products to supplier catalog
    sp1 = svc.add_supplier_product(
        sup.id,
        SupplierProductCreate(
            product_id=prod1.id,
            supplier_sku="HIC-STL-100",
            last_unit_cost=Decimal("1200.00"),
            lead_time_days=7,
            is_preferred=True,
        ),
    )
    assert sp1.supplier_id == sup.id
    assert sp1.product_id == prod1.id
    assert sp1.is_preferred is True

    # 2. Adding same product to sup2 as preferred unsets sup's preferred flag
    sp2 = svc.add_supplier_product(
        sup2.id,
        SupplierProductCreate(
            product_id=prod1.id,
            supplier_sku="AMC-STL-BAR",
            last_unit_cost=Decimal("1150.00"),
            is_preferred=True,
        ),
    )
    assert sp2.is_preferred is True

    # Check sup1 is no longer preferred for prod1
    test_db.refresh(sp1)
    assert sp1.is_preferred is False

    # 3. Duplicate link to same supplier rejected
    with pytest.raises(AppException) as exc_info:
        svc.add_supplier_product(sup.id, SupplierProductCreate(product_id=prod1.id))
    assert exc_info.value.code == "PRODUCT_ALREADY_LINKED"

    # 4. Update supplier product
    updated_sp = svc.update_supplier_product(
        sup.id,
        prod1.id,
        SupplierProductUpdate(last_unit_cost=Decimal("1180.00"), is_preferred=True),
    )
    assert updated_sp.last_unit_cost == Decimal("1180.0000")
    assert updated_sp.is_preferred is True

    # 5. Remove supplier product
    svc.remove_supplier_product(sup.id, prod1.id)
    items = svc.list_supplier_products(sup.id)
    assert len(items) == 0


def test_purchase_order_creation_and_money_math(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(
        SupplierCreate(
            name="Manila Industrial Corp",
            address="Port Area, Manila",
            payment_terms_days=30,
        )
    )
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()
    p2 = test_db.query(Product).filter_by(sku="ALUM-01").one()

    # Create PO with 2 line items:
    # Line 1: 10 * 1,000 = 10,000 net; tax @ 12% = 1,200; total = 11,200
    # Line 2: 5 * 500 = 2,500 net; tax @ 12% = 300; total = 2,800
    # Subtotal = 12,500; Tax total = 1,500; Grand total = 14,000
    payload = PurchaseOrderCreate(
        supplier_id=sup.id,
        warehouse_id=wh.id,
        order_date=date(2026, 10, 15),
        expected_date=date(2026, 10, 22),
        notes="Urgent manufacturing restock",
        items=[
            PurchaseOrderItemPayload(
                product_id=p1.id,
                quantity=Decimal("10.000"),
                unit_cost=Decimal("1000.0000"),
                tax_rate_id=tr.id,
            ),
            PurchaseOrderItemPayload(
                product_id=p2.id,
                quantity=Decimal("5.000"),
                unit_cost=Decimal("500.0000"),
                tax_rate_id=tr.id,
            ),
        ],
    )
    po = svc.create_purchase_order(payload)

    assert po.id is not None
    assert po.po_no.startswith("PO-")
    assert po.status == "draft"
    assert po.payment_terms_days_snapshot == 30
    assert len(po.items) == 2

    # Verify line 1 math
    assert po.items[0].line_net == Decimal("10000.00")
    assert po.items[0].line_tax == Decimal("1200.00")
    assert po.items[0].line_total == Decimal("11200.00")

    # Verify line 2 math
    assert po.items[1].line_net == Decimal("2500.00")
    assert po.items[1].line_tax == Decimal("300.00")
    assert po.items[1].line_total == Decimal("2800.00")

    # Verify header totals
    assert po.subtotal == Decimal("12500.00")
    assert po.tax_total == Decimal("1500.00")
    assert po.grand_total == Decimal("14000.00")


def test_purchase_order_update_in_draft(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(SupplierCreate(name="Supplier Alpha"))
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    po = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("2.000"),
                    unit_cost=Decimal("1000.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    assert po.subtotal == Decimal("2000.00")
    assert po.version == 1

    # Update draft PO with new quantity
    updated = svc.update_purchase_order(
        po.id,
        PurchaseOrderUpdate(
            notes="Revised quantity requirement",
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("4.000"),
                    unit_cost=Decimal("1000.0000"),
                    tax_rate_id=tr.id,
                )
            ],
            version=1,
        ),
    )
    assert updated.subtotal == Decimal("4000.00")
    assert updated.version == 2
    assert updated.notes == "Revised quantity requirement"


def test_purchase_order_send_snapshots(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(
        SupplierCreate(
            name="Contractor Hub",
            address="123 Builder St, Taguig",
            payment_terms_days=45,
        )
    )
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    po = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("1.000"),
                    unit_cost=Decimal("500.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    assert po.status == "draft"
    assert po.supplier_address_snapshot is None

    # Send PO
    sent_po = svc.send_purchase_order(po.id)
    assert sent_po.status == "sent"
    assert sent_po.supplier_address_snapshot == "123 Builder St, Taguig"
    assert sent_po.warehouse_address_snapshot == "100 Pier South, Manila"
    assert sent_po.payment_terms_days_snapshot == 45

    # Modifying the supplier afterwards does not affect the PO snapshot
    svc.update_supplier(
        sup.id,
        SupplierUpdate(
            address="New HQ Address, Makati City",
            payment_terms_days=60,
            version=1,
        ),
    )
    test_db.refresh(sent_po)
    assert sent_po.supplier_address_snapshot == "123 Builder St, Taguig"
    assert sent_po.payment_terms_days_snapshot == 45

    # Sent PO cannot be edited
    with pytest.raises(AppException) as exc_info:
        svc.update_purchase_order(sent_po.id, PurchaseOrderUpdate(notes="Should fail", version=2))
    assert exc_info.value.code == "PO_NOT_EDITABLE"


def test_purchase_order_cancel_workflow(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(SupplierCreate(name="Cancelable Supplier"))
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    po = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("5.000"),
                    unit_cost=Decimal("100.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )

    # 1. Draft PO can be cancelled
    cancelled_po = svc.cancel_purchase_order(po.id, reason="Customer cancelled project")
    assert cancelled_po.status == "cancelled"

    # 2. Sent PO with 0 receipts can be cancelled
    po2 = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("5.000"),
                    unit_cost=Decimal("100.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    svc.send_purchase_order(po2.id)
    cancelled_po2 = svc.cancel_purchase_order(po2.id, reason="Supplier out of stock")
    assert cancelled_po2.status == "cancelled"

    # 3. If quantity has been received, cancellation is blocked
    po3 = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    svc.send_purchase_order(po3.id)
    # Simulate a partial receipt on line item
    po3.items[0].quantity_received = Decimal("3.000")
    test_db.commit()

    with pytest.raises(AppException) as exc_info:
        svc.cancel_purchase_order(po3.id, reason="Try to cancel received PO")
    assert exc_info.value.code == "PO_ALREADY_RECEIVED"


def test_purchase_order_short_close(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(SupplierCreate(name="Short Close Supplier"))
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    po = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    svc.send_purchase_order(po.id)

    # Attempting to short close a sent order is rejected (must be partially_received)
    with pytest.raises(AppException) as exc_info:
        svc.close_purchase_order(
            po.id, PurchaseOrderClosePayload(reason="Remaining items discontinued")
        )
    assert exc_info.value.code == "INVALID_STATUS_TRANSITION"

    # Simulate partially_received status
    po.status = "partially_received"
    po.items[0].quantity_received = Decimal("6.000")
    test_db.commit()

    closed_po = svc.close_purchase_order(
        po.id, PurchaseOrderClosePayload(reason="Supplier discontinued remaining 4 units")
    )
    assert closed_po.status == "closed"


def test_purchase_order_status_history_audit_trail(test_db: Session):
    svc = PurchasingService(test_db)
    sup = svc.create_supplier(SupplierCreate(name="Audit Test Supplier"))
    wh = test_db.query(Warehouse).first()
    tr = test_db.query(TaxRate).first()
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()

    po = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("1.000"),
                    unit_cost=Decimal("100.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    svc.send_purchase_order(po.id)
    svc.cancel_purchase_order(po.id, reason="Audited cancellation")

    history = get_entity_history(test_db, "purchase_order", po.id)
    assert len(history) == 3
    # Ordered descending by changed_at:
    assert history[0].to_status == "cancelled"
    assert history[0].reason == "Audited cancellation"
    assert history[1].to_status == "sent"
    assert history[2].to_status == "draft"
