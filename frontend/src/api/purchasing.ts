import { api } from './client'

export interface SupplierProduct {
  supplier_id: number
  product_id: number
  product_name?: string | null
  product_sku?: string | null
  product_uom?: string | null
  supplier_sku?: string | null
  last_unit_cost?: string | number | null
  lead_time_days?: number | null
  is_preferred: boolean
}

export interface Supplier {
  id: number
  supplier_no: string
  name: string
  tin?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
  payment_terms_days: number
  is_active: boolean
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
  created_by?: number | null
  updated_by?: number | null
  products: SupplierProduct[]
}

export interface PaginatedSuppliers {
  items: Supplier[]
  total: number
  page: number
  page_size: number
}

export interface SupplierCreatePayload {
  supplier_no?: string
  name: string
  tin?: string
  email?: string
  phone?: string
  address?: string
  payment_terms_days?: number
  is_active?: boolean
  notes?: string
}

export interface SupplierUpdatePayload {
  name?: string
  tin?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
  payment_terms_days?: number
  is_active?: boolean
  notes?: string | null
  version: number
}

export interface SupplierProductCreatePayload {
  product_id: number
  supplier_sku?: string
  last_unit_cost?: number | string
  lead_time_days?: number
  is_preferred?: boolean
}

export interface PurchaseOrderItemPayload {
  product_id: number
  description?: string
  uom?: string
  quantity: number | string
  unit_cost: number | string
  tax_rate_id: number
}

export interface PurchaseOrderItem {
  id: number
  purchase_order_id: number
  line_no: number
  product_id: number
  product_name?: string | null
  product_sku?: string | null
  description: string
  uom: string
  quantity: string | number
  unit_cost: string | number
  tax_rate_id: number
  tax_rate: string | number
  line_net: string | number
  line_tax: string | number
  line_total: string | number
  quantity_received: string | number
  quantity_billed: string | number
}

export interface PurchaseOrder {
  id: number
  po_no: string
  supplier_id: number
  supplier_name?: string | null
  warehouse_id: number
  warehouse_code?: string | null
  warehouse_name?: string | null
  status: 'draft' | 'sent' | 'partially_received' | 'received' | 'closed' | 'cancelled'
  order_date: string
  expected_date?: string | null
  notes?: string | null
  payment_terms_days_snapshot: number
  supplier_address_snapshot?: string | null
  warehouse_address_snapshot?: string | null
  subtotal: string | number
  tax_total: string | number
  grand_total: string | number
  version: number
  created_at: string
  updated_at: string
  created_by?: number | null
  updated_by?: number | null
  items: PurchaseOrderItem[]
}

export interface PaginatedPurchaseOrders {
  items: PurchaseOrder[]
  total: number
  page: number
  page_size: number
}

export interface PurchaseOrderCreatePayload {
  supplier_id: number
  warehouse_id: number
  order_date?: string
  expected_date?: string
  notes?: string
  items: PurchaseOrderItemPayload[]
}

export interface PurchaseOrderUpdatePayload {
  warehouse_id?: number
  order_date?: string
  expected_date?: string
  notes?: string
  items?: PurchaseOrderItemPayload[]
  version: number
}

export const suppliersApi = {
  list: (params?: { search?: string; is_active?: boolean; page?: number; page_size?: number }) => {
    const query = new URLSearchParams()
    if (params?.search) query.append('search', params.search)
    if (params?.is_active !== undefined) query.append('is_active', String(params.is_active))
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    const qs = query.toString()
    return api.get<PaginatedSuppliers>(`/api/v1/purchasing/suppliers${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<Supplier>(`/api/v1/purchasing/suppliers/${id}`),

  create: (data: SupplierCreatePayload) => api.post<Supplier>('/api/v1/purchasing/suppliers', data),

  update: (id: number, data: SupplierUpdatePayload) =>
    api.put<Supplier>(`/api/v1/purchasing/suppliers/${id}`, data),

  listProducts: (supplierId: number) =>
    api.get<SupplierProduct[]>(`/api/v1/purchasing/suppliers/${supplierId}/products`),

  addProduct: (supplierId: number, data: SupplierProductCreatePayload) =>
    api.post<SupplierProduct>(`/api/v1/purchasing/suppliers/${supplierId}/products`, data),

  removeProduct: (supplierId: number, productId: number) =>
    api.delete<void>(`/api/v1/purchasing/suppliers/${supplierId}/products/${productId}`),
}

export const purchaseOrdersApi = {
  list: (params?: {
    supplier_id?: number
    warehouse_id?: number
    status?: string
    page?: number
    page_size?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.supplier_id) query.append('supplier_id', String(params.supplier_id))
    if (params?.warehouse_id) query.append('warehouse_id', String(params.warehouse_id))
    if (params?.status) query.append('status', params.status)
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    const qs = query.toString()
    return api.get<PaginatedPurchaseOrders>(`/api/v1/purchasing/purchase-orders${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<PurchaseOrder>(`/api/v1/purchasing/purchase-orders/${id}`),

  create: (data: PurchaseOrderCreatePayload) =>
    api.post<PurchaseOrder>('/api/v1/purchasing/purchase-orders', data),

  update: (id: number, data: PurchaseOrderUpdatePayload) =>
    api.put<PurchaseOrder>(`/api/v1/purchasing/purchase-orders/${id}`, data),

  send: (id: number) =>
    api.post<PurchaseOrder>(`/api/v1/purchasing/purchase-orders/${id}/send`),

  cancel: (id: number) =>
    api.post<PurchaseOrder>(`/api/v1/purchasing/purchase-orders/${id}/cancel`),

  close: (id: number, reason: string) =>
    api.post<PurchaseOrder>(`/api/v1/purchasing/purchase-orders/${id}/close`, { reason }),
}
