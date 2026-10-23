from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.inventory.schemas import (
    ApplyPolicyTuningPayload,
    AutoGeneratePOsPayload,
    AutoGeneratePOsResultOut,
    AutoGenerateTransfersPayload,
    AutoGenerateTransfersResultOut,
    DemandForecastOut,
    InventoryBalanceOut,
    InventoryReconciliationOut,
    InventoryTransactionOut,
    OpeningBalancesCreatePayload,
    PolicyTuningRecommendationOut,
    ReplenishmentSuggestionOut,
    ShipmentCreatePayload,
    ShipmentOut,
    ShipmentPostPayload,
    StockAdjustmentCreatePayload,
    StockAdjustmentOut,
    StockTransferCreatePayload,
    StockTransferDispatchPayload,
    StockTransferOut,
    StockTransferReceivePayload,
    WarehouseCreatePayload,
    WarehouseOut,
    WarehouseReorderPolicyCreatePayload,
    WarehouseReorderPolicyOut,
    WarehouseReorderPolicyUpdatePayload,
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


@router.post("/stock-transfers/{transfer_id}/approve", response_model=StockTransferOut)
def approve_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.approve_stock_transfer(
        transfer_id=transfer_id, current_user_id=current_user.id
    )
    db.commit()
    return result


@router.post("/stock-transfers/{transfer_id}/dispatch", response_model=StockTransferOut)
def dispatch_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: StockTransferDispatchPayload | None = None,
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.dispatch_stock_transfer(
        transfer_id=transfer_id, payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result


@router.post("/stock-transfers/{transfer_id}/receive", response_model=StockTransferOut)
def receive_stock_transfer(
    transfer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: StockTransferReceivePayload | None = None,
) -> StockTransferOut:
    service = InventoryService(db)
    result = service.receive_stock_transfer(
        transfer_id=transfer_id, payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result


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


# ── Warehouse Reorder Policies Endpoints ────────────────────────────
@router.post(
    "/inventory/reorder-policies",
    response_model=WarehouseReorderPolicyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reorder_policy(
    payload: WarehouseReorderPolicyCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseReorderPolicyOut:
    service = InventoryService(db)
    result = service.create_reorder_policy(payload=payload, current_user_id=current_user.id)
    db.commit()
    return result


@router.get("/inventory/reorder-policies", response_model=list[WarehouseReorderPolicyOut])
def list_reorder_policies(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    product_id: int | None = Query(None, description="Filter by product ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
) -> list[WarehouseReorderPolicyOut]:
    service = InventoryService(db)
    return service.list_reorder_policies(
        warehouse_id=warehouse_id, product_id=product_id, is_active=is_active
    )


@router.get("/inventory/reorder-policies/{policy_id}", response_model=WarehouseReorderPolicyOut)
def get_reorder_policy(
    policy_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseReorderPolicyOut:
    service = InventoryService(db)
    return service._map_reorder_policy_out(service.get_reorder_policy(policy_id))


@router.put("/inventory/reorder-policies/{policy_id}", response_model=WarehouseReorderPolicyOut)
def update_reorder_policy(
    policy_id: int,
    payload: WarehouseReorderPolicyUpdatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseReorderPolicyOut:
    service = InventoryService(db)
    result = service.update_reorder_policy(
        policy_id=policy_id, payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result


@router.delete("/inventory/reorder-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reorder_policy(
    policy_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    service = InventoryService(db)
    service.delete_reorder_policy(policy_id)
    db.commit()


# ── Replenishment Suggestions & Auto-Generation Endpoints ───────────
@router.get(
    "/inventory/replenishment/suggestions",
    response_model=list[ReplenishmentSuggestionOut],
)
def get_replenishment_suggestions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by target warehouse ID"),
    urgency: str | None = Query(None, description="Filter by urgency: CRITICAL, HIGH, MEDIUM"),
) -> list[ReplenishmentSuggestionOut]:
    service = InventoryService(db)
    return service.evaluate_replenishment_suggestions(warehouse_id=warehouse_id, urgency=urgency)


@router.post(
    "/inventory/replenishment/auto-generate",
    response_model=AutoGenerateTransfersResultOut,
    status_code=status.HTTP_201_CREATED,
)
def auto_generate_replenishment_transfers(
    payload: AutoGenerateTransfersPayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AutoGenerateTransfersResultOut:
    service = InventoryService(db)
    result = service.auto_generate_replenishment_transfers(
        payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result


@router.post(
    "/inventory/replenishment/auto-generate-pos",
    response_model=AutoGeneratePOsResultOut,
    status_code=status.HTTP_201_CREATED,
)
def auto_generate_replenishment_pos(
    payload: AutoGeneratePOsPayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AutoGeneratePOsResultOut:
    service = InventoryService(db)
    result = service.auto_generate_replenishment_pos(
        payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result


# ── Milestone V3.3: Demand Forecasting & Policy Tuning Endpoints ────
@router.get(
    "/inventory/forecasting/demand",
    response_model=DemandForecastOut,
)
def get_demand_forecast(
    warehouse_id: int,
    product_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    horizon_days: int = Query(30, ge=1, le=365, description="Forecast horizon in days"),
    model: str = Query(
        "auto", description="Forecasting model: auto, holt_winters, holt_linear, croston, ses, sma"
    ),
    days_back: int = Query(90, ge=7, le=730, description="Historical lookback window in days"),
) -> DemandForecastOut:
    service = InventoryService(db)
    return service.forecast_product_demand(
        warehouse_id=warehouse_id,
        product_id=product_id,
        horizon_days=horizon_days,
        model=model,
        days_back=days_back,
    )


@router.get(
    "/inventory/forecasting/policy-recommendations",
    response_model=list[PolicyTuningRecommendationOut],
)
def get_policy_tuning_recommendations(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    warehouse_id: int | None = Query(None, description="Filter by warehouse ID"),
    product_id: int | None = Query(None, description="Filter by product ID"),
) -> list[PolicyTuningRecommendationOut]:
    service = InventoryService(db)
    prod_ids = [product_id] if product_id else None
    return service.recommend_policy_tuning(warehouse_id=warehouse_id, product_ids=prod_ids)


@router.post(
    "/inventory/reorder-policies/{policy_id}/apply-tuning",
    response_model=WarehouseReorderPolicyOut,
)
def apply_policy_tuning(
    policy_id: int,
    payload: ApplyPolicyTuningPayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WarehouseReorderPolicyOut:
    service = InventoryService(db)
    result = service.apply_policy_tuning(
        policy_id=policy_id, payload=payload, current_user_id=current_user.id
    )
    db.commit()
    return result
