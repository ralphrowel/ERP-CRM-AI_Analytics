import { api } from './client'

export interface Warehouse {
  id: number
  code: string
  name: string
  address?: string | null
  is_active: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface WarehouseCreatePayload {
  code: string
  name: string
  address?: string
  is_active?: boolean
  is_default?: boolean
}

export interface WarehouseUpdatePayload {
  name?: string
  address?: string
  is_active?: boolean
  is_default?: boolean
}

export interface InventoryBalance {
  product_id: number
  warehouse_id: number
  qty_on_hand: string
  qty_reserved: string
  qty_available: string
  avg_unit_cost: string
  total_stock_value: string
  reorder_point: string
  product_name: string
  product_sku: string
  warehouse_name: string
  warehouse_code: string
  uom: string
  updated_at: string
}

export interface InventoryTransaction {
  id: number
  product_id: number
  warehouse_id: number
  txn_type: 'opening_balance' | 'reservation' | 'reservation_release' | 'issue' | 'receipt' | 'adjustment'
  quantity: string
  unit_cost: string
  total_cost: string
  qty_on_hand_after: string
  avg_cost_after: string
  source_type: string
  source_id?: number | null
  notes?: string | null
  created_by_user_id?: number | null
  created_at: string
  product_name: string
  product_sku: string
  warehouse_name: string
}

export interface OpeningBalanceItemPayload {
  product_id: number
  quantity: string
  unit_cost: string
}

export interface OpeningBalancesCreatePayload {
  warehouse_id: number
  items: OpeningBalanceItemPayload[]
}

export interface InventoryReconciliationItem {
  product_id: number
  warehouse_id: number
  product_sku: string
  product_name: string
  warehouse_name: string
  balance_on_hand: string
  ledger_sum_quantity: string
  quantity_variance: string
  balance_avg_cost: string
  latest_ledger_unit_cost: string
  is_reconciled: boolean
}

export interface InventoryReconciliationOut {
  items: InventoryReconciliationItem[]
  total_checked: number
  total_reconciled: number
  total_discrepancies: number
}

export const warehousesApi = {
  list: (activeOnly: boolean = false) => {
    const query = activeOnly ? '?active_only=true' : ''
    return api.get<Warehouse[]>(`/warehouses${query}`)
  },
  create: (payload: WarehouseCreatePayload) => api.post<Warehouse>('/warehouses', payload),
  update: (id: number, payload: WarehouseUpdatePayload) =>
    api.put<Warehouse>(`/warehouses/${id}`, payload),
}

export const inventoryApi = {
  listBalances: (params: { warehouse_id?: number; product_id?: number; below_reorder?: boolean } = {}) => {
    const query = new URLSearchParams()
    if (params.warehouse_id) query.set('warehouse_id', params.warehouse_id.toString())
    if (params.product_id) query.set('product_id', params.product_id.toString())
    if (params.below_reorder !== undefined && params.below_reorder !== null) {
      query.set('below_reorder', params.below_reorder ? 'true' : 'false')
    }
    const qStr = query.toString()
    return api.get<InventoryBalance[]>(`/inventory/balances${qStr ? `?${qStr}` : ''}`)
  },
  listTransactions: (params: { warehouse_id?: number; product_id?: number; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.warehouse_id) query.set('warehouse_id', params.warehouse_id.toString())
    if (params.product_id) query.set('product_id', params.product_id.toString())
    if (params.limit) query.set('limit', params.limit.toString())
    const qStr = query.toString()
    return api.get<InventoryTransaction[]>(`/inventory/transactions${qStr ? `?${qStr}` : ''}`)
  },
  postOpeningBalances: (payload: OpeningBalancesCreatePayload) =>
    api.post<InventoryBalance[]>('/inventory/opening-balances', payload),
  getReconciliation: () => api.get<InventoryReconciliationOut>('/inventory/reconciliation'),
}

// ── Shipment Types & API ───────────────────────────────────────────
export interface ShipmentItem {
  id: number
  shipment_id: number
  sales_order_item_id: number
  product_id: number
  product_sku: string
  product_name: string
  product_uom: string
  quantity: string
  unit_cost?: string | null
  cogs_amount?: string | null
  created_at: string
}

export interface Shipment {
  id: number
  shipment_no?: string | null
  sales_order_id: number
  sales_order_no: string
  warehouse_id: number
  warehouse_code: string
  warehouse_name: string
  status: 'draft' | 'posted' | 'cancelled'
  shipped_at?: string | null
  carrier?: string | null
  tracking_no?: string | null
  notes?: string | null
  total_cogs?: string | null
  version: number
  created_at: string
  created_by?: number | null
  items: ShipmentItem[]
}

export interface ShipmentItemCreatePayload {
  sales_order_item_id: number
  quantity: number | string
}

export interface ShipmentCreatePayload {
  sales_order_id: number
  warehouse_id?: number | null
  carrier?: string
  tracking_no?: string
  notes?: string
  items?: ShipmentItemCreatePayload[]
}

export interface ShipmentPostPayload {
  carrier?: string
  tracking_no?: string
  notes?: string
}

export const shipmentsApi = {
  list: (params: { warehouse_id?: number; sales_order_id?: number; status?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.warehouse_id) query.set('warehouse_id', params.warehouse_id.toString())
    if (params.sales_order_id) query.set('sales_order_id', params.sales_order_id.toString())
    if (params.status) query.set('status', params.status)
    const qStr = query.toString()
    return api.get<Shipment[]>(`/shipments${qStr ? `?${qStr}` : ''}`)
  },
  get: (id: number) => api.get<Shipment>(`/shipments/${id}`),
  create: (payload: ShipmentCreatePayload) => api.post<Shipment>('/shipments', payload),
  post: (id: number, payload?: ShipmentPostPayload) =>
    api.post<Shipment>(`/shipments/${id}/post`, payload || {}),
  cancel: (id: number) => api.post<Shipment>(`/shipments/${id}/cancel`, {}),
}

// ── Stock Adjustments Types & API ──────────────────────────────────
export interface StockAdjustmentItem {
  id: number
  stock_adjustment_id: number
  product_id: number
  product_sku: string
  product_name: string
  product_uom: string
  quantity_change: string
  unit_cost?: string | null
  created_at: string
}

export interface StockAdjustment {
  id: number
  adjustment_no?: string | null
  warehouse_id: number
  warehouse_code: string
  warehouse_name: string
  status: 'draft' | 'posted' | 'cancelled'
  reason: 'count_correction' | 'damage' | 'loss' | 'found' | 'expired' | 'other'
  notes?: string | null
  posted_at?: string | null
  version: number
  created_at: string
  created_by?: number | null
  items: StockAdjustmentItem[]
}

export interface StockAdjustmentItemCreatePayload {
  product_id: number
  quantity_change: number | string
  unit_cost?: number | string | null
}

export interface StockAdjustmentCreatePayload {
  warehouse_id: number
  reason: string
  notes?: string
  items: StockAdjustmentItemCreatePayload[]
}

export const stockAdjustmentsApi = {
  list: (params: { warehouse_id?: number; status?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.warehouse_id) query.set('warehouse_id', params.warehouse_id.toString())
    if (params.status) query.set('status', params.status)
    const qStr = query.toString()
    return api.get<StockAdjustment[]>(`/stock-adjustments${qStr ? `?${qStr}` : ''}`)
  },
  get: (id: number) => api.get<StockAdjustment>(`/stock-adjustments/${id}`),
  create: (payload: StockAdjustmentCreatePayload) =>
    api.post<StockAdjustment>('/stock-adjustments', payload),
  post: (id: number) => api.post<StockAdjustment>(`/stock-adjustments/${id}/post`, {}),
  cancel: (id: number) => api.post<StockAdjustment>(`/stock-adjustments/${id}/cancel`, {}),
}

// ── Stock Transfers Types & API ────────────────────────────────────
export interface StockTransferItem {
  id: number
  stock_transfer_id: number
  product_id: number
  product_sku: string
  product_name: string
  product_uom: string
  quantity: string
  unit_cost?: string | null
  created_at: string
}

export interface StockTransfer {
  id: number
  transfer_no?: string | null
  from_warehouse_id: number
  from_warehouse_code: string
  from_warehouse_name: string
  to_warehouse_id: number
  to_warehouse_code: string
  to_warehouse_name: string
  status: 'draft' | 'posted' | 'cancelled'
  notes?: string | null
  posted_at?: string | null
  version: number
  created_at: string
  created_by?: number | null
  items: StockTransferItem[]
}

export interface StockTransferItemCreatePayload {
  product_id: number
  quantity: number | string
}

export interface StockTransferCreatePayload {
  from_warehouse_id: number
  to_warehouse_id: number
  notes?: string
  items: StockTransferItemCreatePayload[]
}

export const stockTransfersApi = {
  list: (params: { warehouse_id?: number; status?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.warehouse_id) query.set('warehouse_id', params.warehouse_id.toString())
    if (params.status) query.set('status', params.status)
    const qStr = query.toString()
    return api.get<StockTransfer[]>(`/stock-transfers${qStr ? `?${qStr}` : ''}`)
  },
  get: (id: number) => api.get<StockTransfer>(`/stock-transfers/${id}`),
  create: (payload: StockTransferCreatePayload) =>
    api.post<StockTransfer>('/stock-transfers', payload),
  post: (id: number) => api.post<StockTransfer>(`/stock-transfers/${id}/post`, {}),
  cancel: (id: number) => api.post<StockTransfer>(`/stock-transfers/${id}/cancel`, {}),
}
