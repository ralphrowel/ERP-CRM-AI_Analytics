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
) -> InventoryReconciliationOut:
    service = InventoryService(db)
    return service.get_inventory_reconciliation()
