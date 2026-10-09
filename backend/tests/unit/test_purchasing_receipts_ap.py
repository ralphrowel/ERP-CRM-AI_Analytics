from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.errors import AppException, ConflictException
from app.core.numbering import DocumentSequence
from app.modules.catalog.models import Product, ProductCategory
from app.modules.inventory.models import InventoryBalance, InventoryTransaction, Warehouse
from app.modules.organization.models import CompanySettings
from app.modules.purchasing.schemas import (
    GoodsReceiptCreate,
    GoodsReceiptItemPayload,
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


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session: Session = TestingSessionLocal()

    # Seed Document Sequences
    sequences = [
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
    ]
    session.add_all(sequences)

    # Seed Company Settings
    settings = CompanySettings(
        id=1,
        legal_name="Acme Enterprise Corp",
        currency_code="PHP",
        bill_price_tolerance_pct=Decimal("0.0500"),  # 5% tolerance
    )
    session.add(settings)

    # Seed Tax Rates
    tr12 = TaxRate(
        code="VAT12",
        name="12% Standard VAT",
        rate=Decimal("0.1200"),
        is_default=True,
        is_active=True,
    )
    session.add(tr12)
    session.flush()

    # Seed Warehouse
    wh = Warehouse(
        code="WH-MNL",
        name="Manila Central Warehouse",
        address="100 Pier South, Manila",
        is_active=True,
        is_default=True,
    )
    session.add(wh)

    # Seed Category & Products
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


def test_goods_receipt_partial_and_full_delivery(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).filter_by(sku="STEEL-01").one()
    p2 = test_db.query(Product).filter_by(sku="ALUM-01").one()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    # Create supplier & PO
    sup = svc.create_supplier(SupplierCreate(name="Steel Corp", payment_terms_days=30))
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
                ),
                PurchaseOrderItemPayload(
                    product_id=p2.id,
                    quantity=Decimal("5.000"),
                    unit_cost=Decimal("200.0000"),
                    tax_rate_id=tr.id,
                ),
            ],
        )
    )
    svc.send_purchase_order(po.id)

    # Partial Receipt #1: 6 Steel Bars
    po_item_1 = po.items[0]
    gr1 = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po_item_1.id, quantity=Decimal("6.000")
                )
            ],
        )
    )
    assert gr1.status == "draft"
    assert gr1.gr_no.startswith("GR-")

    # Post GR1
    posted_gr1 = svc.post_goods_receipt(gr1.id)
    assert posted_gr1.status == "posted"

    # Check PO status -> partially_received
    reloaded_po = svc.get_purchase_order(po.id)
    assert reloaded_po.status == "partially_received"
    assert reloaded_po.items[0].quantity_received == Decimal("6.000")
    assert reloaded_po.items[1].quantity_received == Decimal("0.000")

    # Check Inventory balance & ledger
    bal1 = test_db.query(InventoryBalance).filter_by(product_id=p1.id, warehouse_id=wh.id).one()
    assert bal1.qty_on_hand == Decimal("6.000")
    assert bal1.avg_unit_cost == Decimal("100.0000")

    txn1 = (
        test_db.query(InventoryTransaction)
        .filter_by(source_type="goods_receipt", source_id=gr1.id)
        .one()
    )
    assert txn1.txn_type == "receipt"
    assert txn1.quantity == Decimal("6.000")
    assert txn1.unit_cost == Decimal("100.0000")

    # Partial Receipt #2: Remaining 4 Steel Bars and all 5 Aluminum Sheets
    po_item_2 = po.items[1]
    gr2 = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po_item_1.id, quantity=Decimal("4.000")
                ),
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po_item_2.id, quantity=Decimal("5.000")
                ),
            ],
        )
    )
    svc.post_goods_receipt(gr2.id)

    # PO should now be received
    reloaded_po2 = svc.get_purchase_order(po.id)
    assert reloaded_po2.status == "received"
    assert reloaded_po2.items[0].quantity_received == Decimal("10.000")
    assert reloaded_po2.items[1].quantity_received == Decimal("5.000")

    bal2 = test_db.query(InventoryBalance).filter_by(product_id=p2.id, warehouse_id=wh.id).one()
    assert bal2.qty_on_hand == Decimal("5.000")
    assert bal2.avg_unit_cost == Decimal("200.0000")


def test_goods_receipt_over_receipt_rejection(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Over-Receipt Test"))
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
    svc.send_purchase_order(po.id)

    # Attempt to receive 6 when only 5 ordered
    with pytest.raises(AppException) as exc:
        svc.create_goods_receipt(
            GoodsReceiptCreate(
                purchase_order_id=po.id,
                items=[
                    GoodsReceiptItemPayload(
                        purchase_order_item_id=po.items[0].id, quantity=Decimal("6.000")
                    )
                ],
            )
        )
    assert exc.value.code == "OVER_RECEIPT"


def test_wac_recalculation_after_multiple_receipts(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="WAC Supplier"))

    # PO 1: 10 units at 100
    po1 = svc.create_purchase_order(
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
    svc.send_purchase_order(po1.id)
    gr1 = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po1.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po1.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr1.id)

    bal = test_db.query(InventoryBalance).filter_by(product_id=p1.id, warehouse_id=wh.id).one()
    assert bal.qty_on_hand == Decimal("10.000")
    assert bal.avg_unit_cost == Decimal("100.0000")

    # PO 2: 10 units at 150
    po2 = svc.create_purchase_order(
        PurchaseOrderCreate(
            supplier_id=sup.id,
            warehouse_id=wh.id,
            items=[
                PurchaseOrderItemPayload(
                    product_id=p1.id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("150.0000"),
                    tax_rate_id=tr.id,
                )
            ],
        )
    )
    svc.send_purchase_order(po2.id)
    gr2 = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po2.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po2.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr2.id)

    # New WAC = (10 * 100 + 10 * 150) / 20 = 2500 / 20 = 125.0000
    test_db.refresh(bal)
    assert bal.qty_on_hand == Decimal("20.000")
    assert bal.avg_unit_cost == Decimal("125.0000")


def test_supplier_invoice_3_way_match_pass_and_approval(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Matched Supplier"))
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

    # Receive 10 units
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    # Create bill for 10 units at 100.00 (exact match)
    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="INV-SUP-901",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )
    assert bill.status == "matched"
    assert "3-way match passed" in bill.match_notes
    assert bill.grand_total == Decimal("1120.00")  # 1000 + 12% VAT
    assert bill.balance_due == Decimal("1120.00")

    # Approve bill
    approved_bill = svc.approve_supplier_invoice(bill.id)
    assert approved_bill.status == "approved"

    # PO item quantity_billed should be updated
    test_db.refresh(po.items[0])
    assert po.items[0].quantity_billed == Decimal("10.000")


def test_supplier_invoice_3_way_match_quantity_exception(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Qty Mismatch Supplier"))
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

    # Receive only 4 units
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("4.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    # Bill tries to bill 6 units (exceeds 4 received)
    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="INV-QTY-FAIL",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("6.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )
    assert bill.status == "exception"
    assert "exceeds received qty" in bill.match_notes


def test_supplier_invoice_3_way_match_price_tolerance_exception(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Price Mismatch Supplier"))
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

    # Receive 10 units
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    # Bill at 120.00 (20% higher, while tolerance is 5%)
    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="INV-PRICE-FAIL",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("120.0000"),
                )
            ],
        )
    )
    assert bill.status == "exception"
    assert "differs from PO cost" in bill.match_notes

    # Manual override allows approving exception bill
    approved = svc.approve_supplier_invoice(bill.id)
    assert approved.status == "approved"


def test_duplicate_supplier_invoice_ref_rejected(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Duplicate Ref Supplier"))
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

    svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="SAME-REF-001",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("5.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )

    with pytest.raises(ConflictException):
        svc.create_supplier_invoice(
            SupplierInvoiceCreate(
                purchase_order_id=po.id,
                supplier_invoice_ref="SAME-REF-001",
                items=[
                    SupplierInvoiceItemPayload(
                        purchase_order_item_id=po.items[0].id,
                        quantity=Decimal("5.000"),
                        unit_cost=Decimal("100.0000"),
                    )
                ],
            )
        )


def test_supplier_payment_allocations_and_bill_settlement(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="AP Settlement Supplier"))
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
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    # Bill grand_total = 1120.00
    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="BILL-AP-001",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )
    svc.approve_supplier_invoice(bill.id)

    # 1. Partial Payment of 500.00
    pay1 = svc.create_supplier_payment(
        SupplierPaymentCreate(
            supplier_id=sup.id,
            amount=Decimal("500.00"),
            payment_method="bank_transfer",
            allocations=[
                SupplierPaymentAllocationItem(supplier_invoice_id=bill.id, amount=Decimal("500.00"))
            ],
        )
    )
    assert pay1.status == "posted"
    assert pay1.amount_allocated == Decimal("500.00")

    test_db.refresh(bill)
    assert bill.status == "partially_paid"
    assert bill.amount_paid == Decimal("500.00")
    assert bill.balance_due == Decimal("620.00")

    # 2. Final Payment settling remainder of 620.00
    pay2 = svc.create_supplier_payment(
        SupplierPaymentCreate(
            supplier_id=sup.id,
            amount=Decimal("620.00"),
            payment_method="check",
            allocations=[
                SupplierPaymentAllocationItem(supplier_invoice_id=bill.id, amount=Decimal("620.00"))
            ],
        )
    )
    assert pay2.status == "posted"

    test_db.refresh(bill)
    assert bill.status == "paid"
    assert bill.amount_paid == Decimal("1120.00")
    assert bill.balance_due == Decimal("0.00")


def test_void_supplier_payment_restores_bill_balance(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Void Payment Supplier"))
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
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="BILL-VOID-01",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )
    svc.approve_supplier_invoice(bill.id)

    # Pay full bill
    pay = svc.create_supplier_payment(
        SupplierPaymentCreate(
            supplier_id=sup.id,
            amount=Decimal("1120.00"),
            allocations=[
                SupplierPaymentAllocationItem(
                    supplier_invoice_id=bill.id, amount=Decimal("1120.00")
                )
            ],
        )
    )
    test_db.refresh(bill)
    assert bill.status == "paid"

    # Void payment
    voided_pay = svc.void_supplier_payment(pay.id, reason="Check bounced at clearing")
    assert voided_pay.status == "void"
    assert voided_pay.void_reason == "Check bounced at clearing"

    # Bill balance & status restored to approved
    test_db.refresh(bill)
    assert bill.status == "approved"
    assert bill.amount_paid == Decimal("0.00")
    assert bill.balance_due == Decimal("1120.00")


def test_supplier_statement_reconciliation(test_db: Session):
    svc = PurchasingService(test_db)
    p1 = test_db.query(Product).first()
    tr = test_db.query(TaxRate).first()
    wh = test_db.query(Warehouse).first()

    sup = svc.create_supplier(SupplierCreate(name="Statement Supplier"))
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
    gr = svc.create_goods_receipt(
        GoodsReceiptCreate(
            purchase_order_id=po.id,
            items=[
                GoodsReceiptItemPayload(
                    purchase_order_item_id=po.items[0].id, quantity=Decimal("10.000")
                )
            ],
        )
    )
    svc.post_goods_receipt(gr.id)

    # Bill 1120.00
    bill = svc.create_supplier_invoice(
        SupplierInvoiceCreate(
            purchase_order_id=po.id,
            supplier_invoice_ref="STMT-BILL-01",
            items=[
                SupplierInvoiceItemPayload(
                    purchase_order_item_id=po.items[0].id,
                    quantity=Decimal("10.000"),
                    unit_cost=Decimal("100.0000"),
                )
            ],
        )
    )
    svc.approve_supplier_invoice(bill.id)

    # Payment of 500.00
    svc.create_supplier_payment(
        SupplierPaymentCreate(
            supplier_id=sup.id,
            amount=Decimal("500.00"),
            allocations=[
                SupplierPaymentAllocationItem(supplier_invoice_id=bill.id, amount=Decimal("500.00"))
            ],
        )
    )

    stmt = svc.get_supplier_statement(sup.id)
    assert stmt.supplier_id == sup.id
    assert len(stmt.bills) == 1
    assert len(stmt.payments) == 1
    assert stmt.total_billed == Decimal("1120.00")
    assert stmt.total_paid == Decimal("500.00")
    assert stmt.total_outstanding == Decimal("620.00")
