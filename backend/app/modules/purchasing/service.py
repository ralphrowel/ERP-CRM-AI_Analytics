from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import get_clock
from app.core.errors import AppException, ConflictException, NotFoundException
from app.core.money import round_money, round_qty, round_unit_price
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.catalog.models import Product
from app.modules.inventory.models import InventoryBalance, InventoryTransaction, Warehouse
from app.modules.organization.models import CompanySettings
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierProduct,
)
from app.modules.purchasing.schemas import (
    GoodsReceiptCreate,
    PurchaseOrderClosePayload,
    PurchaseOrderCreate,
    PurchaseOrderItemPayload,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierInvoiceCreate,
    SupplierPaymentCreate,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierStatementBillItem,
    SupplierStatementOut,
    SupplierStatementPaymentItem,
    SupplierUpdate,
)
from app.modules.sales.models import TaxRate


class PurchasingService:
    def __init__(self, db: Session):
        self.db = db
        self.clock = get_clock()

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

        # Roadmap V0.7: Check PO_AMOUNT approval rule
        from app.modules.workflow.models import ApprovalRule
        from app.modules.workflow.service import WorkflowService

        rule = self.db.execute(
            select(ApprovalRule).where(
                ApprovalRule.code == "PO_AMOUNT",
                ApprovalRule.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if rule and rule.threshold_amount is not None and po.grand_total > rule.threshold_amount:
            wf_service = WorkflowService(self.db)
            wf_service.check_purchase_order_approval(po, requester_id=user_id or po.created_by or 1)
            po.status = "pending_approval"
            record_status_change(
                db=self.db,
                entity_type="purchase_order",
                entity_id=po.id,
                to_status="pending_approval",
                from_status="draft",
                reason=f"Grand total ₱{po.grand_total:,.2f} exceeds spend threshold ₱{rule.threshold_amount:,.2f}",
                changed_by=user_id,
            )
            self.db.commit()
            raise AppException(
                status_code=400,
                code="APPROVAL_REQUIRED",
                detail=f"Purchase order total ₱{po.grand_total:,.2f} exceeds spend threshold ₱{rule.threshold_amount:,.2f}. Managerial approval required.",
            )

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

    # ── Goods Receipts (Physical Receipts) ──────────────────────────────
    def list_goods_receipts(
        self,
        purchase_order_id: int | None = None,
        warehouse_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[GoodsReceipt], int]:
        stmt = (
            select(GoodsReceipt)
            .options(
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.product),
                selectinload(GoodsReceipt.purchase_order),
                selectinload(GoodsReceipt.warehouse),
            )
            .order_by(GoodsReceipt.id.desc())
        )
        count_stmt = select(func.count(GoodsReceipt.id))

        if purchase_order_id is not None:
            stmt = stmt.where(GoodsReceipt.purchase_order_id == purchase_order_id)
            count_stmt = count_stmt.where(GoodsReceipt.purchase_order_id == purchase_order_id)
        if warehouse_id is not None:
            stmt = stmt.where(GoodsReceipt.warehouse_id == warehouse_id)
            count_stmt = count_stmt.where(GoodsReceipt.warehouse_id == warehouse_id)
        if status is not None:
            stmt = stmt.where(GoodsReceipt.status == status)
            count_stmt = count_stmt.where(GoodsReceipt.status == status)

        total = self.db.execute(count_stmt).scalar() or 0
        offset = (page - 1) * page_size
        items = self.db.execute(stmt.offset(offset).limit(page_size)).scalars().all()
        return list(items), total

    def get_goods_receipt(self, receipt_id: int) -> GoodsReceipt:
        stmt = (
            select(GoodsReceipt)
            .options(
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.product),
                selectinload(GoodsReceipt.purchase_order),
                selectinload(GoodsReceipt.warehouse),
            )
            .where(GoodsReceipt.id == receipt_id)
        )
        receipt = self.db.execute(stmt).scalar_one_or_none()
        if not receipt:
            raise NotFoundException(f"Goods receipt #{receipt_id} not found.")
        return receipt

    def create_goods_receipt(
        self, payload: GoodsReceiptCreate, current_user_id: int | None = None
    ) -> GoodsReceipt:
        po = self.get_purchase_order(payload.purchase_order_id)

        if po.status not in ("sent", "partially_received"):
            raise AppException(
                status_code=400,
                code="INVALID_PO_STATUS",
                detail=f"Cannot receive goods for Purchase Order {po.po_no} in status '{po.status}'. Must be 'sent' or 'partially_received'.",
            )

        po_items_map = {item.id: item for item in po.items}
        gr_items: list[GoodsReceiptItem] = []

        for item_payload in payload.items:
            po_item = po_items_map.get(item_payload.purchase_order_item_id)
            if not po_item:
                raise AppException(
                    status_code=400,
                    code="INVALID_PO_ITEM",
                    detail=f"Item #{item_payload.purchase_order_item_id} does not belong to PO {po.po_no}.",
                )

            qty = round_qty(item_payload.quantity)
            if qty <= Decimal("0"):
                raise AppException(
                    status_code=400,
                    code="INVALID_QUANTITY",
                    detail=f"Receipt quantity must be greater than zero for PO line #{po_item.line_no}.",
                )

            remaining = po_item.quantity - po_item.quantity_received
            if qty > remaining:
                raise AppException(
                    status_code=400,
                    code="OVER_RECEIPT",
                    detail=(
                        f"Receipt quantity {qty} exceeds outstanding receivable quantity {remaining} "
                        f"for item '{po_item.description}' (Line #{po_item.line_no})."
                    ),
                )

            gr_items.append(
                GoodsReceiptItem(
                    purchase_order_item_id=po_item.id,
                    product_id=po_item.product_id,
                    quantity=qty,
                    unit_cost=po_item.unit_cost,
                )
            )

        gr_no = generate_next_number(self.db, "goods_receipt", clock=self.clock)
        receipt = GoodsReceipt(
            gr_no=gr_no,
            purchase_order_id=po.id,
            warehouse_id=po.warehouse_id,
            status="draft",
            supplier_delivery_ref=payload.supplier_delivery_ref.strip()
            if payload.supplier_delivery_ref
            else None,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            items=gr_items,
        )
        self.db.add(receipt)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="goods_receipt",
            entity_id=receipt.id,
            from_status=None,
            to_status="draft",
            reason=f"Draft receipt created for PO {po.po_no}",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_goods_receipt(receipt.id)

    def post_goods_receipt(
        self, receipt_id: int, current_user_id: int | None = None
    ) -> GoodsReceipt:
        receipt = self.get_goods_receipt(receipt_id)
        if receipt.status != "draft":
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                detail=f"Only draft goods receipts can be posted. Current status: '{receipt.status}'.",
            )

        po = receipt.purchase_order
        if po.status not in ("sent", "partially_received"):
            raise AppException(
                status_code=400,
                code="INVALID_PO_STATUS",
                detail=f"Purchase Order {po.po_no} is in status '{po.status}' and cannot receive goods.",
            )

        now = self.clock.now()

        # Deadlock Avoidance: Sort product IDs strictly ascending
        sorted_pids = sorted({item.product_id for item in receipt.items})
        balances_map: dict[int, InventoryBalance] = {}
        for pid in sorted_pids:
            bal_stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == receipt.warehouse_id,
                )
                .with_for_update()
            )
            bal = self.db.execute(bal_stmt).scalar_one_or_none()
            if bal:
                balances_map[pid] = bal

        for item in receipt.items:
            po_item = item.purchase_order_item
            remaining = po_item.quantity - po_item.quantity_received
            if item.quantity > remaining:
                raise AppException(
                    status_code=400,
                    code="OVER_RECEIPT",
                    detail=(
                        f"Receipt quantity {item.quantity} exceeds outstanding receivable quantity "
                        f"{remaining} for PO line #{po_item.line_no}."
                    ),
                )

            qty_in = item.quantity
            unit_cost_in = item.unit_cost
            total_cost = round_money(qty_in * unit_cost_in)

            bal = balances_map.get(item.product_id)
            if bal:
                new_avg = round_unit_price(
                    (bal.qty_on_hand * bal.avg_unit_cost + qty_in * unit_cost_in)
                    / (bal.qty_on_hand + qty_in)
                )
                bal.qty_on_hand += qty_in
                bal.avg_unit_cost = new_avg
                bal.updated_at = now
            else:
                new_avg = unit_cost_in
                bal = InventoryBalance(
                    product_id=item.product_id,
                    warehouse_id=receipt.warehouse_id,
                    qty_on_hand=qty_in,
                    qty_reserved=Decimal("0.000"),
                    avg_unit_cost=new_avg,
                    updated_at=now,
                )
                self.db.add(bal)
                balances_map[item.product_id] = bal

            txn = InventoryTransaction(
                product_id=item.product_id,
                warehouse_id=receipt.warehouse_id,
                txn_type="receipt",
                quantity=qty_in,
                unit_cost=unit_cost_in,
                total_cost=total_cost,
                qty_on_hand_after=bal.qty_on_hand,
                avg_cost_after=bal.avg_unit_cost,
                source_type="goods_receipt",
                source_id=receipt.id,
                source_line_id=item.id,
                occurred_at=now,
                posted_by=current_user_id,
                created_at=now,
            )
            self.db.add(txn)

            # Update PO line quantity_received
            po_item.quantity_received += qty_in

            # Update SupplierProduct last_unit_cost catalog
            sp = self.db.get(SupplierProduct, (po.supplier_id, item.product_id))
            if sp:
                sp.last_unit_cost = unit_cost_in

        # Update PO status
        is_fully_received = all(it.quantity_received >= it.quantity for it in po.items)
        new_po_status = "received" if is_fully_received else "partially_received"
        if po.status != new_po_status:
            old_po_status = po.status
            po.status = new_po_status
            record_status_change(
                self.db,
                entity_type="purchase_order",
                entity_id=po.id,
                from_status=old_po_status,
                to_status=new_po_status,
                reason=f"Goods receipt {receipt.gr_no} posted",
                changed_by=current_user_id,
                clock=self.clock,
            )

        # Transition GoodsReceipt to posted
        receipt.status = "posted"
        receipt.received_at = now
        record_status_change(
            self.db,
            entity_type="goods_receipt",
            entity_id=receipt.id,
            from_status="draft",
            to_status="posted",
            reason=f"Posted physical receipt against PO {po.po_no}",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.flush()
        return self.get_goods_receipt(receipt.id)

    def cancel_goods_receipt(
        self, receipt_id: int, current_user_id: int | None = None
    ) -> GoodsReceipt:
        receipt = self.get_goods_receipt(receipt_id)
        if receipt.status != "draft":
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                detail=f"Only draft receipts can be cancelled. Current status: '{receipt.status}'.",
            )

        receipt.status = "cancelled"
        record_status_change(
            self.db,
            entity_type="goods_receipt",
            entity_id=receipt.id,
            from_status="draft",
            to_status="cancelled",
            reason="Draft receipt cancelled by user",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_goods_receipt(receipt.id)

    # ── Supplier Invoices (Bills & 3-Way Matching) ──────────────────────
    def list_supplier_invoices(
        self,
        supplier_id: int | None = None,
        purchase_order_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SupplierInvoice], int]:
        stmt = (
            select(SupplierInvoice)
            .options(
                selectinload(SupplierInvoice.items).selectinload(SupplierInvoiceItem.product),
                selectinload(SupplierInvoice.supplier),
                selectinload(SupplierInvoice.purchase_order),
            )
            .order_by(SupplierInvoice.id.desc())
        )
        count_stmt = select(func.count(SupplierInvoice.id))

        if supplier_id is not None:
            stmt = stmt.where(SupplierInvoice.supplier_id == supplier_id)
            count_stmt = count_stmt.where(SupplierInvoice.supplier_id == supplier_id)
        if purchase_order_id is not None:
            stmt = stmt.where(SupplierInvoice.purchase_order_id == purchase_order_id)
            count_stmt = count_stmt.where(SupplierInvoice.purchase_order_id == purchase_order_id)
        if status is not None:
            stmt = stmt.where(SupplierInvoice.status == status)
            count_stmt = count_stmt.where(SupplierInvoice.status == status)

        total = self.db.execute(count_stmt).scalar() or 0
        offset = (page - 1) * page_size
        items = self.db.execute(stmt.offset(offset).limit(page_size)).scalars().all()
        return list(items), total

    def get_supplier_invoice(self, invoice_id: int) -> SupplierInvoice:
        stmt = (
            select(SupplierInvoice)
            .options(
                selectinload(SupplierInvoice.items).selectinload(SupplierInvoiceItem.product),
                selectinload(SupplierInvoice.supplier),
                selectinload(SupplierInvoice.purchase_order),
            )
            .where(SupplierInvoice.id == invoice_id)
        )
        bill = self.db.execute(stmt).scalar_one_or_none()
        if not bill:
            raise NotFoundException(f"Supplier bill #{invoice_id} not found.")
        return bill

    def create_supplier_invoice(
        self, payload: SupplierInvoiceCreate, current_user_id: int | None = None
    ) -> SupplierInvoice:
        po = self.get_purchase_order(payload.purchase_order_id)
        if po.status not in ("sent", "partially_received", "received"):
            raise AppException(
                status_code=400,
                code="INVALID_PO_STATUS",
                detail=f"Cannot bill Purchase Order {po.po_no} in status '{po.status}'. Must be sent or received.",
            )

        ref_clean = payload.supplier_invoice_ref.strip()
        existing_ref = self.db.execute(
            select(SupplierInvoice).where(
                SupplierInvoice.supplier_id == po.supplier_id,
                SupplierInvoice.supplier_invoice_ref == ref_clean,
            )
        ).scalar_one_or_none()
        if existing_ref:
            raise ConflictException(
                f"Supplier invoice reference '{ref_clean}' already exists for supplier #{po.supplier_id}."
            )

        # Get tolerance setting
        company_settings = self.db.get(CompanySettings, 1)
        tolerance_pct = (
            company_settings.bill_price_tolerance_pct if company_settings else Decimal("0.0000")
        )

        po_items_map = {item.id: item for item in po.items}
        bill_items: list[SupplierInvoiceItem] = []
        mismatch_reasons: list[str] = []

        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for idx, item_payload in enumerate(payload.items, start=1):
            po_item = po_items_map.get(item_payload.purchase_order_item_id)
            if not po_item:
                raise AppException(
                    status_code=400,
                    code="INVALID_PO_ITEM",
                    detail=f"Line #{idx}: PO item #{item_payload.purchase_order_item_id} does not belong to PO {po.po_no}.",
                )

            qty = round_qty(item_payload.quantity)
            unit_cost = round_unit_price(item_payload.unit_cost)
            tax_rate = po_item.tax_rate

            line_net = round_money(qty * unit_cost)
            line_tax = round_money(line_net * tax_rate)
            line_total = line_net + line_tax

            subtotal += line_net
            tax_total += line_tax
            grand_total += line_total

            # 3-Way Match Check 1: Cumulative billed quantity vs received quantity
            stmt_billed = (
                select(func.coalesce(func.sum(SupplierInvoiceItem.quantity), 0))
                .join(SupplierInvoice)
                .where(
                    SupplierInvoiceItem.purchase_order_item_id == po_item.id,
                    SupplierInvoice.status.notin_(("void", "draft")),
                )
            )
            existing_billed = self.db.execute(stmt_billed).scalar() or Decimal("0.000")
            total_billed = existing_billed + qty

            if total_billed > po_item.quantity_received:
                mismatch_reasons.append(
                    f"Line #{idx} ({po_item.description}): Cumulative billed qty ({total_billed}) "
                    f"exceeds received qty ({po_item.quantity_received})."
                )

            # 3-Way Match Check 2: Unit cost tolerance
            po_cost = po_item.unit_cost
            cost_diff = abs(unit_cost - po_cost)
            allowed_tolerance = po_cost * tolerance_pct

            if cost_diff > allowed_tolerance:
                mismatch_reasons.append(
                    f"Line #{idx} ({po_item.description}): Billed cost ₱{unit_cost} differs from PO cost "
                    f"₱{po_cost} beyond allowed tolerance of {tolerance_pct * 100}% (max diff: ₱{allowed_tolerance})."
                )

            bill_items.append(
                SupplierInvoiceItem(
                    purchase_order_item_id=po_item.id,
                    product_id=po_item.product_id,
                    line_no=idx,
                    description=po_item.description,
                    uom=po_item.uom,
                    quantity=qty,
                    unit_cost=unit_cost,
                    tax_rate_id=po_item.tax_rate_id,
                    tax_rate=tax_rate,
                    line_net=line_net,
                    line_tax=line_tax,
                    line_total=line_total,
                )
            )

        bill_no = generate_next_number(self.db, "supplier_invoice", clock=self.clock)
        invoice_date = payload.invoice_date or self.clock.today()
        due_date = payload.due_date or (
            invoice_date + timedelta(days=po.payment_terms_days_snapshot)
        )

        initial_status = "exception" if mismatch_reasons else "matched"
        match_notes = (
            "; ".join(mismatch_reasons)
            if mismatch_reasons
            else f"3-way match passed successfully against PO {po.po_no}."
        )

        bill = SupplierInvoice(
            bill_no=bill_no,
            supplier_id=po.supplier_id,
            purchase_order_id=po.id,
            supplier_invoice_ref=ref_clean,
            status=initial_status,
            invoice_date=invoice_date,
            due_date=due_date,
            subtotal=subtotal,
            tax_total=tax_total,
            grand_total=grand_total,
            amount_paid=Decimal("0.00"),
            balance_due=grand_total,
            match_notes=match_notes,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            items=bill_items,
        )
        self.db.add(bill)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="supplier_invoice",
            entity_id=bill.id,
            from_status=None,
            to_status=initial_status,
            reason=f"Bill created from PO {po.po_no} ({match_notes})",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_supplier_invoice(bill.id)

    def approve_supplier_invoice(
        self, invoice_id: int, current_user_id: int | None = None
    ) -> SupplierInvoice:
        bill = self.get_supplier_invoice(invoice_id)
        if bill.status not in ("matched", "exception"):
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                detail=f"Cannot approve bill in status '{bill.status}'. Must be 'matched' or 'exception'.",
            )

        old_status = bill.status
        bill.status = "approved"

        # Update PO items quantity_billed
        for item in bill.items:
            po_item = item.purchase_order_item
            po_item.quantity_billed += item.quantity

        record_status_change(
            self.db,
            entity_type="supplier_invoice",
            entity_id=bill.id,
            from_status=old_status,
            to_status="approved",
            reason="Approved for AP payment allocation",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_supplier_invoice(bill.id)

    def void_supplier_invoice(
        self, invoice_id: int, reason: str, current_user_id: int | None = None
    ) -> SupplierInvoice:
        bill = self.get_supplier_invoice(invoice_id)
        if bill.status not in ("draft", "matched", "exception", "approved"):
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                detail=f"Cannot void bill in status '{bill.status}'.",
            )
        if bill.amount_paid > Decimal("0.00"):
            raise AppException(
                status_code=400,
                code="BILL_HAS_PAYMENTS",
                detail=f"Cannot void bill with existing payment allocations of ₱{bill.amount_paid}.",
            )

        old_status = bill.status
        # If was approved, reverse quantity_billed on PO
        if old_status == "approved":
            for item in bill.items:
                po_item = item.purchase_order_item
                po_item.quantity_billed = max(
                    Decimal("0.000"), po_item.quantity_billed - item.quantity
                )

        bill.status = "void"
        record_status_change(
            self.db,
            entity_type="supplier_invoice",
            entity_id=bill.id,
            from_status=old_status,
            to_status="void",
            reason=f"Voided: {reason}",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_supplier_invoice(bill.id)

    # ── Accounts Payable (Supplier Payments & Allocations) ──────────────
    def list_supplier_payments(
        self,
        supplier_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SupplierPayment], int]:
        stmt = (
            select(SupplierPayment)
            .options(
                selectinload(SupplierPayment.allocations).selectinload(
                    SupplierPaymentAllocation.invoice
                ),
                selectinload(SupplierPayment.supplier),
            )
            .order_by(SupplierPayment.id.desc())
        )
        count_stmt = select(func.count(SupplierPayment.id))

        if supplier_id is not None:
            stmt = stmt.where(SupplierPayment.supplier_id == supplier_id)
            count_stmt = count_stmt.where(SupplierPayment.supplier_id == supplier_id)
        if status is not None:
            stmt = stmt.where(SupplierPayment.status == status)
            count_stmt = count_stmt.where(SupplierPayment.status == status)

        total = self.db.execute(count_stmt).scalar() or 0
        offset = (page - 1) * page_size
        items = self.db.execute(stmt.offset(offset).limit(page_size)).scalars().all()
        return list(items), total

    def get_supplier_payment(self, payment_id: int) -> SupplierPayment:
        stmt = (
            select(SupplierPayment)
            .options(
                selectinload(SupplierPayment.allocations).selectinload(
                    SupplierPaymentAllocation.invoice
                ),
                selectinload(SupplierPayment.supplier),
            )
            .where(SupplierPayment.id == payment_id)
        )
        payment = self.db.execute(stmt).scalar_one_or_none()
        if not payment:
            raise NotFoundException(f"Supplier payment #{payment_id} not found.")
        return payment

    def create_supplier_payment(
        self, payload: SupplierPaymentCreate, current_user_id: int | None = None
    ) -> SupplierPayment:
        supplier = self.get_supplier(payload.supplier_id)
        if not supplier.is_active:
            raise AppException(
                status_code=400,
                code="SUPPLIER_INACTIVE",
                detail=f"Supplier '{supplier.name}' is inactive.",
            )

        payment_amount = round_money(payload.amount)
        if payment_amount <= Decimal("0.00"):
            raise AppException(
                status_code=400,
                code="INVALID_AMOUNT",
                detail="Payment amount must be greater than zero.",
            )

        allocations: list[SupplierPaymentAllocation] = []
        total_allocated = Decimal("0.00")

        # Process allocations
        for alloc in payload.allocations:
            alloc_amt = round_money(alloc.amount)
            if alloc_amt <= Decimal("0.00"):
                continue

            bill = self.db.execute(
                select(SupplierInvoice)
                .where(SupplierInvoice.id == alloc.supplier_invoice_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not bill:
                raise NotFoundException(f"Supplier invoice #{alloc.supplier_invoice_id} not found.")

            if bill.supplier_id != supplier.id:
                raise AppException(
                    status_code=400,
                    code="SUPPLIER_MISMATCH",
                    detail=f"Invoice #{bill.bill_no} does not belong to supplier '{supplier.name}'.",
                )

            if bill.status not in ("approved", "partially_paid"):
                raise AppException(
                    status_code=400,
                    code="BILL_NOT_APPROVED",
                    detail=f"Cannot allocate payment to bill #{bill.bill_no} in status '{bill.status}'. Must be 'approved' or 'partially_paid'.",
                )

            if alloc_amt > bill.balance_due:
                raise AppException(
                    status_code=400,
                    code="OVER_ALLOCATION",
                    detail=f"Allocation amount ₱{alloc_amt} exceeds balance due ₱{bill.balance_due} for bill #{bill.bill_no}.",
                )

            total_allocated += alloc_amt
            if total_allocated > payment_amount:
                raise AppException(
                    status_code=400,
                    code="ALLOCATION_EXCEEDS_PAYMENT",
                    detail=f"Total allocations (₱{total_allocated}) exceed payment amount (₱{payment_amount}).",
                )

            bill.amount_paid += alloc_amt
            bill.balance_due = bill.grand_total - bill.amount_paid
            new_bill_status = "paid" if bill.balance_due == Decimal("0.00") else "partially_paid"
            if bill.status != new_bill_status:
                old_bill_status = bill.status
                bill.status = new_bill_status
                record_status_change(
                    self.db,
                    entity_type="supplier_invoice",
                    entity_id=bill.id,
                    from_status=old_bill_status,
                    to_status=new_bill_status,
                    reason=f"Payment allocated: ₱{alloc_amt}",
                    changed_by=current_user_id,
                    clock=self.clock,
                )

            allocations.append(
                SupplierPaymentAllocation(
                    supplier_invoice_id=bill.id,
                    amount=alloc_amt,
                    allocated_by=current_user_id,
                )
            )

        payment_no = generate_next_number(self.db, "supplier_payment", clock=self.clock)
        payment = SupplierPayment(
            payment_no=payment_no,
            supplier_id=supplier.id,
            payment_date=payload.payment_date or self.clock.today(),
            payment_method=payload.payment_method,
            reference_no=payload.reference_no.strip() if payload.reference_no else None,
            amount=payment_amount,
            amount_allocated=total_allocated,
            status="posted",
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            allocations=allocations,
        )
        self.db.add(payment)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="supplier_payment",
            entity_id=payment.id,
            from_status=None,
            to_status="posted",
            reason=f"Supplier payment created (Allocated ₱{total_allocated} / ₱{payment_amount})",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_supplier_payment(payment.id)

    def void_supplier_payment(
        self, payment_id: int, reason: str, current_user_id: int | None = None
    ) -> SupplierPayment:
        payment = self.get_supplier_payment(payment_id)
        if payment.status != "posted":
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                detail=f"Only posted payments can be voided. Current status: '{payment.status}'.",
            )

        now = self.clock.now()

        # Rollback allocations
        for alloc in payment.allocations:
            bill = self.db.execute(
                select(SupplierInvoice)
                .where(SupplierInvoice.id == alloc.supplier_invoice_id)
                .with_for_update()
            ).scalar_one_or_none()
            if bill:
                bill.amount_paid = max(Decimal("0.00"), bill.amount_paid - alloc.amount)
                bill.balance_due = bill.grand_total - bill.amount_paid
                new_status = "partially_paid" if bill.amount_paid > Decimal("0.00") else "approved"
                if bill.status != new_status:
                    old_status = bill.status
                    bill.status = new_status
                    record_status_change(
                        self.db,
                        entity_type="supplier_invoice",
                        entity_id=bill.id,
                        from_status=old_status,
                        to_status=new_status,
                        reason=f"Payment {payment.payment_no} voided; reversed allocation of ₱{alloc.amount}",
                        changed_by=current_user_id,
                        clock=self.clock,
                    )

        payment.status = "void"
        payment.void_reason = reason.strip()
        payment.voided_at = now
        record_status_change(
            self.db,
            entity_type="supplier_payment",
            entity_id=payment.id,
            from_status="posted",
            to_status="void",
            reason=f"Voided payment: {reason}",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self.get_supplier_payment(payment.id)

    # ── Supplier Statement & AP Reconciliation ──────────────────────────
    def get_supplier_statement(self, supplier_id: int) -> SupplierStatementOut:
        supplier = self.get_supplier(supplier_id)

        # Bills excluding void
        bills_stmt = (
            select(SupplierInvoice)
            .where(
                SupplierInvoice.supplier_id == supplier.id,
                SupplierInvoice.status != "void",
            )
            .order_by(SupplierInvoice.invoice_date.asc())
        )
        bills = self.db.execute(bills_stmt).scalars().all()

        # Payments excluding void
        payments_stmt = (
            select(SupplierPayment)
            .where(
                SupplierPayment.supplier_id == supplier.id,
                SupplierPayment.status == "posted",
            )
            .order_by(SupplierPayment.payment_date.asc())
        )
        payments = self.db.execute(payments_stmt).scalars().all()

        total_billed = sum((b.grand_total for b in bills), start=Decimal("0.00"))
        total_paid = sum((p.amount for p in payments), start=Decimal("0.00"))
        total_outstanding = sum((b.balance_due for b in bills), start=Decimal("0.00"))

        return SupplierStatementOut(
            supplier_id=supplier.id,
            supplier_no=supplier.supplier_no,
            supplier_name=supplier.name,
            bills=[
                SupplierStatementBillItem(
                    id=b.id,
                    bill_no=b.bill_no,
                    supplier_invoice_ref=b.supplier_invoice_ref,
                    invoice_date=b.invoice_date,
                    due_date=b.due_date,
                    grand_total=b.grand_total,
                    amount_paid=b.amount_paid,
                    balance_due=b.balance_due,
                    status=b.status,
                )
                for b in bills
            ],
            payments=[
                SupplierStatementPaymentItem(
                    id=p.id,
                    payment_no=p.payment_no,
                    payment_date=p.payment_date,
                    payment_method=p.payment_method,
                    reference_no=p.reference_no,
                    amount=p.amount,
                    amount_allocated=p.amount_allocated,
                    status=p.status,
                )
                for p in payments
            ],
            total_billed=round_money(total_billed),
            total_paid=round_money(total_paid),
            total_outstanding=round_money(total_outstanding),
        )
