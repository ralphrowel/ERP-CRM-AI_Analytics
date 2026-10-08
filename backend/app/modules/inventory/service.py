from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, get_clock
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.money import round_money, round_qty, round_unit_price
from app.modules.catalog.models import Product
from app.modules.inventory.models import (
    InventoryBalance,
    InventoryTransaction,
    StockReservation,
    Warehouse,
)
from app.modules.inventory.schemas import (
    InventoryBalanceOut,
    InventoryReconciliationItem,
    InventoryReconciliationOut,
    InventoryTransactionOut,
    OpeningBalancesCreatePayload,
    WarehouseCreatePayload,
    WarehouseOut,
    WarehouseUpdatePayload,
)
from app.modules.sales.models import SalesOrder, SalesOrderItem


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
