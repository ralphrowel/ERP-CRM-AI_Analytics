from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.purchasing.schemas import (
    GoodsReceiptCreate,
    GoodsReceiptItemOut,
    GoodsReceiptListOut,
    GoodsReceiptOut,
    PurchaseOrderClosePayload,
    PurchaseOrderCreate,
    PurchaseOrderItemOut,
    PurchaseOrderListOut,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierInvoiceCreate,
    SupplierInvoiceItemOut,
    SupplierInvoiceListOut,
    SupplierInvoiceOut,
    SupplierListOut,
    SupplierOut,
    SupplierPaymentAllocationOut,
    SupplierPaymentCreate,
    SupplierPaymentListOut,
    SupplierPaymentOut,
    SupplierPaymentVoidPayload,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierProductUpdate,
    SupplierStatementOut,
    SupplierUpdate,
)
from app.modules.purchasing.service import PurchasingService

router = APIRouter(prefix="", tags=["Purchasing & Procurement"])


def get_purchasing_service(
    db: Annotated[Session, Depends(get_db)],
) -> PurchasingService:
    return PurchasingService(db)


# ── Suppliers ─────────────────────────────────────────────────────────
@router.get("/suppliers", response_model=SupplierListOut)
def list_suppliers(
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
):
    items, total = service.list_suppliers(
        page=page, page_size=page_size, is_active=is_active, search=search
    )
    supplier_outs = []
    for s in items:
        products_out = [
            SupplierProductOut(
                supplier_id=sp.supplier_id,
                product_id=sp.product_id,
                product_name=sp.product.name if sp.product else None,
                product_sku=sp.product.sku if sp.product else None,
                product_uom=sp.product.uom if sp.product else None,
                supplier_sku=sp.supplier_sku,
                last_unit_cost=sp.last_unit_cost,
                lead_time_days=sp.lead_time_days,
                is_preferred=sp.is_preferred,
            )
            for sp in s.products
        ]
        supplier_outs.append(
            SupplierOut(
                id=s.id,
                supplier_no=s.supplier_no,
                name=s.name,
                tin=s.tin,
                email=s.email,
                phone=s.phone,
                address=s.address,
                payment_terms_days=s.payment_terms_days,
                is_active=s.is_active,
                notes=s.notes,
                version=s.version,
                created_at=s.created_at,
                updated_at=s.updated_at,
                created_by=s.created_by,
                updated_by=s.updated_by,
                products=products_out,
            )
        )
    return SupplierListOut(items=supplier_outs, total=total, page=page, page_size=page_size)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    supplier = service.create_supplier(payload, user_id=current_user.id)
    return SupplierOut(
        id=supplier.id,
        supplier_no=supplier.supplier_no,
        name=supplier.name,
        tin=supplier.tin,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        payment_terms_days=supplier.payment_terms_days,
        is_active=supplier.is_active,
        notes=supplier.notes,
        version=supplier.version,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
        created_by=supplier.created_by,
        updated_by=supplier.updated_by,
        products=[],
    )


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    supplier = service.get_supplier(supplier_id)
    products_out = [
        SupplierProductOut(
            supplier_id=sp.supplier_id,
            product_id=sp.product_id,
            product_name=sp.product.name if sp.product else None,
            product_sku=sp.product.sku if sp.product else None,
            product_uom=sp.product.uom if sp.product else None,
            supplier_sku=sp.supplier_sku,
            last_unit_cost=sp.last_unit_cost,
            lead_time_days=sp.lead_time_days,
            is_preferred=sp.is_preferred,
        )
        for sp in supplier.products
    ]
    return SupplierOut(
        id=supplier.id,
        supplier_no=supplier.supplier_no,
        name=supplier.name,
        tin=supplier.tin,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        payment_terms_days=supplier.payment_terms_days,
        is_active=supplier.is_active,
        notes=supplier.notes,
        version=supplier.version,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
        created_by=supplier.created_by,
        updated_by=supplier.updated_by,
        products=products_out,
    )


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    supplier = service.update_supplier(supplier_id, payload, user_id=current_user.id)
    products_out = [
        SupplierProductOut(
            supplier_id=sp.supplier_id,
            product_id=sp.product_id,
            product_name=sp.product.name if sp.product else None,
            product_sku=sp.product.sku if sp.product else None,
            product_uom=sp.product.uom if sp.product else None,
            supplier_sku=sp.supplier_sku,
            last_unit_cost=sp.last_unit_cost,
            lead_time_days=sp.lead_time_days,
            is_preferred=sp.is_preferred,
        )
        for sp in supplier.products
    ]
    return SupplierOut(
        id=supplier.id,
        supplier_no=supplier.supplier_no,
        name=supplier.name,
        tin=supplier.tin,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        payment_terms_days=supplier.payment_terms_days,
        is_active=supplier.is_active,
        notes=supplier.notes,
        version=supplier.version,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
        created_by=supplier.created_by,
        updated_by=supplier.updated_by,
        products=products_out,
    )


# ── Supplier Products ─────────────────────────────────────────────────
@router.get(
    "/suppliers/{supplier_id}/products",
    response_model=list[SupplierProductOut],
)
def list_supplier_products(
    supplier_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    items = service.list_supplier_products(supplier_id)
    return [
        SupplierProductOut(
            supplier_id=sp.supplier_id,
            product_id=sp.product_id,
            product_name=sp.product.name if sp.product else None,
            product_sku=sp.product.sku if sp.product else None,
            product_uom=sp.product.uom if sp.product else None,
            supplier_sku=sp.supplier_sku,
            last_unit_cost=sp.last_unit_cost,
            lead_time_days=sp.lead_time_days,
            is_preferred=sp.is_preferred,
        )
        for sp in items
    ]


@router.post(
    "/suppliers/{supplier_id}/products",
    response_model=SupplierProductOut,
    status_code=status.HTTP_201_CREATED,
)
def add_supplier_product(
    supplier_id: int,
    payload: SupplierProductCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    sp = service.add_supplier_product(supplier_id, payload, user_id=current_user.id)
    return SupplierProductOut(
        supplier_id=sp.supplier_id,
        product_id=sp.product_id,
        product_name=sp.product.name if sp.product else None,
        product_sku=sp.product.sku if sp.product else None,
        product_uom=sp.product.uom if sp.product else None,
        supplier_sku=sp.supplier_sku,
        last_unit_cost=sp.last_unit_cost,
        lead_time_days=sp.lead_time_days,
        is_preferred=sp.is_preferred,
    )


@router.put(
    "/suppliers/{supplier_id}/products/{product_id}",
    response_model=SupplierProductOut,
)
def update_supplier_product(
    supplier_id: int,
    product_id: int,
    payload: SupplierProductUpdate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    sp = service.update_supplier_product(supplier_id, product_id, payload, user_id=current_user.id)
    return SupplierProductOut(
        supplier_id=sp.supplier_id,
        product_id=sp.product_id,
        product_name=sp.product.name if sp.product else None,
        product_sku=sp.product.sku if sp.product else None,
        product_uom=sp.product.uom if sp.product else None,
        supplier_sku=sp.supplier_sku,
        last_unit_cost=sp.last_unit_cost,
        lead_time_days=sp.lead_time_days,
        is_preferred=sp.is_preferred,
    )


@router.delete(
    "/suppliers/{supplier_id}/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_supplier_product(
    supplier_id: int,
    product_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    service.remove_supplier_product(supplier_id, product_id)


# ── Purchase Orders ───────────────────────────────────────────────────
def _map_po_to_out(po) -> PurchaseOrderOut:
    items_out = [
        PurchaseOrderItemOut(
            id=i.id,
            purchase_order_id=i.purchase_order_id,
            line_no=i.line_no,
            product_id=i.product_id,
            product_name=i.product.name if i.product else None,
            product_sku=i.product.sku if i.product else None,
            description=i.description,
            uom=i.uom,
            quantity=i.quantity,
            unit_cost=i.unit_cost,
            tax_rate_id=i.tax_rate_id,
            tax_rate=i.tax_rate,
            line_net=i.line_net,
            line_tax=i.line_tax,
            line_total=i.line_total,
            quantity_received=i.quantity_received,
            quantity_billed=i.quantity_billed,
        )
        for i in po.items
    ]
    return PurchaseOrderOut(
        id=po.id,
        po_no=po.po_no,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier.name if po.supplier else None,
        warehouse_id=po.warehouse_id,
        warehouse_code=po.warehouse.code if po.warehouse else None,
        warehouse_name=po.warehouse.name if po.warehouse else None,
        status=po.status,
        order_date=po.order_date,
        expected_date=po.expected_date,
        notes=po.notes,
        payment_terms_days_snapshot=po.payment_terms_days_snapshot,
        supplier_address_snapshot=po.supplier_address_snapshot,
        warehouse_address_snapshot=po.warehouse_address_snapshot,
        subtotal=po.subtotal,
        tax_total=po.tax_total,
        grand_total=po.grand_total,
        version=po.version,
        created_at=po.created_at,
        updated_at=po.updated_at,
        created_by=po.created_by,
        updated_by=po.updated_by,
        items=items_out,
    )


@router.get("/purchase-orders", response_model=PurchaseOrderListOut)
def list_purchase_orders(
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    supplier_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    status: str | None = Query(None),
):
    items, total = service.list_purchase_orders(
        page=page,
        page_size=page_size,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        status=status,
    )
    return PurchaseOrderListOut(
        items=[_map_po_to_out(po) for po in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    po = service.create_purchase_order(payload, user_id=current_user.id)
    return _map_po_to_out(po)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
def get_purchase_order(
    po_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    po = service.get_purchase_order(po_id)
    return _map_po_to_out(po)


@router.put("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
def update_purchase_order(
    po_id: int,
    payload: PurchaseOrderUpdate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    po = service.update_purchase_order(po_id, payload, user_id=current_user.id)
    return _map_po_to_out(po)


@router.post("/purchase-orders/{po_id}/send", response_model=PurchaseOrderOut)
def send_purchase_order(
    po_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    po = service.send_purchase_order(po_id, user_id=current_user.id)
    return _map_po_to_out(po)


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderOut)
def cancel_purchase_order(
    po_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    reason: str | None = Query(None),
):
    po = service.cancel_purchase_order(po_id, reason=reason, user_id=current_user.id)
    return _map_po_to_out(po)


@router.post("/purchase-orders/{po_id}/close", response_model=PurchaseOrderOut)
def close_purchase_order(
    po_id: int,
    payload: PurchaseOrderClosePayload,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    po = service.close_purchase_order(po_id, payload, user_id=current_user.id)
    return _map_po_to_out(po)


# ── Goods Receipts (Physical Receipts) ────────────────────────────────
def _map_gr_to_out(receipt) -> GoodsReceiptOut:
    return GoodsReceiptOut(
        id=receipt.id,
        gr_no=receipt.gr_no,
        purchase_order_id=receipt.purchase_order_id,
        po_no=receipt.purchase_order.po_no if receipt.purchase_order else None,
        warehouse_id=receipt.warehouse_id,
        warehouse_code=receipt.warehouse.code if receipt.warehouse else None,
        warehouse_name=receipt.warehouse.name if receipt.warehouse else None,
        status=receipt.status,
        received_at=receipt.received_at,
        supplier_delivery_ref=receipt.supplier_delivery_ref,
        notes=receipt.notes,
        version=receipt.version,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
        created_by=receipt.created_by,
        items=[
            GoodsReceiptItemOut(
                id=item.id,
                goods_receipt_id=item.goods_receipt_id,
                purchase_order_item_id=item.purchase_order_item_id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                product_sku=item.product.sku if item.product else None,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
            )
            for item in receipt.items
        ],
    )


@router.get("/goods-receipts", response_model=GoodsReceiptListOut)
def list_goods_receipts(
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    purchase_order_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    items, total = service.list_goods_receipts(
        purchase_order_id=purchase_order_id,
        warehouse_id=warehouse_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return GoodsReceiptListOut(
        items=[_map_gr_to_out(gr) for gr in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/goods-receipts", response_model=GoodsReceiptOut, status_code=status.HTTP_201_CREATED)
def create_goods_receipt(
    payload: GoodsReceiptCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    gr = service.create_goods_receipt(payload, current_user_id=current_user.id)
    return _map_gr_to_out(gr)


@router.get("/goods-receipts/{receipt_id}", response_model=GoodsReceiptOut)
def get_goods_receipt(
    receipt_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    gr = service.get_goods_receipt(receipt_id)
    return _map_gr_to_out(gr)


@router.post("/goods-receipts/{receipt_id}/post", response_model=GoodsReceiptOut)
def post_goods_receipt(
    receipt_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    gr = service.post_goods_receipt(receipt_id, current_user_id=current_user.id)
    return _map_gr_to_out(gr)


@router.post("/goods-receipts/{receipt_id}/cancel", response_model=GoodsReceiptOut)
def cancel_goods_receipt(
    receipt_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    gr = service.cancel_goods_receipt(receipt_id, current_user_id=current_user.id)
    return _map_gr_to_out(gr)


# ── Supplier Invoices (Bills & 3-Way Match) ───────────────────────────
def _map_bill_to_out(bill) -> SupplierInvoiceOut:
    return SupplierInvoiceOut(
        id=bill.id,
        bill_no=bill.bill_no,
        supplier_id=bill.supplier_id,
        supplier_name=bill.supplier.name if bill.supplier else None,
        purchase_order_id=bill.purchase_order_id,
        po_no=bill.purchase_order.po_no if bill.purchase_order else None,
        supplier_invoice_ref=bill.supplier_invoice_ref,
        status=bill.status,
        invoice_date=bill.invoice_date,
        due_date=bill.due_date,
        subtotal=bill.subtotal,
        tax_total=bill.tax_total,
        grand_total=bill.grand_total,
        amount_paid=bill.amount_paid,
        balance_due=bill.balance_due,
        match_notes=bill.match_notes,
        notes=bill.notes,
        version=bill.version,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
        items=[
            SupplierInvoiceItemOut(
                id=item.id,
                supplier_invoice_id=item.supplier_invoice_id,
                purchase_order_item_id=item.purchase_order_item_id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                product_sku=item.product.sku if item.product else None,
                line_no=item.line_no,
                description=item.description,
                uom=item.uom,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                tax_rate_id=item.tax_rate_id,
                tax_rate=item.tax_rate,
                line_net=item.line_net,
                line_tax=item.line_tax,
                line_total=item.line_total,
            )
            for item in bill.items
        ],
    )


@router.get("/supplier-invoices", response_model=SupplierInvoiceListOut)
def list_supplier_invoices(
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    supplier_id: int | None = Query(None),
    purchase_order_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    items, total = service.list_supplier_invoices(
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return SupplierInvoiceListOut(
        items=[_map_bill_to_out(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/supplier-invoices",
    response_model=SupplierInvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_invoice(
    payload: SupplierInvoiceCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    bill = service.create_supplier_invoice(payload, current_user_id=current_user.id)
    return _map_bill_to_out(bill)


@router.get("/supplier-invoices/{invoice_id}", response_model=SupplierInvoiceOut)
def get_supplier_invoice(
    invoice_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    bill = service.get_supplier_invoice(invoice_id)
    return _map_bill_to_out(bill)


@router.post("/supplier-invoices/{invoice_id}/approve", response_model=SupplierInvoiceOut)
def approve_supplier_invoice(
    invoice_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    bill = service.approve_supplier_invoice(invoice_id, current_user_id=current_user.id)
    return _map_bill_to_out(bill)


@router.post("/supplier-invoices/{invoice_id}/void", response_model=SupplierInvoiceOut)
def void_supplier_invoice(
    invoice_id: int,
    payload: SupplierPaymentVoidPayload,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    bill = service.void_supplier_invoice(
        invoice_id, reason=payload.reason, current_user_id=current_user.id
    )
    return _map_bill_to_out(bill)


# ── Accounts Payable (Supplier Payments & Allocations) ──────────────
def _map_payment_to_out(payment) -> SupplierPaymentOut:
    return SupplierPaymentOut(
        id=payment.id,
        payment_no=payment.payment_no,
        supplier_id=payment.supplier_id,
        supplier_name=payment.supplier.name if payment.supplier else None,
        payment_date=payment.payment_date,
        payment_method=payment.payment_method,
        reference_no=payment.reference_no,
        amount=payment.amount,
        amount_allocated=payment.amount_allocated,
        status=payment.status,
        void_reason=payment.void_reason,
        voided_at=payment.voided_at,
        notes=payment.notes,
        version=payment.version,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        allocations=[
            SupplierPaymentAllocationOut(
                id=alloc.id,
                supplier_payment_id=alloc.supplier_payment_id,
                supplier_invoice_id=alloc.supplier_invoice_id,
                bill_no=alloc.invoice.bill_no if alloc.invoice else None,
                supplier_invoice_ref=alloc.invoice.supplier_invoice_ref if alloc.invoice else None,
                amount=alloc.amount,
                allocated_at=alloc.allocated_at,
            )
            for alloc in payment.allocations
        ],
    )


@router.get("/supplier-payments", response_model=SupplierPaymentListOut)
def list_supplier_payments(
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    supplier_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    items, total = service.list_supplier_payments(
        supplier_id=supplier_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return SupplierPaymentListOut(
        items=[_map_payment_to_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/supplier-payments",
    response_model=SupplierPaymentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_payment(
    payload: SupplierPaymentCreate,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    payment = service.create_supplier_payment(payload, current_user_id=current_user.id)
    return _map_payment_to_out(payment)


@router.get("/supplier-payments/{payment_id}", response_model=SupplierPaymentOut)
def get_supplier_payment(
    payment_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    payment = service.get_supplier_payment(payment_id)
    return _map_payment_to_out(payment)


@router.post("/supplier-payments/{payment_id}/void", response_model=SupplierPaymentOut)
def void_supplier_payment(
    payment_id: int,
    payload: SupplierPaymentVoidPayload,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    payment = service.void_supplier_payment(
        payment_id, reason=payload.reason, current_user_id=current_user.id
    )
    return _map_payment_to_out(payment)


# ── Supplier Statement ────────────────────────────────────────────────
@router.get("/suppliers/{supplier_id}/statement", response_model=SupplierStatementOut)
def get_supplier_statement(
    supplier_id: int,
    service: Annotated[PurchasingService, Depends(get_purchasing_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return service.get_supplier_statement(supplier_id)
