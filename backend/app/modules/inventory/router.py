from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.inventory.schemas import (
    InventoryBalanceOut,
    InventoryReconciliationOut,
    InventoryTransactionOut,
    OpeningBalancesCreatePayload,
    ShipmentCreatePayload,
    ShipmentOut,
    ShipmentPostPayload,
    StockAdjustmentCreatePayload,
    StockAdjustmentOut,
    StockTransferCreatePayload,
    StockTransferOut,
    WarehouseCreatePayload,
    WarehouseOut,
    WarehouseUpdatePayload,
)
from app.modules.inventory.service import InventoryService

router = APIRouter(tags=["inventory"])


# ── Warehouses Endpoints ───────────────────────────────────────────
@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    active_only: bool = Query(False, description="Filter only active warehouses"),
) -> list[WarehouseOut]:
    service = InventoryService(db)
    return service.list_warehouses(active_only=active_only)


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseOut:
    service = InventoryService(db)
    result = service.create_warehouse(payload)
    db.commit()
    return result


@router.put("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseOut:
    service = InventoryService(db)
    result = service.update_warehouse(warehouse_id, payload)
    db.commit()
    return result


# ── Inventory Balances & Ledger Endpoints ───────────────────────────
@router.get("/inventory/balances", response_model=list[InventoryBalanceOut])
def list_inventory_balances(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    product_id: int | None = Query(None, description="Filter by product ID"),
    below_reorder: bool | None = Query(None, description="Filter items below reorder point"),
) -> list[InventoryBalanceOut]:
    service = InventoryService(db)
    return service.list_inventory_balances(
        warehouse_id=warehouse_id,
        product_id=product_id,
        below_reorder=below_reorder,
    )


@router.get("/inventory/transactions", response_model=list[InventoryTransactionOut])
def list_inventory_transactions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    product_id: int | None = Query(None, description="Filter by product ID"),
    limit: int = Query(100, ge=1, le=500, description="Max transactions to return"),
) -> list[InventoryTransactionOut]:
    service = InventoryService(db)
    return service.list_inventory_transactions(
        warehouse_id=warehouse_id,
        product_id=product_id,
        limit=limit,
    )


@router.post(
    "/inventory/opening-balances",
    response_model=list[InventoryBalanceOut],
    status_code=status.HTTP_201_CREATED,
)
def post_opening_balances(
    payload: OpeningBalancesCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[InventoryBalanceOut]:
    service = InventoryService(db)
    result = service.post_opening_balances(payload, user_id=current_user.id)
    db.commit()
    return result


@router.get("/inventory/reconciliation", response_model=InventoryReconciliationOut)
def get_inventory_reconciliation(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    service = InventoryService(db)
    return service.get_inventory_reconciliation()


# ── Shipments Endpoints ─────────────────────────────────────────────
@router.post("/shipments", response_model=ShipmentOut, status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShipmentOut:
    service = InventoryService(db)
    result = service.create_shipment(payload, current_user_id=current_user.id)
    db.commit()
    return result


@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    sales_order_id: int | None = Query(None, description="Filter by sales order ID"),
    status: str | None = Query(None, description="Filter by shipment status"),
) -> list[ShipmentOut]:
    service = InventoryService(db)
    return service.list_shipments(
        warehouse_id=warehouse_id,
        sales_order_id=sales_order_id,
        status=status,
    )


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShipmentOut:
    service = InventoryService(db)
    return service._map_shipment_out(service.get_shipment(shipment_id))


@router.post("/shipments/{shipment_id}/post", response_model=ShipmentOut)
def post_shipment(
    shipment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: ShipmentPostPayload | None = None,
) -> ShipmentOut:
    service = InventoryService(db)
    result = service.post_shipment(
        shipment_id=shipment_id,
        payload=payload,
        current_user_id=current_user.id,
    )
    db.commit()
    return result


@router.post("/shipments/{shipment_id}/cancel", response_model=ShipmentOut)
def cancel_shipment(
    shipment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShipmentOut:
    service = InventoryService(db)
    result = service.cancel_shipment(
        shipment_id=shipment_id,
        current_user_id=current_user.id,
    )
    db.commit()
    return result


# ── Stock Adjustments Endpoints ─────────────────────────────────────
@router.post(
    "/stock-adjustments", response_model=StockAdjustmentOut, status_code=status.HTTP_201_CREATED
)
def create_stock_adjustment(
    payload: StockAdjustmentCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockAdjustmentOut:
    service = InventoryService(db)
    result = service.create_stock_adjustment(payload, current_user_id=current_user.id)
    db.commit()
    return result


@router.get("/stock-adjustments", response_model=list[StockAdjustmentOut])
def list_stock_adjustments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    status: str | None = Query(None, description="Filter by adjustment status"),
) -> list[StockAdjustmentOut]:
    service = InventoryService(db)
    return service.list_stock_adjustments(warehouse_id=warehouse_id, status=status)


@router.get("/stock-adjustments/{adjustment_id}", response_model=StockAdjustmentOut)
def get_stock_adjustment(
    adjustment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockAdjustmentOut:
    service = InventoryService(db)
    return service._map_adjustment_out(service.get_stock_adjustment(adjustment_id))


@router.post("/stock-adjustments/{adjustment_id}/post", response_model=StockAdjustmentOut)
def post_stock_adjustment(
    adjustment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockAdjustmentOut:
    service = InventoryService(db)
    result = service.post_stock_adjustment(
        adjustment_id=adjustment_id, current_user_id=current_user.id
    )
    db.commit()
    return result


@router.post("/stock-adjustments/{adjustment_id}/cancel", response_model=StockAdjustmentOut)
def cancel_stock_adjustment(
    adjustment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockAdjustmentOut:
    service = InventoryService(db)
    result = service.cancel_stock_adjustment(
        adjustment_id=adjustment_id, current_user_id=current_user.id
    )
    db.commit()
    return result


# ── Stock Transfers Endpoints ───────────────────────────────────────
@router.post(
    "/stock-transfers", response_model=StockTransferOut, status_code=status.HTTP_201_CREATED
)
def create_stock_transfer(
    payload: StockTransferCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.create_stock_transfer(payload, current_user_id=current_user.id)
    db.commit()
    return result


@router.get("/stock-transfers", response_model=list[StockTransferOut])
def list_stock_transfers(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    status: str | None = Query(None, description="Filter by transfer status"),
) -> list[StockTransferOut]:
    service = InventoryService(db)
    return service.list_stock_transfers(warehouse_id=warehouse_id, status=status)


@router.get("/stock-transfers/{transfer_id}", response_model=StockTransferOut)
def get_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockTransferOut:
    service = InventoryService(db)
    return service._map_transfer_out(service.get_stock_transfer(transfer_id))


@router.post("/stock-transfers/{transfer_id}/post", response_model=StockTransferOut)
def post_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.post_stock_transfer(transfer_id=transfer_id, current_user_id=current_user.id)
    db.commit()
    return result


@router.post("/stock-transfers/{transfer_id}/cancel", response_model=StockTransferOut)
def cancel_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.cancel_stock_transfer(transfer_id=transfer_id, current_user_id=current_user.id)
    db.commit()
    return result
