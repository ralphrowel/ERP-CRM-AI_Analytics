import { api } from './client'

export interface TaxRate {
  id: number
  code: string
  name: string
  rate: string
  is_default: boolean
  is_active: boolean
}

export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired' | 'cancelled'
export type SalesOrderStatus =
  | 'draft'
  | 'confirmed'
  | 'on_hold'
  | 'partially_shipped'
  | 'shipped'
  | 'completed'
  | 'cancelled'

export interface LineItem {
  id?: number
  line_no: number
  product_id?: number | null
  description: string
  uom: string
  quantity: string
  unit_price: string
  discount_amount: string
  tax_rate_id: number
  tax_rate: string
  line_net: string
  line_tax: string
  line_total: string
}

export interface SalesOrderItem extends LineItem {
  quantity_invoiced: string
  quantity_shipped: string
}

export interface LineItemPayload {
  product_id?: number | null
  description?: string
  uom?: string
  quantity: string
  unit_price: string
  discount_amount?: string
  tax_rate_id?: number
}

export interface Quote {
  id: number
  quote_no: string
  customer_id: number
  opportunity_id?: number | null
  contact_id?: number | null
  status: QuoteStatus
  issue_date?: string | null
  valid_until?: string | null
  owner_user_id?: number | null
  notes?: string | null
  currency_code: string
  subtotal: string
  discount_total: string
  tax_total: string
  grand_total: string
  version: number
  items: LineItem[]
  created_at: string
  updated_at: string
}

export interface PaginatedQuotes {
  items: Quote[]
  total: number
  page: number
  page_size: number
}

export interface QuoteCreatePayload {
  customer_id: number
  opportunity_id?: number | null
  contact_id?: number | null
  valid_until?: string | null
  notes?: string | null
  items: LineItemPayload[]
}

export interface SalesOrder {
  id: number
  order_no: string
  customer_id: number
  quote_id?: number | null
  contact_id?: number | null
  status: SalesOrderStatus
  order_date: string
  requested_delivery_date?: string | null
  billing_address_snapshot: string
  shipping_address_snapshot: string
  payment_terms_days_snapshot: number
  cancel_reason?: string | null
  owner_user_id?: number | null
  notes?: string | null
  currency_code: string
  subtotal: string
  discount_total: string
  tax_total: string
  grand_total: string
  version: number
  items: SalesOrderItem[]
  created_at: string
  updated_at: string
}

export interface PaginatedSalesOrders {
  items: SalesOrder[]
  total: number
  page: number
  page_size: number
}

export interface SalesOrderCreatePayload {
  customer_id: number
  quote_id?: number | null
  contact_id?: number | null
  order_date?: string | null
  requested_delivery_date?: string | null
  notes?: string | null
  items: LineItemPayload[]
}

export const salesApi = {
  // Tax Rates
  listTaxRates: () => api.get<TaxRate[]>('/api/v1/tax-rates'),

  // Quotes
  listQuotes: (params: { page?: number; page_size?: number; customer_id?: number; status?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.set('page', params.page.toString())
    if (params.page_size) q.set('page_size', params.page_size.toString())
    if (params.customer_id) q.set('customer_id', params.customer_id.toString())
    if (params.status) q.set('status', params.status)
    return api.get<PaginatedQuotes>(`/api/v1/quotes?${q.toString()}`)
  },
  getQuote: (id: number) => api.get<Quote>(`/api/v1/quotes/${id}`),
  createQuote: (payload: QuoteCreatePayload) => api.post<Quote>('/api/v1/quotes', payload),
  updateQuote: (id: number, payload: { contact_id?: number | null; valid_until?: string | null; notes?: string | null; items: LineItemPayload[]; version: number }) =>
    api.put<Quote>(`/api/v1/quotes/${id}`, payload),
  sendQuote: (id: number) => api.post<Quote>(`/api/v1/quotes/${id}/send`),
  acceptQuote: (id: number) => api.post<Quote>(`/api/v1/quotes/${id}/accept`),
  rejectQuote: (id: number, reason?: string) => api.post<Quote>(`/api/v1/quotes/${id}/reject`, { reason }),
  cancelQuote: (id: number, reason?: string) => api.post<Quote>(`/api/v1/quotes/${id}/cancel`, { reason }),
  createOrderFromQuote: (id: number) => api.post<SalesOrder>(`/api/v1/quotes/${id}/create-order`),

  // Sales Orders
  listSalesOrders: (params: { page?: number; page_size?: number; customer_id?: number; status?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.set('page', params.page.toString())
    if (params.page_size) q.set('page_size', params.page_size.toString())
    if (params.customer_id) q.set('customer_id', params.customer_id.toString())
    if (params.status) q.set('status', params.status)
    return api.get<PaginatedSalesOrders>(`/api/v1/sales-orders?${q.toString()}`)
  },
  getSalesOrder: (id: number) => api.get<SalesOrder>(`/api/v1/sales-orders/${id}`),
  createSalesOrder: (payload: SalesOrderCreatePayload) => api.post<SalesOrder>('/api/v1/sales-orders', payload),
  confirmSalesOrder: (id: number) => api.post<SalesOrder>(`/api/v1/sales-orders/${id}/confirm`),
  holdSalesOrder: (id: number, reason?: string) => api.post<SalesOrder>(`/api/v1/sales-orders/${id}/hold`, { reason }),
  releaseSalesOrder: (id: number) => api.post<SalesOrder>(`/api/v1/sales-orders/${id}/release`),
  cancelSalesOrder: (id: number, reason?: string) => api.post<SalesOrder>(`/api/v1/sales-orders/${id}/cancel`, { reason }),
}
