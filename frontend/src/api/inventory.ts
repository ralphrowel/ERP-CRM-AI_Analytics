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
