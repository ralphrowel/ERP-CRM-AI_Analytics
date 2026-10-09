from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, get_clock
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.money import round_money, round_qty, round_unit_price
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.catalog.models import Product
from app.modules.inventory.models import (
    InventoryBalance,
    InventoryTransaction,
    Shipment,
    ShipmentItem,
    StockAdjustment,
    StockAdjustmentItem,
    StockReservation,
    StockTransfer,
    StockTransferItem,
    Warehouse,
)
from app.modules.inventory.schemas import (
    InventoryBalanceOut,
    InventoryReconciliationItem,
    InventoryReconciliationOut,
    InventoryTransactionOut,
    OpeningBalancesCreatePayload,
    ShipmentCreatePayload,
    ShipmentItemOut,
    ShipmentOut,
    ShipmentPostPayload,
    StockAdjustmentCreatePayload,
    StockAdjustmentItemOut,
    StockAdjustmentOut,
    StockTransferCreatePayload,
    StockTransferItemOut,
    StockTransferOut,
    WarehouseCreatePayload,
    WarehouseOut,
    WarehouseUpdatePayload,
)
from app.modules.sales.models import Invoice, SalesOrder, SalesOrderItem


class InventoryService:
    def __init__(self, db: Session, clock: Clock | None = None):
        self.db = db
        self.clock = clock or get_clock()

    # ── Warehouse Management ───────────────────────────────────────────
    def list_warehouses(self, active_only: bool = False) -> list[WarehouseOut]:
        stmt = select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.name.asc())
        if active_only:
            stmt = stmt.where(Warehouse.is_active.is_(True))
        warehouses = self.db.execute(stmt).scalars().all()
        return [WarehouseOut.model_validate(w) for w in warehouses]

    def get_warehouse(self, warehouse_id: int) -> Warehouse:
        warehouse = self.db.get(Warehouse, warehouse_id)
        if not warehouse:
            raise NotFoundError(f"Warehouse with ID {warehouse_id} not found.")
        return warehouse

    def get_default_warehouse(self) -> Warehouse:
        stmt = select(Warehouse).where(Warehouse.is_default.is_(True)).limit(1)
        warehouse = self.db.execute(stmt).scalar_one_or_none()
        if not warehouse:
            # Fallback to any active warehouse
            stmt_any = (
                select(Warehouse)
                .where(Warehouse.is_active.is_(True))
                .order_by(Warehouse.id.asc())
                .limit(1)
            )
            warehouse = self.db.execute(stmt_any).scalar_one_or_none()
        if not warehouse:
            warehouse = Warehouse(
                code="MNL-MAIN",
                name="Main Warehouse - Manila",
                address="Port Area, Manila, Philippines",
                is_active=True,
                is_default=True,
            )
            self.db.add(warehouse)
            self.db.flush()
        return warehouse

    def create_warehouse(self, payload: WarehouseCreatePayload) -> WarehouseOut:
        existing = self.db.execute(
            select(Warehouse).where(func.lower(Warehouse.code) == payload.code.strip().lower())
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Warehouse code '{payload.code}' already exists.")

        if payload.is_default:
            # Clear existing default
            self.db.execute(select(Warehouse).where(Warehouse.is_default.is_(True)))
            for w in (
                self.db.execute(select(Warehouse).where(Warehouse.is_default.is_(True)))
                .scalars()
                .all()
            ):
                w.is_default = False

        warehouse = Warehouse(
            code=payload.code.strip().upper(),
            name=payload.name.strip(),
            address=payload.address.strip() if payload.address else None,
            is_active=payload.is_active,
            is_default=payload.is_default,
        )
        self.db.add(warehouse)
        self.db.flush()
        return WarehouseOut.model_validate(warehouse)

    def update_warehouse(self, warehouse_id: int, payload: WarehouseUpdatePayload) -> WarehouseOut:
        warehouse = self.get_warehouse(warehouse_id)

        if payload.is_default:
            for w in (
                self.db.execute(select(Warehouse).where(Warehouse.is_default.is_(True)))
                .scalars()
                .all()
            ):
                if w.id != warehouse.id:
                    w.is_default = False
            warehouse.is_default = True
        elif payload.is_default is False and warehouse.is_default:
            raise BusinessRuleError(
                code="INVALID_DEFAULT_WAREHOUSE",
                detail="Cannot unset the default warehouse without designating another.",
            )

        if payload.name is not None:
            warehouse.name = payload.name.strip()
        if payload.address is not None:
            warehouse.address = payload.address.strip() if payload.address else None
        if payload.is_active is not None:
            if not payload.is_active and warehouse.is_default:
                raise BusinessRuleError(
                    code="CANNOT_DEACTIVATE_DEFAULT",
                    detail="Cannot deactivate the default warehouse.",
                )
            warehouse.is_active = payload.is_active

        self.db.flush()
        return WarehouseOut.model_validate(warehouse)

    # ── Opening Balances ───────────────────────────────────────────────
    def post_opening_balances(
        self, payload: OpeningBalancesCreatePayload, user_id: int | None = None
    ) -> list[InventoryBalanceOut]:
        warehouse = self.get_warehouse(payload.warehouse_id)
        if not warehouse.is_active:
            raise BusinessRuleError(
                code="WAREHOUSE_INACTIVE",
                detail=f"Warehouse '{warehouse.name}' is inactive.",
            )

        now = self.clock.now()
        results: list[InventoryBalanceOut] = []

        # Sort product IDs to prevent deadlocks
        sorted_items = sorted(payload.items, key=lambda x: x.product_id)

        for item in sorted_items:
            product = self.db.get(Product, item.product_id)
            if not product:
                raise NotFoundError(f"Product with ID {item.product_id} not found.")
            if product.product_type != "stock":
                raise BusinessRuleError(
                    code="INVALID_PRODUCT_TYPE",
                    detail=f"Product '{product.name}' is a service item and cannot hold inventory.",
                )

            # Check if balance already exists
            balance_stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == item.product_id,
                    InventoryBalance.warehouse_id == warehouse.id,
                )
                .with_for_update()
            )
            balance = self.db.execute(balance_stmt).scalar_one_or_none()

            if balance and balance.qty_on_hand > Decimal("0.000"):
                raise ConflictError(
                    f"Product '{product.name}' already has an inventory balance of {balance.qty_on_hand} in warehouse '{warehouse.name}'."
                )

            qty = round_qty(item.quantity)
            unit_cost = round_unit_price(item.unit_cost)
            total_cost = round_money(qty * unit_cost)

            # 1. Create opening transaction in immutable ledger
            txn = InventoryTransaction(
                product_id=product.id,
                warehouse_id=warehouse.id,
                txn_type="opening",
                quantity=qty,
                unit_cost=unit_cost,
                total_cost=total_cost,
                qty_on_hand_after=qty,
                avg_cost_after=unit_cost,
                source_type="opening",
                source_id=None,
                source_line_id=None,
                occurred_at=now,
                posted_by=user_id,
                created_at=now,
            )
            self.db.add(txn)

            # 2. Update or insert balance cache
            if balance:
                balance.qty_on_hand = qty
                balance.avg_unit_cost = unit_cost
                balance.updated_at = now
            else:
                balance = InventoryBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    qty_on_hand=qty,
                    qty_reserved=Decimal("0.000"),
                    avg_unit_cost=unit_cost,
                    updated_at=now,
                )
                self.db.add(balance)

            self.db.flush()

            avail = balance.qty_on_hand - balance.qty_reserved
            is_below = bool(product.reorder_point is not None and avail <= product.reorder_point)
            results.append(
                InventoryBalanceOut(
                    product_id=product.id,
                    product_sku=product.sku,
                    product_name=product.name,
                    product_uom=product.uom,
                    warehouse_id=warehouse.id,
                    warehouse_code=warehouse.code,
                    warehouse_name=warehouse.name,
                    qty_on_hand=balance.qty_on_hand,
                    qty_reserved=balance.qty_reserved,
                    qty_available=avail,
                    avg_unit_cost=balance.avg_unit_cost,
                    total_value=round_money(balance.qty_on_hand * balance.avg_unit_cost),
                    reorder_point=product.reorder_point,
                    is_below_reorder=is_below,
                    updated_at=balance.updated_at,
                )
            )

        return results

    # ── Order Stock Reservation Concurrency ────────────────────────────
    def reserve_sales_order_stock(self, order_id: int) -> None:
        """
        Reserves available stock for all physical products in a confirmed sales order.
        Acquires row-level locks on inventory_balances in strictly sorted product order
        to guarantee deadlock avoidance (Roadmap §V0.4 Rule 7).
        """
        order = (
            self.db.execute(
                select(SalesOrder)
                .options(
                    joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
                    joinedload(SalesOrder.warehouse),
                )
                .where(SalesOrder.id == order_id)
            )
            .unique()
            .scalar_one_or_none()
        )

        if not order:
            raise NotFoundError(f"Sales order with ID {order_id} not found.")

        # Filter only physical stock products
        stock_items: list[SalesOrderItem] = [
            item for item in order.items if item.product and item.product.product_type == "stock"
        ]
        if not stock_items:
            return  # Service-only order requires no stock reservation

        # Group required quantity by product_id
        product_quantities: dict[int, Decimal] = {}
        for item in stock_items:
            product_quantities[item.product_id] = (
                product_quantities.get(item.product_id, Decimal("0.000")) + item.quantity
            )

        # DEADLOCK AVOIDANCE: Sort product IDs strictly ascending
        sorted_product_ids = sorted(product_quantities.keys())

        # Lock inventory_balances rows for (product_id, order.warehouse_id) in sorted order
        balances_map: dict[int, InventoryBalance] = {}
        for pid in sorted_product_ids:
            stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == order.warehouse_id,
                )
                .with_for_update()
            )
            bal = self.db.execute(stmt).scalar_one_or_none()
            if bal:
                balances_map[pid] = bal

        # Check available stock for each product
        for pid in sorted_product_ids:
            req_qty = product_quantities[pid]
            bal = balances_map.get(pid)
            avail = (bal.qty_on_hand - bal.qty_reserved) if bal else Decimal("0.000")

            if avail < req_qty:
                product = self.db.get(Product, pid)
                product_label = f"'{product.name}' (SKU: {product.sku})" if product else f"ID {pid}"
                wh_label = order.warehouse.name if order.warehouse else f"ID {order.warehouse_id}"
                raise BusinessRuleError(
                    code="INSUFFICIENT_STOCK",
                    detail=(
                        f"Insufficient available inventory for product {product_label} "
                        f"in warehouse '{wh_label}'. Required: {req_qty}, Available: {avail}"
                    ),
                )

        # Allocate reservations
        now = self.clock.now()
        for item in stock_items:
            bal = balances_map[item.product_id]
            bal.qty_reserved += item.quantity
            bal.updated_at = now

            res = StockReservation(
                sales_order_item_id=item.id,
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=item.quantity,
                quantity_consumed=Decimal("0.000"),
                status="active",
                created_at=now,
            )
            self.db.add(res)

        self.db.flush()

    def release_sales_order_reservations(self, order_id: int) -> None:
        """
        Releases active reservations when a sales order is cancelled.
        """
        order = self.db.get(SalesOrder, order_id)
        if not order:
            return

        order_item_ids = [
            item_id
            for (item_id,) in self.db.execute(
                select(SalesOrderItem.id).where(SalesOrderItem.sales_order_id == order_id)
            ).all()
        ]
        if not order_item_ids:
            return

        reservations = (
            self.db.execute(
                select(StockReservation).where(
                    StockReservation.sales_order_item_id.in_(order_item_ids),
                    StockReservation.status == "active",
                )
            )
            .scalars()
            .all()
        )
        if not reservations:
            return

        # Sort product IDs for deadlock avoidance
        sorted_product_ids = sorted({r.product_id for r in reservations})
        now = self.clock.now()

        for pid in sorted_product_ids:
            stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == order.warehouse_id,
                )
                .with_for_update()
            )
            bal = self.db.execute(stmt).scalar_one_or_none()
            if bal:
                # Sum released quantity for this product
                qty_to_release = sum(
                    (r.quantity - r.quantity_consumed)
                    for r in reservations
                    if r.product_id == pid and r.status == "active"
                )
                bal.qty_reserved = max(Decimal("0.000"), bal.qty_reserved - qty_to_release)
                bal.updated_at = now

        for res in reservations:
            res.status = "released"
            res.released_at = now

        self.db.flush()

    # ── Inventory Balances Query ───────────────────────────────────────
    def list_inventory_balances(
        self,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        below_reorder: bool | None = None,
    ) -> list[InventoryBalanceOut]:
        stmt = (
            select(InventoryBalance)
            .options(
                joinedload(InventoryBalance.product),
                joinedload(InventoryBalance.warehouse),
            )
            .join(Product, InventoryBalance.product_id == Product.id)
            .join(Warehouse, InventoryBalance.warehouse_id == Warehouse.id)
        )

        if warehouse_id is not None:
            stmt = stmt.where(InventoryBalance.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(InventoryBalance.product_id == product_id)

        stmt = stmt.order_by(Warehouse.name.asc(), Product.name.asc())
        balances = self.db.execute(stmt).scalars().all()

        results: list[InventoryBalanceOut] = []
        for bal in balances:
            avail = bal.qty_on_hand - bal.qty_reserved
            is_below = bool(
                bal.product.reorder_point is not None and avail <= bal.product.reorder_point
            )

            if below_reorder is True and not is_below:
                continue
            if below_reorder is False and is_below:
                continue

            results.append(
                InventoryBalanceOut(
                    product_id=bal.product.id,
                    product_sku=bal.product.sku,
                    product_name=bal.product.name,
                    product_uom=bal.product.uom,
                    warehouse_id=bal.warehouse.id,
                    warehouse_code=bal.warehouse.code,
                    warehouse_name=bal.warehouse.name,
                    qty_on_hand=bal.qty_on_hand,
                    qty_reserved=bal.qty_reserved,
                    qty_available=avail,
                    avg_unit_cost=bal.avg_unit_cost,
                    total_value=round_money(bal.qty_on_hand * bal.avg_unit_cost),
                    reorder_point=bal.product.reorder_point,
                    is_below_reorder=is_below,
                    updated_at=bal.updated_at,
                )
            )

        return results

    # ── Ledger Transactions Query ──────────────────────────────────────
    def list_inventory_transactions(
        self,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        limit: int = 100,
    ) -> list[InventoryTransactionOut]:
        stmt = (
            select(InventoryTransaction)
            .options(
                joinedload(InventoryTransaction.product),
                joinedload(InventoryTransaction.warehouse),
            )
            .order_by(InventoryTransaction.occurred_at.desc(), InventoryTransaction.id.desc())
            .limit(limit)
        )

        if warehouse_id is not None:
            stmt = stmt.where(InventoryTransaction.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(InventoryTransaction.product_id == product_id)

        txns = self.db.execute(stmt).scalars().all()
        return [
            InventoryTransactionOut(
                id=t.id,
                product_id=t.product_id,
                product_sku=t.product.sku,
                product_name=t.product.name,
                warehouse_id=t.warehouse_id,
                warehouse_code=t.warehouse.code,
                txn_type=t.txn_type,
                quantity=t.quantity,
                unit_cost=t.unit_cost,
                total_cost=t.total_cost,
                qty_on_hand_after=t.qty_on_hand_after,
                avg_cost_after=t.avg_cost_after,
                source_type=t.source_type,
                source_id=t.source_id,
                source_line_id=t.source_line_id,
                occurred_at=t.occurred_at,
                posted_by=t.posted_by,
                created_at=t.created_at,
            )
            for t in txns
        ]

    # ── Ledger Reconciliation ──────────────────────────────────────────
    def get_inventory_reconciliation(self) -> InventoryReconciliationOut:
        """
        Verifies for every (product, warehouse) that:
          1. Σ ledger.quantity == qty_on_hand (physical integrity)
          2. latest avg_cost_after == avg_unit_cost (costing integrity)
        """
        now = self.clock.now()
        stmt = select(InventoryBalance).options(
            joinedload(InventoryBalance.product),
            joinedload(InventoryBalance.warehouse),
        )
        balances = self.db.execute(stmt).scalars().all()

        items: list[InventoryReconciliationItem] = []
        discrepant_count = 0

        for bal in balances:
            # Sum ledger
            sum_ledger = self.db.execute(
                select(
                    func.coalesce(func.sum(InventoryTransaction.quantity), Decimal("0.000"))
                ).where(
                    InventoryTransaction.product_id == bal.product_id,
                    InventoryTransaction.warehouse_id == bal.warehouse_id,
                )
            ).scalar_one()

            # Latest transaction
            last_txn = self.db.execute(
                select(InventoryTransaction)
                .where(
                    InventoryTransaction.product_id == bal.product_id,
                    InventoryTransaction.warehouse_id == bal.warehouse_id,
                )
                .order_by(InventoryTransaction.occurred_at.desc(), InventoryTransaction.id.desc())
                .limit(1)
            ).scalar_one_or_none()

            last_cost = last_txn.avg_cost_after if last_txn else Decimal("0.0000")
            qty_diff = bal.qty_on_hand - sum_ledger
            cost_diff = bal.avg_unit_cost - last_cost

            is_ok = bool(qty_diff == Decimal("0.000") and cost_diff == Decimal("0.0000"))
            if not is_ok:
                discrepant_count += 1

            items.append(
                InventoryReconciliationItem(
                    product_id=bal.product_id,
                    product_sku=bal.product.sku,
                    product_name=bal.product.name,
                    warehouse_id=bal.warehouse_id,
                    warehouse_code=bal.warehouse.code,
                    sum_ledger_qty=sum_ledger,
                    qty_on_hand=bal.qty_on_hand,
                    qty_discrepancy=qty_diff,
                    avg_unit_cost=bal.avg_unit_cost,
                    last_ledger_avg_cost=last_cost,
                    cost_discrepancy=cost_diff,
                    is_reconciled=is_ok,
                )
            )

        return InventoryReconciliationOut(
            reconciled_at=now,
            total_items_checked=len(balances),
            discrepant_count=discrepant_count,
            items=items,
        )

    # ── Shipments & Physical Fulfillment ───────────────────────────────
    def _map_shipment_out(self, s: Shipment) -> ShipmentOut:
        total_cogs = (
            sum((it.cogs_amount or Decimal("0.00")) for it in s.items if it.cogs_amount is not None)
            if s.status == "posted"
            else None
        )
        return ShipmentOut(
            id=s.id,
            shipment_no=s.shipment_no,
            sales_order_id=s.sales_order_id,
            sales_order_no=s.order.order_no if s.order else "",
            warehouse_id=s.warehouse_id,
            warehouse_code=s.warehouse.code if s.warehouse else "",
            warehouse_name=s.warehouse.name if s.warehouse else "",
            status=s.status,
            shipped_at=s.shipped_at,
            carrier=s.carrier,
            tracking_no=s.tracking_no,
            notes=s.notes,
            total_cogs=total_cogs,
            version=s.version,
            created_at=s.created_at,
            created_by=s.created_by,
            items=[
                ShipmentItemOut(
                    id=it.id,
                    shipment_id=it.shipment_id,
                    sales_order_item_id=it.sales_order_item_id,
                    product_id=it.product_id,
                    product_sku=it.product.sku if it.product else "",
                    product_name=it.product.name if it.product else "",
                    product_uom=it.product.uom if it.product else "",
                    quantity=it.quantity,
                    unit_cost=it.unit_cost,
                    cogs_amount=it.cogs_amount,
                    created_at=it.created_at,
                )
                for it in s.items
            ],
        )

    def create_shipment(
        self, payload: ShipmentCreatePayload, current_user_id: int | None = None
    ) -> ShipmentOut:
        order = (
            self.db.execute(
                select(SalesOrder)
                .options(
                    joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
                    joinedload(SalesOrder.warehouse),
                )
                .where(SalesOrder.id == payload.sales_order_id)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not order:
            raise NotFoundError(f"Sales order with ID {payload.sales_order_id} not found.")

        if order.status in ("draft", "cancelled", "on_hold"):
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Cannot create shipment for order in status '{order.status}'.",
            )

        warehouse_id = payload.warehouse_id or order.warehouse_id
        warehouse = self.get_warehouse(warehouse_id)
        if not warehouse.is_active:
            raise BusinessRuleError(
                code="WAREHOUSE_INACTIVE",
                detail=f"Warehouse '{warehouse.name}' is inactive.",
            )

        # Map eligible stock products on the order
        stock_items = [
            item for item in order.items if item.product and item.product.product_type == "stock"
        ]
        if not stock_items:
            raise BusinessRuleError(
                code="NO_SHIPPABLE_ITEMS",
                detail="Sales order contains no shippable physical products.",
            )

        so_items_map = {item.id: item for item in stock_items}
        shipment_items: list[ShipmentItem] = []

        if payload.items is None or len(payload.items) == 0:
            # Auto-populate all remaining unshipped quantities
            for so_item in stock_items:
                remaining = so_item.quantity - so_item.quantity_shipped
                if remaining > Decimal("0.000"):
                    shipment_items.append(
                        ShipmentItem(
                            sales_order_item_id=so_item.id,
                            product_id=so_item.product_id,
                            quantity=remaining,
                        )
                    )
            if not shipment_items:
                raise BusinessRuleError(
                    code="ORDER_ALREADY_FULFILLED",
                    detail=f"All physical items on order {order.order_no} have already been fully shipped.",
                )
        else:
            seen_items: set[int] = set()
            for item_payload in payload.items:
                if item_payload.sales_order_item_id not in so_items_map:
                    raise BusinessRuleError(
                        code="INVALID_SHIPMENT_ITEM",
                        detail=f"Order item ID {item_payload.sales_order_item_id} is not an unshipped stock item on this sales order.",
                    )
                if item_payload.sales_order_item_id in seen_items:
                    raise BusinessRuleError(
                        code="DUPLICATE_ITEM",
                        detail="Each order item may only appear once per shipment.",
                    )
                seen_items.add(item_payload.sales_order_item_id)

                so_item = so_items_map[item_payload.sales_order_item_id]
                remaining = so_item.quantity - so_item.quantity_shipped
                requested_qty = round_qty(item_payload.quantity)

                if requested_qty > remaining:
                    raise BusinessRuleError(
                        code="EXCEEDS_ORDER_QUANTITY",
                        detail=f"Shipment quantity {requested_qty} exceeds remaining unshipped quantity {remaining} for item '{so_item.description}'.",
                    )

                shipment_items.append(
                    ShipmentItem(
                        sales_order_item_id=so_item.id,
                        product_id=so_item.product_id,
                        quantity=requested_qty,
                    )
                )

        shipment = Shipment(
            sales_order_id=order.id,
            warehouse_id=warehouse.id,
            status="draft",
            carrier=payload.carrier.strip() if payload.carrier else None,
            tracking_no=payload.tracking_no.strip() if payload.tracking_no else None,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            items=shipment_items,
        )
        self.db.add(shipment)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="shipment",
            entity_id=shipment.id,
            from_status=None,
            to_status="draft",
            reason=f"Draft shipment created for Sales Order {order.order_no}",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()

        # Re-fetch with relationships for output
        return self._map_shipment_out(self.get_shipment(shipment.id))

    def get_shipment(self, shipment_id: int) -> Shipment:
        stmt = (
            select(Shipment)
            .options(
                joinedload(Shipment.order),
                joinedload(Shipment.warehouse),
                joinedload(Shipment.items).joinedload(ShipmentItem.product),
            )
            .where(Shipment.id == shipment_id)
        )
        shipment = self.db.execute(stmt).unique().scalar_one_or_none()
        if not shipment:
            raise NotFoundError(f"Shipment with ID {shipment_id} not found.")
        return shipment

    def list_shipments(
        self,
        warehouse_id: int | None = None,
        sales_order_id: int | None = None,
        status: str | None = None,
    ) -> list[ShipmentOut]:
        stmt = (
            select(Shipment)
            .options(
                joinedload(Shipment.order),
                joinedload(Shipment.warehouse),
                joinedload(Shipment.items).joinedload(ShipmentItem.product),
            )
            .order_by(Shipment.id.desc())
        )
        if warehouse_id is not None:
            stmt = stmt.where(Shipment.warehouse_id == warehouse_id)
        if sales_order_id is not None:
            stmt = stmt.where(Shipment.sales_order_id == sales_order_id)
        if status is not None:
            stmt = stmt.where(Shipment.status == status)

        shipments = self.db.execute(stmt).unique().scalars().all()
        return [self._map_shipment_out(s) for s in shipments]

    def post_shipment(
        self,
        shipment_id: int,
        payload: ShipmentPostPayload | None = None,
        current_user_id: int | None = None,
    ) -> ShipmentOut:
        shipment = self.get_shipment(shipment_id)
        if shipment.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft shipments can be posted. Current status: '{shipment.status}'.",
            )

        order = (
            self.db.execute(
                select(SalesOrder)
                .options(joinedload(SalesOrder.items))
                .where(SalesOrder.id == shipment.sales_order_id)
            )
            .unique()
            .scalar_one()
        )

        # 1. Prepaid Rule Enforcement (Roadmap §V0.4 Rule 4)
        if order.payment_terms_days_snapshot == 0:
            issued_invoices = (
                self.db.execute(
                    select(Invoice).where(
                        Invoice.sales_order_id == order.id,
                        Invoice.status != "void",
                    )
                )
                .scalars()
                .all()
            )
            if not issued_invoices or any(inv.status != "paid" for inv in issued_invoices):
                raise BusinessRuleError(
                    code="PREPAYMENT_REQUIRED",
                    detail="Prepaid sales orders (payment terms 0 days) require all issued invoices to be fully paid prior to shipment posting.",
                )

        now = self.clock.now()

        # 2. Deadlock Avoidance: Sort product IDs strictly ascending (Roadmap §V0.4 Rule 7)
        sorted_pids = sorted({it.product_id for it in shipment.items})
        balances_map: dict[int, InventoryBalance] = {}
        for pid in sorted_pids:
            bal_stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == shipment.warehouse_id,
                )
                .with_for_update()
            )
            bal = self.db.execute(bal_stmt).scalar_one_or_none()
            if bal:
                balances_map[pid] = bal

        so_items_map = {item.id: item for item in order.items}

        # 3. Process stock issue per item
        for item in shipment.items:
            bal = balances_map.get(item.product_id)
            if not bal or bal.qty_on_hand < item.quantity:
                product_name = item.product.name if item.product else f"ID {item.product_id}"
                on_hand = bal.qty_on_hand if bal else Decimal("0.000")
                raise BusinessRuleError(
                    code="INSUFFICIENT_STOCK",
                    detail=f"Insufficient physical inventory on hand for product '{product_name}'. Required: {item.quantity}, On hand: {on_hand}.",
                )

            so_item = so_items_map[item.sales_order_item_id]
            remaining = so_item.quantity - so_item.quantity_shipped
            if item.quantity > remaining:
                raise BusinessRuleError(
                    code="EXCEEDS_ORDER_QUANTITY",
                    detail=f"Shipment quantity {item.quantity} exceeds unshipped quantity {remaining} for item '{so_item.description}'.",
                )

            # Snapshot unit cost and COGS
            unit_cost = bal.avg_unit_cost
            cogs_amount = round_money(item.quantity * unit_cost)
            item.unit_cost = unit_cost
            item.cogs_amount = cogs_amount

            # Reduce on hand and reserved balances
            bal.qty_on_hand -= item.quantity
            bal.qty_reserved = max(Decimal("0.000"), bal.qty_reserved - item.quantity)
            bal.updated_at = now

            # 4. Write immutable ledger transaction row
            txn = InventoryTransaction(
                product_id=item.product_id,
                warehouse_id=shipment.warehouse_id,
                txn_type="issue",
                quantity=-item.quantity,  # Negative for issue
                unit_cost=unit_cost,
                total_cost=-cogs_amount,  # Signed negative
                qty_on_hand_after=bal.qty_on_hand,
                avg_cost_after=bal.avg_unit_cost,
                source_type="shipment",
                source_id=shipment.id,
                source_line_id=item.id,
                occurred_at=now,
                posted_by=current_user_id,
                created_at=now,
            )
            self.db.add(txn)

            # 5. Consume reservation
            res = (
                self.db.execute(
                    select(StockReservation).where(
                        StockReservation.sales_order_item_id == so_item.id,
                        StockReservation.status == "active",
                    )
                )
                .scalars()
                .first()
            )
            if res:
                res.quantity_consumed += item.quantity
                if res.quantity_consumed >= res.quantity:
                    res.status = "consumed"

            # 6. Update order item shipped quantity
            so_item.quantity_shipped += item.quantity

        # 7. Update shipment metadata
        shipment_no = generate_next_number(self.db, "shipment", self.clock)
        shipment.shipment_no = shipment_no
        shipment.status = "posted"
        shipment.shipped_at = now
        shipment.version += 1
        shipment.updated_by = current_user_id

        if payload:
            if payload.carrier is not None:
                shipment.carrier = payload.carrier.strip() if payload.carrier else None
            if payload.tracking_no is not None:
                shipment.tracking_no = payload.tracking_no.strip() if payload.tracking_no else None
            if payload.notes is not None:
                shipment.notes = payload.notes.strip() if payload.notes else None

        record_status_change(
            self.db,
            entity_type="shipment",
            entity_id=shipment.id,
            from_status="draft",
            to_status="posted",
            reason=f"Shipment {shipment_no} officially posted and stock issued",
            changed_by=current_user_id,
            clock=self.clock,
        )

        # 8. Transition Sales Order status (Roadmap §V0.4 State Machine)
        all_shipped = all(si.quantity_shipped >= si.quantity for si in order.items)
        all_invoiced = all(si.quantity_invoiced >= si.quantity for si in order.items)
        any_shipped = any(si.quantity_shipped > Decimal("0.000") for si in order.items)

        if all_shipped and all_invoiced:
            target_status = "completed"
        elif all_shipped:
            target_status = "shipped"
        elif any_shipped:
            target_status = "partially_shipped"
        else:
            target_status = order.status

        if target_status != order.status:
            from_st = order.status
            order.status = target_status
            order.version += 1
            order.updated_by = current_user_id
            record_status_change(
                self.db,
                entity_type="sales_order",
                entity_id=order.id,
                from_status=from_st,
                to_status=target_status,
                reason=f"Order status transitioned to '{target_status}' on Shipment {shipment_no} posting",
                changed_by=current_user_id,
                clock=self.clock,
            )

        self.db.flush()
        return self._map_shipment_out(shipment)

    def cancel_shipment(self, shipment_id: int, current_user_id: int | None = None) -> ShipmentOut:
        shipment = self.get_shipment(shipment_id)
        if shipment.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft shipments can be cancelled. Current status: '{shipment.status}'. Posted shipments are immutable.",
            )

        from_status = shipment.status
        shipment.status = "cancelled"
        shipment.version += 1
        shipment.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="shipment",
            entity_id=shipment.id,
            from_status=from_status,
            to_status="cancelled",
            reason="Shipment cancelled by user",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_shipment_out(shipment)

    # ── Stock Adjustments ──────────────────────────────────────────────
    def _map_adjustment_out(self, a: StockAdjustment) -> StockAdjustmentOut:
        return StockAdjustmentOut(
            id=a.id,
            adjustment_no=a.adjustment_no,
            warehouse_id=a.warehouse_id,
            warehouse_code=a.warehouse.code if a.warehouse else "",
            warehouse_name=a.warehouse.name if a.warehouse else "",
            status=a.status,
            reason=a.reason,
            notes=a.notes,
            posted_at=a.posted_at,
            version=a.version,
            created_at=a.created_at,
            created_by=a.created_by,
            items=[
                StockAdjustmentItemOut(
                    id=it.id,
                    stock_adjustment_id=it.stock_adjustment_id,
                    product_id=it.product_id,
                    product_sku=it.product.sku if it.product else "",
                    product_name=it.product.name if it.product else "",
                    product_uom=it.product.uom if it.product else "",
                    quantity_change=it.quantity_change,
                    unit_cost=it.unit_cost,
                    created_at=it.created_at,
                )
                for it in a.items
            ],
        )

    def create_stock_adjustment(
        self, payload: StockAdjustmentCreatePayload, current_user_id: int | None = None
    ) -> StockAdjustmentOut:
        warehouse = self.get_warehouse(payload.warehouse_id)
        if not warehouse.is_active:
            raise BusinessRuleError(
                code="WAREHOUSE_INACTIVE",
                detail=f"Warehouse '{warehouse.name}' is inactive.",
            )

        seen_products: set[int] = set()
        items: list[StockAdjustmentItem] = []

        for it in payload.items:
            if it.product_id in seen_products:
                raise BusinessRuleError(
                    code="DUPLICATE_PRODUCT",
                    detail=f"Product ID {it.product_id} appears more than once in adjustment.",
                )
            seen_products.add(it.product_id)

            prod = self.db.get(Product, it.product_id)
            if not prod:
                raise NotFoundError(f"Product with ID {it.product_id} not found.")
            if prod.product_type != "stock":
                raise BusinessRuleError(
                    code="INVALID_PRODUCT_TYPE",
                    detail=f"Product '{prod.name}' is not a stock product.",
                )

            qty_change = round_qty(it.quantity_change)
            if qty_change == Decimal("0.000"):
                raise BusinessRuleError(
                    code="ZERO_QUANTITY_CHANGE",
                    detail="Adjustment item quantity change cannot be zero.",
                )

            unit_cost = None
            if qty_change > Decimal("0.000"):
                if it.unit_cost is None or it.unit_cost < Decimal("0.0000"):
                    raise BusinessRuleError(
                        code="MISSING_UNIT_COST",
                        detail=f"Positive adjustment for product '{prod.name}' requires a non-negative unit cost.",
                    )
                unit_cost = round_unit_price(it.unit_cost)

            items.append(
                StockAdjustmentItem(
                    product_id=prod.id,
                    quantity_change=qty_change,
                    unit_cost=unit_cost,
                )
            )

        adj = StockAdjustment(
            warehouse_id=warehouse.id,
            status="draft",
            reason=payload.reason,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            items=items,
        )
        self.db.add(adj)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="stock_adjustment",
            entity_id=adj.id,
            from_status=None,
            to_status="draft",
            reason=f"Draft stock adjustment created ({adj.reason})",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_adjustment_out(self.get_stock_adjustment(adj.id))

    def get_stock_adjustment(self, adjustment_id: int) -> StockAdjustment:
        stmt = (
            select(StockAdjustment)
            .options(
                joinedload(StockAdjustment.warehouse),
                joinedload(StockAdjustment.items).joinedload(StockAdjustmentItem.product),
            )
            .where(StockAdjustment.id == adjustment_id)
        )
        adj = self.db.execute(stmt).unique().scalar_one_or_none()
        if not adj:
            raise NotFoundError(f"Stock adjustment with ID {adjustment_id} not found.")
        return adj

    def list_stock_adjustments(
        self, warehouse_id: int | None = None, status: str | None = None
    ) -> list[StockAdjustmentOut]:
        stmt = (
            select(StockAdjustment)
            .options(
                joinedload(StockAdjustment.warehouse),
                joinedload(StockAdjustment.items).joinedload(StockAdjustmentItem.product),
            )
            .order_by(StockAdjustment.id.desc())
        )
        if warehouse_id is not None:
            stmt = stmt.where(StockAdjustment.warehouse_id == warehouse_id)
        if status is not None:
            stmt = stmt.where(StockAdjustment.status == status)

        adjustments = self.db.execute(stmt).unique().scalars().all()
        return [self._map_adjustment_out(a) for a in adjustments]

    def post_stock_adjustment(
        self, adjustment_id: int, current_user_id: int | None = None
    ) -> StockAdjustmentOut:
        adj = self.get_stock_adjustment(adjustment_id)
        if adj.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft adjustments can be posted. Current status: '{adj.status}'.",
            )

        now = self.clock.now()

        # Deadlock Avoidance: Sort product IDs strictly ascending
        sorted_pids = sorted({it.product_id for it in adj.items})
        balances_map: dict[int, InventoryBalance] = {}
        for pid in sorted_pids:
            bal_stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == adj.warehouse_id,
                )
                .with_for_update()
            )
            bal = self.db.execute(bal_stmt).scalar_one_or_none()
            if bal:
                balances_map[pid] = bal

        for item in adj.items:
            bal = balances_map.get(item.product_id)
            if item.quantity_change < Decimal("0.000"):
                # Negative adjustment: check that qty_on_hand does not fall below qty_reserved (Rule 6)
                abs_qty = abs(item.quantity_change)
                avail = (bal.qty_on_hand - bal.qty_reserved) if bal else Decimal("0.000")
                if not bal or avail < abs_qty:
                    reserved = bal.qty_reserved if bal else Decimal("0.000")
                    on_hand = bal.qty_on_hand if bal else Decimal("0.000")
                    prod_name = item.product.name if item.product else f"ID {item.product_id}"
                    raise BusinessRuleError(
                        code="ADJUSTMENT_EXCEEDS_AVAILABLE",
                        detail=(
                            f"Negative adjustment of {abs_qty} would drive on-hand ({on_hand}) "
                            f"below reserved stock ({reserved}) for product '{prod_name}'."
                        ),
                    )

                unit_cost = bal.avg_unit_cost
                total_cost = -round_money(abs_qty * unit_cost)
                bal.qty_on_hand -= abs_qty
                bal.updated_at = now

                txn = InventoryTransaction(
                    product_id=item.product_id,
                    warehouse_id=adj.warehouse_id,
                    txn_type="adjustment_out",
                    quantity=item.quantity_change,  # Signed negative
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    qty_on_hand_after=bal.qty_on_hand,
                    avg_cost_after=bal.avg_unit_cost,
                    source_type="stock_adjustment",
                    source_id=adj.id,
                    source_line_id=item.id,
                    occurred_at=now,
                    posted_by=current_user_id,
                    created_at=now,
                )
                self.db.add(txn)

            else:
                # Positive adjustment: recalculates WAC (Roadmap §V0.4 Costing)
                unit_cost_in = item.unit_cost or Decimal("0.0000")
                qty_in = item.quantity_change
                total_cost = round_money(qty_in * unit_cost_in)

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
                        warehouse_id=adj.warehouse_id,
                        qty_on_hand=qty_in,
                        qty_reserved=Decimal("0.000"),
                        avg_unit_cost=new_avg,
                        updated_at=now,
                    )
                    self.db.add(bal)
                    balances_map[item.product_id] = bal

                txn = InventoryTransaction(
                    product_id=item.product_id,
                    warehouse_id=adj.warehouse_id,
                    txn_type="adjustment_in",
                    quantity=qty_in,
                    unit_cost=unit_cost_in,
                    total_cost=total_cost,
                    qty_on_hand_after=bal.qty_on_hand,
                    avg_cost_after=bal.avg_unit_cost,
                    source_type="stock_adjustment",
                    source_id=adj.id,
                    source_line_id=item.id,
                    occurred_at=now,
                    posted_by=current_user_id,
                    created_at=now,
                )
                self.db.add(txn)

        adjustment_no = generate_next_number(self.db, "stock_adjustment", self.clock)
        adj.adjustment_no = adjustment_no
        adj.status = "posted"
        adj.posted_at = now
        adj.version += 1
        adj.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="stock_adjustment",
            entity_id=adj.id,
            from_status="draft",
            to_status="posted",
            reason=f"Stock adjustment {adjustment_no} officially posted",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_adjustment_out(adj)

    def cancel_stock_adjustment(
        self, adjustment_id: int, current_user_id: int | None = None
    ) -> StockAdjustmentOut:
        adj = self.get_stock_adjustment(adjustment_id)
        if adj.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft adjustments can be cancelled. Current status: '{adj.status}'.",
            )

        from_status = adj.status
        adj.status = "cancelled"
        adj.version += 1
        adj.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="stock_adjustment",
            entity_id=adj.id,
            from_status=from_status,
            to_status="cancelled",
            reason="Stock adjustment cancelled by user",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_adjustment_out(adj)

    # ── Stock Transfers ────────────────────────────────────────────────
    def _map_transfer_out(self, t: StockTransfer) -> StockTransferOut:
        return StockTransferOut(
            id=t.id,
            transfer_no=t.transfer_no,
            from_warehouse_id=t.from_warehouse_id,
            from_warehouse_code=t.from_warehouse.code if t.from_warehouse else "",
            from_warehouse_name=t.from_warehouse.name if t.from_warehouse else "",
            to_warehouse_id=t.to_warehouse_id,
            to_warehouse_code=t.to_warehouse.code if t.to_warehouse else "",
            to_warehouse_name=t.to_warehouse.name if t.to_warehouse else "",
            status=t.status,
            notes=t.notes,
            posted_at=t.posted_at,
            version=t.version,
            created_at=t.created_at,
            created_by=t.created_by,
            items=[
                StockTransferItemOut(
                    id=it.id,
                    stock_transfer_id=it.stock_transfer_id,
                    product_id=it.product_id,
                    product_sku=it.product.sku if it.product else "",
                    product_name=it.product.name if it.product else "",
                    product_uom=it.product.uom if it.product else "",
                    quantity=it.quantity,
                    unit_cost=it.unit_cost,
                    created_at=it.created_at,
                )
                for it in t.items
            ],
        )

    def create_stock_transfer(
        self, payload: StockTransferCreatePayload, current_user_id: int | None = None
    ) -> StockTransferOut:
        if payload.from_warehouse_id == payload.to_warehouse_id:
            raise BusinessRuleError(
                code="IDENTICAL_WAREHOUSES",
                detail="Source and destination warehouses must be different.",
            )

        from_wh = self.get_warehouse(payload.from_warehouse_id)
        to_wh = self.get_warehouse(payload.to_warehouse_id)
        if not from_wh.is_active or not to_wh.is_active:
            raise BusinessRuleError(
                code="WAREHOUSE_INACTIVE",
                detail="Both source and destination warehouses must be active.",
            )

        seen_products: set[int] = set()
        items: list[StockTransferItem] = []

        for it in payload.items:
            if it.product_id in seen_products:
                raise BusinessRuleError(
                    code="DUPLICATE_PRODUCT",
                    detail=f"Product ID {it.product_id} appears more than once in transfer.",
                )
            seen_products.add(it.product_id)

            prod = self.db.get(Product, it.product_id)
            if not prod:
                raise NotFoundError(f"Product with ID {it.product_id} not found.")
            if prod.product_type != "stock":
                raise BusinessRuleError(
                    code="INVALID_PRODUCT_TYPE",
                    detail=f"Product '{prod.name}' is not a stock product.",
                )

            qty = round_qty(it.quantity)
            if qty <= Decimal("0.000"):
                raise BusinessRuleError(
                    code="INVALID_TRANSFER_QUANTITY",
                    detail="Transfer item quantity must be strictly greater than zero.",
                )

            items.append(
                StockTransferItem(
                    product_id=prod.id,
                    quantity=qty,
                )
            )

        transfer = StockTransfer(
            from_warehouse_id=from_wh.id,
            to_warehouse_id=to_wh.id,
            status="draft",
            notes=payload.notes.strip() if payload.notes else None,
            created_by=current_user_id,
            updated_by=current_user_id,
            items=items,
        )
        self.db.add(transfer)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="stock_transfer",
            entity_id=transfer.id,
            from_status=None,
            to_status="draft",
            reason=f"Draft stock transfer created ({from_wh.code} -> {to_wh.code})",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_transfer_out(self.get_stock_transfer(transfer.id))

    def get_stock_transfer(self, transfer_id: int) -> StockTransfer:
        stmt = (
            select(StockTransfer)
            .options(
                joinedload(StockTransfer.from_warehouse),
                joinedload(StockTransfer.to_warehouse),
                joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
            )
            .where(StockTransfer.id == transfer_id)
        )
        transfer = self.db.execute(stmt).unique().scalar_one_or_none()
        if not transfer:
            raise NotFoundError(f"Stock transfer with ID {transfer_id} not found.")
        return transfer

    def list_stock_transfers(
        self, warehouse_id: int | None = None, status: str | None = None
    ) -> list[StockTransferOut]:
        stmt = (
            select(StockTransfer)
            .options(
                joinedload(StockTransfer.from_warehouse),
                joinedload(StockTransfer.to_warehouse),
                joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
            )
            .order_by(StockTransfer.id.desc())
        )
        if warehouse_id is not None:
            stmt = stmt.where(
                (StockTransfer.from_warehouse_id == warehouse_id)
                | (StockTransfer.to_warehouse_id == warehouse_id)
            )
        if status is not None:
            stmt = stmt.where(StockTransfer.status == status)

        transfers = self.db.execute(stmt).unique().scalars().all()
        return [self._map_transfer_out(t) for t in transfers]

    def post_stock_transfer(
        self, transfer_id: int, current_user_id: int | None = None
    ) -> StockTransferOut:
        transfer = self.get_stock_transfer(transfer_id)
        if transfer.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft transfers can be posted. Current status: '{transfer.status}'.",
            )

        now = self.clock.now()

        # Deadlock Avoidance across warehouses: Sort (product_id, warehouse_id) strictly ascending
        lock_keys = sorted(
            {
                (it.product_id, wid)
                for it in transfer.items
                for wid in (transfer.from_warehouse_id, transfer.to_warehouse_id)
            }
        )

        balances_map: dict[tuple[int, int], InventoryBalance] = {}
        for pid, wid in lock_keys:
            stmt = (
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == pid,
                    InventoryBalance.warehouse_id == wid,
                )
                .with_for_update()
            )
            bal = self.db.execute(stmt).scalar_one_or_none()
            if bal:
                balances_map[(pid, wid)] = bal

        for item in transfer.items:
            from_bal = balances_map.get((item.product_id, transfer.from_warehouse_id))
            avail = (from_bal.qty_on_hand - from_bal.qty_reserved) if from_bal else Decimal("0.000")
            prod_name = item.product.name if item.product else f"ID {item.product_id}"

            if not from_bal or avail < item.quantity:
                raise BusinessRuleError(
                    code="INSUFFICIENT_STOCK",
                    detail=(
                        f"Insufficient available stock for product '{prod_name}' in source warehouse "
                        f"'{transfer.from_warehouse.name}'. Required: {item.quantity}, Available: {avail}."
                    ),
                )

            # Costing: transfer_out at source avg -> transfer_in at same unit cost at destination
            source_unit_cost = from_bal.avg_unit_cost
            item.unit_cost = source_unit_cost

            # 1. Deduct from source warehouse
            from_bal.qty_on_hand -= item.quantity
            from_bal.updated_at = now

            txn_out = InventoryTransaction(
                product_id=item.product_id,
                warehouse_id=transfer.from_warehouse_id,
                txn_type="transfer_out",
                quantity=-item.quantity,  # Negative for issue/out
                unit_cost=source_unit_cost,
                total_cost=-round_money(item.quantity * source_unit_cost),
                qty_on_hand_after=from_bal.qty_on_hand,
                avg_cost_after=from_bal.avg_unit_cost,
                source_type="stock_transfer",
                source_id=transfer.id,
                source_line_id=item.id,
                occurred_at=now,
                posted_by=current_user_id,
                created_at=now,
            )
            self.db.add(txn_out)

            # 2. Add to destination warehouse & update WAC
            to_bal = balances_map.get((item.product_id, transfer.to_warehouse_id))
            if to_bal:
                new_avg = round_unit_price(
                    (to_bal.qty_on_hand * to_bal.avg_unit_cost + item.quantity * source_unit_cost)
                    / (to_bal.qty_on_hand + item.quantity)
                )
                to_bal.qty_on_hand += item.quantity
                to_bal.avg_unit_cost = new_avg
                to_bal.updated_at = now
            else:
                new_avg = source_unit_cost
                to_bal = InventoryBalance(
                    product_id=item.product_id,
                    warehouse_id=transfer.to_warehouse_id,
                    qty_on_hand=item.quantity,
                    qty_reserved=Decimal("0.000"),
                    avg_unit_cost=new_avg,
                    updated_at=now,
                )
                self.db.add(to_bal)
                balances_map[(item.product_id, transfer.to_warehouse_id)] = to_bal

            txn_in = InventoryTransaction(
                product_id=item.product_id,
                warehouse_id=transfer.to_warehouse_id,
                txn_type="transfer_in",
                quantity=item.quantity,
                unit_cost=source_unit_cost,
                total_cost=round_money(item.quantity * source_unit_cost),
                qty_on_hand_after=to_bal.qty_on_hand,
                avg_cost_after=to_bal.avg_unit_cost,
                source_type="stock_transfer",
                source_id=transfer.id,
                source_line_id=item.id,
                occurred_at=now,
                posted_by=current_user_id,
                created_at=now,
            )
            self.db.add(txn_in)

        transfer_no = generate_next_number(self.db, "stock_transfer", self.clock)
        transfer.transfer_no = transfer_no
        transfer.status = "posted"
        transfer.posted_at = now
        transfer.version += 1
        transfer.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="stock_transfer",
            entity_id=transfer.id,
            from_status="draft",
            to_status="posted",
            reason=f"Stock transfer {transfer_no} officially posted and executed",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_transfer_out(transfer)

    def cancel_stock_transfer(
        self, transfer_id: int, current_user_id: int | None = None
    ) -> StockTransferOut:
        transfer = self.get_stock_transfer(transfer_id)
        if transfer.status != "draft":
            raise BusinessRuleError(
                code="INVALID_TRANSITION",
                detail=f"Only draft transfers can be cancelled. Current status: '{transfer.status}'.",
            )

        from_status = transfer.status
        transfer.status = "cancelled"
        transfer.version += 1
        transfer.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="stock_transfer",
            entity_id=transfer.id,
            from_status=from_status,
            to_status="cancelled",
            reason="Stock transfer cancelled by user",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.flush()
        return self._map_transfer_out(transfer)
