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
  status: 'draft' | 'pending_approval' | 'sent' | 'partially_received' | 'received' | 'closed' | 'cancelled'
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

// ── Goods Receipts ───────────────────────────────────────────────────
export interface GoodsReceiptItemPayload {
  purchase_order_item_id: number
  quantity: number | string
}

export interface GoodsReceiptCreatePayload {
  purchase_order_id: number
  supplier_delivery_ref?: string
  notes?: string
  items: GoodsReceiptItemPayload[]
}

export interface GoodsReceiptItem {
  id: number
  goods_receipt_id: number
  purchase_order_item_id: number
  product_id: number
  product_name?: string | null
  product_sku?: string | null
  quantity: string | number
  unit_cost: string | number
}

export interface GoodsReceipt {
  id: number
  gr_no: string
  purchase_order_id: number
  po_no?: string | null
  warehouse_id: number
  warehouse_code?: string | null
  warehouse_name?: string | null
  status: 'draft' | 'posted' | 'cancelled'
  received_at?: string | null
  supplier_delivery_ref?: string | null
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
  created_by?: number | null
  items: GoodsReceiptItem[]
}

export interface PaginatedGoodsReceipts {
  items: GoodsReceipt[]
  total: number
  page: number
  page_size: number
}

// ── Supplier Invoices (Bills) ─────────────────────────────────────────
export interface SupplierInvoiceItemPayload {
  purchase_order_item_id: number
  quantity: number | string
  unit_cost: number | string
}

export interface SupplierInvoiceCreatePayload {
  purchase_order_id: number
  supplier_invoice_ref: string
  invoice_date?: string
  due_date?: string
  notes?: string
  items: SupplierInvoiceItemPayload[]
}

export interface SupplierInvoiceItem {
  id: number
  supplier_invoice_id: number
  purchase_order_item_id: number
  product_id: number
  product_name?: string | null
  product_sku?: string | null
  line_no: number
  description: string
  uom: string
  quantity: string | number
  unit_cost: string | number
  tax_rate_id: number
  tax_rate: string | number
  line_net: string | number
  line_tax: string | number
  line_total: string | number
}

export interface SupplierInvoice {
  id: number
  bill_no: string
  supplier_id: number
  supplier_name?: string | null
  purchase_order_id: number
  po_no?: string | null
  supplier_invoice_ref: string
  status: 'draft' | 'matched' | 'exception' | 'approved' | 'partially_paid' | 'paid' | 'void'
  invoice_date: string
  due_date: string
  subtotal: string | number
  tax_total: string | number
  grand_total: string | number
  amount_paid: string | number
  balance_due: string | number
  match_notes?: string | null
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
  items: SupplierInvoiceItem[]
}

export interface PaginatedSupplierInvoices {
  items: SupplierInvoice[]
  total: number
  page: number
  page_size: number
}

// ── Supplier Payments & Allocations ──────────────────────────────────
export interface SupplierPaymentAllocationItem {
  supplier_invoice_id: number
  amount: number | string
}

export interface SupplierPaymentCreatePayload {
  supplier_id: number
  payment_date?: string
  payment_method?: string
  reference_no?: string
  amount: number | string
  notes?: string
  allocations?: SupplierPaymentAllocationItem[]
}

export interface SupplierPaymentAllocation {
  id: number
  supplier_payment_id: number
  supplier_invoice_id: number
  bill_no?: string | null
  supplier_invoice_ref?: string | null
  amount: string | number
  allocated_at: string
}

export interface SupplierPayment {
  id: number
  payment_no: string
  supplier_id: number
  supplier_name?: string | null
  payment_date: string
  payment_method: string
  reference_no?: string | null
  amount: string | number
  amount_allocated: string | number
  status: 'posted' | 'void'
  void_reason?: string | null
  voided_at?: string | null
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
  allocations: SupplierPaymentAllocation[]
}

export interface PaginatedSupplierPayments {
  items: SupplierPayment[]
  total: number
  page: number
  page_size: number
}

// ── Supplier Statement ────────────────────────────────────────────────
export interface SupplierStatementBillItem {
  id: number
  bill_no: string
  supplier_invoice_ref: string
  invoice_date: string
  due_date: string
  grand_total: string | number
  amount_paid: string | number
  balance_due: string | number
  status: string
}

export interface SupplierStatementPaymentItem {
  id: number
  payment_no: string
  payment_date: string
  payment_method: string
  reference_no?: string | null
  amount: string | number
  amount_allocated: string | number
  status: string
}

export interface SupplierStatement {
  supplier_id: number
  supplier_no: string
  supplier_name: string
  bills: SupplierStatementBillItem[]
  payments: SupplierStatementPaymentItem[]
  total_billed: string | number
  total_paid: string | number
  total_outstanding: string | number
}

// ── API Clients ───────────────────────────────────────────────────────
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

  getStatement: (supplierId: number) =>
    api.get<SupplierStatement>(`/api/v1/purchasing/suppliers/${supplierId}/statement`),
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

export const goodsReceiptsApi = {
  list: (params?: {
    purchase_order_id?: number
    warehouse_id?: number
    status?: string
    page?: number
    page_size?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.purchase_order_id) query.append('purchase_order_id', String(params.purchase_order_id))
    if (params?.warehouse_id) query.append('warehouse_id', String(params.warehouse_id))
    if (params?.status) query.append('status', params.status)
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    const qs = query.toString()
    return api.get<PaginatedGoodsReceipts>(`/api/v1/purchasing/goods-receipts${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<GoodsReceipt>(`/api/v1/purchasing/goods-receipts/${id}`),

  create: (data: GoodsReceiptCreatePayload) =>
    api.post<GoodsReceipt>('/api/v1/purchasing/goods-receipts', data),

  post: (id: number) =>
    api.post<GoodsReceipt>(`/api/v1/purchasing/goods-receipts/${id}/post`),

  cancel: (id: number) =>
    api.post<GoodsReceipt>(`/api/v1/purchasing/goods-receipts/${id}/cancel`),
}

export const supplierInvoicesApi = {
  list: (params?: {
    supplier_id?: number
    purchase_order_id?: number
    status?: string
    page?: number
    page_size?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.supplier_id) query.append('supplier_id', String(params.supplier_id))
    if (params?.purchase_order_id) query.append('purchase_order_id', String(params.purchase_order_id))
    if (params?.status) query.append('status', params.status)
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    const qs = query.toString()
    return api.get<PaginatedSupplierInvoices>(`/api/v1/purchasing/supplier-invoices${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<SupplierInvoice>(`/api/v1/purchasing/supplier-invoices/${id}`),

  create: (data: SupplierInvoiceCreatePayload) =>
    api.post<SupplierInvoice>('/api/v1/purchasing/supplier-invoices', data),

  approve: (id: number) =>
    api.post<SupplierInvoice>(`/api/v1/purchasing/supplier-invoices/${id}/approve`),

  void: (id: number, reason: string) =>
    api.post<SupplierInvoice>(`/api/v1/purchasing/supplier-invoices/${id}/void`, { reason }),
}

export const supplierPaymentsApi = {
  list: (params?: {
    supplier_id?: number
    status?: string
    page?: number
    page_size?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.supplier_id) query.append('supplier_id', String(params.supplier_id))
    if (params?.status) query.append('status', params.status)
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    const qs = query.toString()
    return api.get<PaginatedSupplierPayments>(`/api/v1/purchasing/supplier-payments${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<SupplierPayment>(`/api/v1/purchasing/supplier-payments/${id}`),

  create: (data: SupplierPaymentCreatePayload) =>
    api.post<SupplierPayment>('/api/v1/purchasing/supplier-payments', data),

  void: (id: number, reason: string) =>
    api.post<SupplierPayment>(`/api/v1/purchasing/supplier-payments/${id}/void`, { reason }),
}
