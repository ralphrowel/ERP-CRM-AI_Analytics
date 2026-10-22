from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ── Warehouse Schemas ──────────────────────────────────────────────
class WarehouseCreatePayload(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    is_active: bool = True
    is_default: bool = False


class WarehouseUpdatePayload(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str | None
    is_active: bool
    is_default: bool
    version: int
    created_at: datetime
    updated_at: datetime


# ── Inventory Balance Schemas ──────────────────────────────────────
class InventoryBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    qty_on_hand: Decimal
    qty_reserved: Decimal
    qty_available: Decimal
    avg_unit_cost: Decimal
    total_value: Decimal
    reorder_point: Decimal | None
    is_below_reorder: bool
    updated_at: datetime


# ── Inventory Transaction Ledger Schemas ────────────────────────────
class InventoryTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_sku: str
    product_name: str
    warehouse_id: int
    warehouse_code: str
    txn_type: str
    quantity: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    qty_on_hand_after: Decimal
    avg_cost_after: Decimal
    source_type: str
    source_id: int | None
    source_line_id: int | None
    occurred_at: datetime
    posted_by: int | None
    created_at: datetime


# ── Opening Balance Entry Schemas ──────────────────────────────────
class OpeningBalanceItemPayload(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class OpeningBalancesCreatePayload(BaseModel):
    warehouse_id: int
    items: list[OpeningBalanceItemPayload] = Field(..., min_length=1)


# ── Stock Reservation Schemas ──────────────────────────────────────
class StockReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sales_order_item_id: int
    product_id: int
    product_sku: str
    product_name: str
    warehouse_id: int
    quantity: Decimal
    quantity_consumed: Decimal
    status: str
    created_at: datetime
    released_at: datetime | None


# ── Inventory Reconciliation Schemas ───────────────────────────────
class InventoryReconciliationItem(BaseModel):
    product_id: int
    product_sku: str
    product_name: str
    warehouse_id: int
    warehouse_code: str
    sum_ledger_qty: Decimal
    qty_on_hand: Decimal
    qty_discrepancy: Decimal
    avg_unit_cost: Decimal
    last_ledger_avg_cost: Decimal
    cost_discrepancy: Decimal
    is_reconciled: bool


class InventoryReconciliationOut(BaseModel):
    reconciled_at: datetime
    total_items_checked: int
    discrepant_count: int
    items: list[InventoryReconciliationItem]


# ── Shipment Schemas ───────────────────────────────────────────────
class ShipmentItemCreatePayload(BaseModel):
    sales_order_item_id: int
    quantity: Decimal = Field(..., gt=0)


class ShipmentCreatePayload(BaseModel):
    sales_order_id: int
    warehouse_id: int | None = None
    carrier: str | None = Field(None, max_length=100)
    tracking_no: str | None = Field(None, max_length=100)
    notes: str | None = None
    items: list[ShipmentItemCreatePayload] | None = None


class ShipmentPostPayload(BaseModel):
    carrier: str | None = Field(None, max_length=100)
    tracking_no: str | None = Field(None, max_length=100)
    notes: str | None = None


class ShipmentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_id: int
    sales_order_item_id: int
    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    quantity: Decimal
    unit_cost: Decimal | None
    cogs_amount: Decimal | None
    created_at: datetime


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_no: str | None
    sales_order_id: int
    sales_order_no: str
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    status: str
    shipped_at: datetime | None
    carrier: str | None
    tracking_no: str | None
    notes: str | None
    total_cogs: Decimal | None
    version: int
    created_at: datetime
    created_by: int | None
    items: list[ShipmentItemOut]


# ── Stock Adjustment Schemas ───────────────────────────────────────
class StockAdjustmentItemCreatePayload(BaseModel):
    product_id: int
    quantity_change: Decimal
    unit_cost: Decimal | None = None


class StockAdjustmentCreatePayload(BaseModel):
    warehouse_id: int
    reason: str = Field(..., pattern="^(count_correction|damage|loss|found|expired|other)$")
    notes: str | None = None
    items: list[StockAdjustmentItemCreatePayload] = Field(..., min_length=1)


class StockAdjustmentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_adjustment_id: int
    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    quantity_change: Decimal
    unit_cost: Decimal | None
    created_at: datetime


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    adjustment_no: str | None
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    status: str
    reason: str
    notes: str | None
    posted_at: datetime | None
    version: int
    created_at: datetime
    created_by: int | None
    items: list[StockAdjustmentItemOut]


# ── Stock Transfer Schemas ─────────────────────────────────────────
class StockTransferItemCreatePayload(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)


class StockTransferCreatePayload(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    notes: str | None = None
    items: list[StockTransferItemCreatePayload] = Field(..., min_length=1)


class StockTransferItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_transfer_id: int
    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    quantity: Decimal
    unit_cost: Decimal | None
    created_at: datetime


class StockTransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_no: str | None
    from_warehouse_id: int
    from_warehouse_code: str
    from_warehouse_name: str
    to_warehouse_id: int
    to_warehouse_code: str
    to_warehouse_name: str
    status: str
    notes: str | None
    approved_at: datetime | None = None
    approved_by: int | None = None
    dispatched_at: datetime | None = None
    dispatched_by: int | None = None
    received_at: datetime | None = None
    received_by: int | None = None
    posted_at: datetime | None
    version: int
    created_at: datetime
    created_by: int | None
    items: list[StockTransferItemOut]


# ── Warehouse Reorder Policy Schemas ───────────────────────────────
class WarehouseReorderPolicyCreatePayload(BaseModel):
    warehouse_id: int
    product_id: int
    min_qty: Decimal = Field(..., ge=0)
    max_qty: Decimal = Field(..., ge=0)
    reorder_quantity: Decimal | None = Field(None, gt=0)
    replenishment_source: str = Field("transfer", pattern="^(transfer|purchase)$")
    source_warehouse_id: int | None = None
    lead_time_days: int = Field(0, ge=0)
    is_active: bool = True


class WarehouseReorderPolicyUpdatePayload(BaseModel):
    min_qty: Decimal | None = Field(None, ge=0)
    max_qty: Decimal | None = Field(None, ge=0)
    reorder_quantity: Decimal | None = Field(None, gt=0)
    replenishment_source: str | None = Field(None, pattern="^(transfer|purchase)$")
    source_warehouse_id: int | None = None
    lead_time_days: int | None = Field(None, ge=0)
    is_active: bool | None = None


class WarehouseReorderPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    min_qty: Decimal
    max_qty: Decimal
    reorder_quantity: Decimal | None
    replenishment_source: str
    source_warehouse_id: int | None
    source_warehouse_code: str | None
    source_warehouse_name: str | None
    lead_time_days: int
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


# ── Replenishment Suggestion Schemas ───────────────────────────────
class ReplenishmentSuggestionOut(BaseModel):
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    product_id: int
    product_sku: str
    product_name: str
    product_uom: str
    qty_on_hand: Decimal
    qty_reserved: Decimal
    qty_available: Decimal
    min_qty: Decimal
    max_qty: Decimal
    deficit_qty: Decimal
    suggested_qty: Decimal
    replenishment_source: str
    source_warehouse_id: int | None
    source_warehouse_code: str | None
    source_warehouse_name: str | None
    source_qty_available: Decimal | None
    can_fulfill_transfer: bool
    urgency: str


class AutoGenerateTransfersPayload(BaseModel):
    warehouse_id: int | None = None
    product_ids: list[int] | None = None


class AutoGenerateTransfersResultOut(BaseModel):
    created_transfers_count: int
    transfer_ids: list[int]
    transfers: list[StockTransferOut]
    unfulfilled_suggestions_count: int
    unfulfilled_suggestions: list[ReplenishmentSuggestionOut]


class StockTransferDispatchPayload(BaseModel):
    notes: str | None = None


class StockTransferReceivePayload(BaseModel):
    notes: str | None = None
