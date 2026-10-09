from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import get_clock
from app.core.errors import AppException, ConflictException, NotFoundException
from app.core.money import round_money
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.catalog.models import Product
from app.modules.inventory.models import Warehouse
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierProduct,
)
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
from app.modules.sales.models import TaxRate


class PurchasingService:
    def __init__(self, db: Session):
        self.db = db

    # ── Suppliers ────────────────────────────────────────────────────────
    def list_suppliers(
        self,
        page: int = 1,
        page_size: int = 50,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[Supplier], int]:
        stmt = select(Supplier).options(
            selectinload(Supplier.products).selectinload(SupplierProduct.product)
        )
        count_stmt = select(func.count(Supplier.id))

        if is_active is not None:
            stmt = stmt.where(Supplier.is_active == is_active)
            count_stmt = count_stmt.where(Supplier.is_active == is_active)

        if search:
            pattern = f"%{search.strip()}%"
            filter_expr = or_(
                Supplier.name.ilike(pattern),
                Supplier.supplier_no.ilike(pattern),
                Supplier.email.ilike(pattern),
            )
            stmt = stmt.where(filter_expr)
            count_stmt = count_stmt.where(filter_expr)

        total = self.db.execute(count_stmt).scalar() or 0
        items = (
            self.db.execute(
                stmt.order_by(Supplier.name.asc()).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(items), total

    def get_supplier(self, supplier_id: int) -> Supplier:
        supplier = self.db.execute(
            select(Supplier)
            .options(selectinload(Supplier.products).selectinload(SupplierProduct.product))
            .where(Supplier.id == supplier_id)
        ).scalar_one_or_none()
        if not supplier:
            raise NotFoundException(f"Supplier #{supplier_id} not found.")
        return supplier

    def create_supplier(self, payload: SupplierCreate, user_id: int | None = None) -> Supplier:
        supplier_no = payload.supplier_no
        if not supplier_no:
            supplier_no = generate_next_number(self.db, "supplier")

        # Check unique supplier_no
        existing = self.db.execute(
            select(Supplier).where(Supplier.supplier_no == supplier_no)
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="DUPLICATE_SUPPLIER_NO",
                detail=f"Supplier number {supplier_no} already exists.",
            )

        supplier = Supplier(
            supplier_no=supplier_no,
            name=payload.name,
            tin=payload.tin,
            email=payload.email,
            phone=payload.phone,
            address=payload.address,
            payment_terms_days=payload.payment_terms_days,
            is_active=payload.is_active,
            notes=payload.notes,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return self.get_supplier(supplier.id)

    def update_supplier(
        self, supplier_id: int, payload: SupplierUpdate, user_id: int | None = None
    ) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        if supplier.version != payload.version:
            raise ConflictException("Supplier was modified concurrently. Please reload.")

        if payload.name is not None:
            supplier.name = payload.name
        if payload.tin is not None:
            supplier.tin = payload.tin
        if payload.email is not None:
            supplier.email = payload.email
        if payload.phone is not None:
            supplier.phone = payload.phone
        if payload.address is not None:
            supplier.address = payload.address
        if payload.payment_terms_days is not None:
            supplier.payment_terms_days = payload.payment_terms_days
        if payload.is_active is not None:
            supplier.is_active = payload.is_active
        if payload.notes is not None:
            supplier.notes = payload.notes

        supplier.version += 1
        supplier.updated_by = user_id
        self.db.commit()
        self.db.refresh(supplier)
        return self.get_supplier(supplier.id)

    # ── Supplier Products ─────────────────────────────────────────────────
    def list_supplier_products(self, supplier_id: int) -> list[SupplierProduct]:
        # verify supplier exists
        self.get_supplier(supplier_id)
        stmt = (
            select(SupplierProduct)
            .options(selectinload(SupplierProduct.product))
            .where(SupplierProduct.supplier_id == supplier_id)
            .order_by(SupplierProduct.is_preferred.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def add_supplier_product(
        self,
        supplier_id: int,
        payload: SupplierProductCreate,
        user_id: int | None = None,
    ) -> SupplierProduct:
        self.get_supplier(supplier_id)
        product = self.db.execute(
            select(Product).where(Product.id == payload.product_id)
        ).scalar_one_or_none()
        if not product:
            raise NotFoundException(f"Product #{payload.product_id} not found.")

        existing = self.db.execute(
            select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == payload.product_id,
            )
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="PRODUCT_ALREADY_LINKED",
                detail="Product is already linked to this supplier.",
            )

        if payload.is_preferred:
            # Unset preferred flag on other suppliers for this product
            self.db.execute(
                select(SupplierProduct).where(SupplierProduct.product_id == payload.product_id)
            )
            # update other supplier products
            other_sps = (
                self.db.execute(
                    select(SupplierProduct).where(
                        SupplierProduct.product_id == payload.product_id,
                        SupplierProduct.is_preferred.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            for other in other_sps:
                other.is_preferred = False

        sp = SupplierProduct(
            supplier_id=supplier_id,
            product_id=payload.product_id,
            supplier_sku=payload.supplier_sku,
            last_unit_cost=payload.last_unit_cost,
            lead_time_days=payload.lead_time_days,
            is_preferred=payload.is_preferred,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(sp)
        self.db.commit()
        return (
            self.db.execute(
                select(SupplierProduct)
                .options(selectinload(SupplierProduct.product))
                .where(
                    SupplierProduct.supplier_id == supplier_id,
                    SupplierProduct.product_id == payload.product_id,
                )
            )
            .scalars()
            .one()
        )

    def update_supplier_product(
        self,
        supplier_id: int,
        product_id: int,
        payload: SupplierProductUpdate,
        user_id: int | None = None,
    ) -> SupplierProduct:
        sp = self.db.execute(
            select(SupplierProduct)
            .options(selectinload(SupplierProduct.product))
            .where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == product_id,
            )
        ).scalar_one_or_none()
        if not sp:
            raise NotFoundException("Supplier product relationship not found.")

        if payload.supplier_sku is not None:
            sp.supplier_sku = payload.supplier_sku
        if payload.last_unit_cost is not None:
            sp.last_unit_cost = payload.last_unit_cost
        if payload.lead_time_days is not None:
            sp.lead_time_days = payload.lead_time_days
        if payload.is_preferred is not None:
            if payload.is_preferred:
                # Unset preferred flag on others
                other_sps = (
                    self.db.execute(
                        select(SupplierProduct).where(
                            SupplierProduct.product_id == product_id,
                            SupplierProduct.supplier_id != supplier_id,
                            SupplierProduct.is_preferred.is_(True),
                        )
                    )
                    .scalars()
                    .all()
                )
                for other in other_sps:
                    other.is_preferred = False
            sp.is_preferred = payload.is_preferred

        sp.updated_by = user_id
        self.db.commit()
        self.db.refresh(sp)
        return sp

    def remove_supplier_product(self, supplier_id: int, product_id: int) -> None:
        sp = self.db.execute(
            select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id,
                SupplierProduct.product_id == product_id,
            )
        ).scalar_one_or_none()
        if not sp:
            raise NotFoundException("Supplier product relationship not found.")
        self.db.delete(sp)
        self.db.commit()

    # ── Purchase Orders ───────────────────────────────────────────────────
    def list_purchase_orders(
        self,
        page: int = 1,
        page_size: int = 50,
        supplier_id: int | None = None,
        warehouse_id: int | None = None,
        status: str | None = None,
    ) -> tuple[list[PurchaseOrder], int]:
        stmt = select(PurchaseOrder).options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.warehouse),
            selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.product),
            selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.tax_rate_rel),
        )
        count_stmt = select(func.count(PurchaseOrder.id))

        if supplier_id:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
            count_stmt = count_stmt.where(PurchaseOrder.supplier_id == supplier_id)
        if warehouse_id:
            stmt = stmt.where(PurchaseOrder.warehouse_id == warehouse_id)
            count_stmt = count_stmt.where(PurchaseOrder.warehouse_id == warehouse_id)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
            count_stmt = count_stmt.where(PurchaseOrder.status == status)

        total = self.db.execute(count_stmt).scalar() or 0
        items = (
            self.db.execute(
                stmt.order_by(PurchaseOrder.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(items), total

    def get_purchase_order(self, po_id: int) -> PurchaseOrder:
        po = self.db.execute(
            select(PurchaseOrder)
            .options(
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.warehouse),
                selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.product),
                selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.tax_rate_rel),
            )
            .where(PurchaseOrder.id == po_id)
        ).scalar_one_or_none()
        if not po:
            raise NotFoundException(f"Purchase order #{po_id} not found.")
        return po

    def create_purchase_order(
        self, payload: PurchaseOrderCreate, user_id: int | None = None
    ) -> PurchaseOrder:
        supplier = self.get_supplier(payload.supplier_id)
        if not supplier.is_active:
            raise AppException(
                status_code=400,
                code="INACTIVE_SUPPLIER",
                detail="Cannot create purchase order for an inactive supplier.",
            )

        warehouse = self.db.execute(
            select(Warehouse).where(Warehouse.id == payload.warehouse_id)
        ).scalar_one_or_none()
        if not warehouse or not warehouse.is_active:
            raise AppException(
                status_code=400,
                code="INVALID_WAREHOUSE",
                detail="Target fulfillment warehouse not found or is inactive.",
            )

        po_no = generate_next_number(self.db, "purchase_order")
        order_date = payload.order_date or get_clock().now().date()

        po = PurchaseOrder(
            po_no=po_no,
            supplier_id=supplier.id,
            warehouse_id=warehouse.id,
            status="draft",
            order_date=order_date,
            expected_date=payload.expected_date,
            notes=payload.notes,
            payment_terms_days_snapshot=supplier.payment_terms_days,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(po)
        self.db.flush()

        self._build_po_items(po, payload.items)
        self.db.commit()

        record_status_change(
            db=self.db,
            entity_type="purchase_order",
            entity_id=po.id,
            to_status="draft",
            changed_by=user_id,
        )
        self.db.commit()

        return self.get_purchase_order(po.id)

    def update_purchase_order(
        self, po_id: int, payload: PurchaseOrderUpdate, user_id: int | None = None
    ) -> PurchaseOrder:
        po = self.get_purchase_order(po_id)
        if po.status != "draft":
            raise AppException(
                status_code=400,
                code="PO_NOT_EDITABLE",
                detail=f"Only draft purchase orders can be edited (current: {po.status}).",
            )
        if po.version != payload.version:
            raise ConflictException("Purchase order was modified concurrently. Please reload.")

        if payload.warehouse_id is not None:
            wh = self.db.execute(
                select(Warehouse).where(Warehouse.id == payload.warehouse_id)
            ).scalar_one_or_none()
            if not wh or not wh.is_active:
                raise AppException(
                    status_code=400,
                    code="INVALID_WAREHOUSE",
                    detail="Warehouse not found or inactive.",
                )
            po.warehouse_id = wh.id

        if payload.order_date is not None:
            po.order_date = payload.order_date
        if payload.expected_date is not None:
            po.expected_date = payload.expected_date
        if payload.notes is not None:
            po.notes = payload.notes

        if payload.items is not None:
            # Delete existing items and rebuild
            for item in list(po.items):
                self.db.delete(item)
            self.db.flush()
            self._build_po_items(po, payload.items)

        po.version += 1
        po.updated_by = user_id
        self.db.commit()
        return self.get_purchase_order(po.id)

    def send_purchase_order(self, po_id: int, user_id: int | None = None) -> PurchaseOrder:
        po = self.get_purchase_order(po_id)
        if po.status != "draft":
            raise AppException(
                status_code=400,
                code="INVALID_STATUS_TRANSITION",
                detail=f"Cannot send purchase order in status '{po.status}' (must be draft).",
            )

        # Snapshot address and terms
        po.supplier_address_snapshot = po.supplier.address
        po.warehouse_address_snapshot = po.warehouse.address
        po.payment_terms_days_snapshot = po.supplier.payment_terms_days

        from_status = po.status
        po.status = "sent"
        po.version += 1
        po.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="purchase_order",
            entity_id=po.id,
            from_status=from_status,
            to_status="sent",
            reason="Sent purchase order to supplier",
            changed_by=user_id,
        )
        self.db.commit()
        return self.get_purchase_order(po.id)

    def cancel_purchase_order(
        self, po_id: int, reason: str | None = None, user_id: int | None = None
    ) -> PurchaseOrder:
        po = self.get_purchase_order(po_id)
        if po.status not in ("draft", "sent"):
            raise AppException(
                status_code=400,
                code="INVALID_STATUS_TRANSITION",
                detail=f"Cannot cancel purchase order in status '{po.status}'.",
            )

        # Roadmap rule: cancel only if zero items have been received
        any_received = any(Decimal(str(item.quantity_received)) > Decimal("0") for item in po.items)
        if any_received:
            raise AppException(
                status_code=400,
                code="PO_ALREADY_RECEIVED",
                detail="Cannot cancel purchase order after goods have been received.",
            )

        from_status = po.status
        po.status = "cancelled"
        po.version += 1
        po.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="purchase_order",
            entity_id=po.id,
            from_status=from_status,
            to_status="cancelled",
            reason=reason or "Cancelled by user",
            changed_by=user_id,
        )
        self.db.commit()
        return self.get_purchase_order(po.id)

    def close_purchase_order(
        self, po_id: int, payload: PurchaseOrderClosePayload, user_id: int | None = None
    ) -> PurchaseOrder:
        po = self.get_purchase_order(po_id)
        if po.status != "partially_received":
            raise AppException(
                status_code=400,
                code="INVALID_STATUS_TRANSITION",
                detail=f"Short-close is only allowed for partially_received orders (current: {po.status}).",
            )

        from_status = po.status
        po.status = "closed"
        po.version += 1
        po.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="purchase_order",
            entity_id=po.id,
            from_status=from_status,
            to_status="closed",
            reason=f"Short-closed: {payload.reason}",
            changed_by=user_id,
        )
        self.db.commit()
        return self.get_purchase_order(po.id)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _build_po_items(
        self, po: PurchaseOrder, item_payloads: list[PurchaseOrderItemPayload]
    ) -> None:
        subtotal = Decimal("0.0000")
        tax_total = Decimal("0.0000")
        grand_total = Decimal("0.0000")

        for idx, payload in enumerate(item_payloads, start=1):
            product = self.db.execute(
                select(Product).where(Product.id == payload.product_id)
            ).scalar_one_or_none()
            if not product or not product.is_active:
                raise NotFoundException(f"Product #{payload.product_id} not found or inactive.")

            tax_rate = self.db.execute(
                select(TaxRate).where(TaxRate.id == payload.tax_rate_id)
            ).scalar_one_or_none()
            if not tax_rate or not tax_rate.is_active:
                raise NotFoundException(f"Tax rate #{payload.tax_rate_id} not found or inactive.")

            qty = Decimal(str(payload.quantity))
            cost = Decimal(str(payload.unit_cost))
            rate = Decimal(str(tax_rate.rate))

            line_net = round_money(qty * cost)
            line_tax = round_money(line_net * rate)
            line_total = line_net + line_tax

            subtotal += line_net
            tax_total += line_tax
            grand_total += line_total

            item = PurchaseOrderItem(
                purchase_order_id=po.id,
                line_no=idx,
                product_id=product.id,
                description=payload.description or product.name,
                uom=payload.uom or product.uom,
                quantity=qty,
                unit_cost=cost,
                tax_rate_id=tax_rate.id,
                tax_rate=rate,
                line_net=line_net,
                line_tax=line_tax,
                line_total=line_total,
                quantity_received=Decimal("0.000"),
                quantity_billed=Decimal("0.000"),
            )
            self.db.add(item)

        po.subtotal = subtotal
        po.tax_total = tax_total
        po.grand_total = grand_total
