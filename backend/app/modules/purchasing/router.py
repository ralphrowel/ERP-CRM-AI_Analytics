from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.purchasing.schemas import (
    PurchaseOrderClosePayload,
    PurchaseOrderCreate,
    PurchaseOrderItemOut,
    PurchaseOrderListOut,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierListOut,
    SupplierOut,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierProductUpdate,
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
