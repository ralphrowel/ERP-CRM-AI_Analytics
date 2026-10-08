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
  warehouse_id?: number | null
  warehouse?: {
    id: number
    code: string
    name: string
  } | null
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
  warehouse_id?: number | null
  quote_id?: number | null
  contact_id?: number | null
  order_date?: string | null
  requested_delivery_date?: string | null
  notes?: string | null
  items: LineItemPayload[]
}

// --- Invoices ---

export type InvoiceStatus = 'draft' | 'issued' | 'partially_paid' | 'paid' | 'void'

export interface InvoiceItem extends LineItem {
  sales_order_item_id?: number | null
}

export interface Invoice {
  id: number
  invoice_no?: string | null
  customer_id: number
  sales_order_id?: number | null
  status: InvoiceStatus
  issue_date?: string | null
  due_date?: string | null
  customer_name_snapshot?: string | null
  customer_tin_snapshot?: string | null
  billing_address_snapshot?: string | null
  currency_code: string
  subtotal: string
  discount_total: string
  tax_total: string
  grand_total: string
  amount_paid: string
  amount_credited: string
  balance_due: string
  voided_at?: string | null
  void_reason?: string | null
  version: number
  items: InvoiceItem[]
  created_at: string
  updated_at: string
}

export interface PaginatedInvoices {
  items: Invoice[]
  total: number
  page: number
  page_size: number
}

// --- Payments ---

export type PaymentMethod = 'cash' | 'bank_transfer' | 'check' | 'gcash' | 'maya' | 'card'
export type PaymentStatus = 'posted' | 'void'

export interface PaymentAllocation {
  id: number
  payment_id: number
  invoice_id: number
  amount: string
  allocated_at: string
  allocated_by?: number | null
  invoice_no?: string | null
}

export interface Payment {
  id: number
  payment_no: string
  customer_id: number
  payment_date: string
  method: PaymentMethod
  reference_no?: string | null
  amount: string
  amount_allocated: string
  unallocated_amount: string
  status: PaymentStatus
  void_reason?: string | null
  version: number
  allocations: PaymentAllocation[]
  created_at: string
  updated_at: string
}

export interface PaginatedPayments {
  items: Payment[]
  total: number
  page: number
  page_size: number
}

export interface PaymentCreatePayload {
  customer_id: number
  payment_date?: string | null
  method: PaymentMethod
  reference_no?: string | null
  amount: string
  allocations?: Array<{ invoice_id: number; amount: string }>
}

// --- Credit Notes ---

export interface CreditNoteItem extends LineItem {
  invoice_item_id?: number | null
}

export interface CreditNote {
  id: number
  credit_note_no?: string | null
  invoice_id: number
  customer_id: number
  status: string
  issue_date?: string | null
  reason: string
  currency_code: string
  subtotal: string
  discount_total: string
  tax_total: string
  grand_total: string
  version: number
  items: CreditNoteItem[]
  created_at: string
  updated_at: string
}

export interface PaginatedCreditNotes {
  items: CreditNote[]
  total: number
  page: number
  page_size: number
}

export interface CreditNoteCreatePayload {
  invoice_id: number
  reason: string
  items?: Array<{
    invoice_item_id?: number | null
    product_id?: number | null
    description?: string
    uom?: string
    quantity: string
    unit_price: string
    discount_amount?: string
    tax_rate_id?: number
  }>
}

// --- AR Statement ---

export interface StatementTransaction {
  date: string
  doc_type: string
  doc_no: string
  reference?: string | null
  amount_invoiced: string
  amount_paid: string
  running_balance: string
}

export interface CustomerStatement {
  customer_id: number
  customer_name: string
  statement_date: string
  total_invoiced: string
  total_paid: string
  total_credited: string
  unallocated_credit: string
  open_ar_balance: string
  transactions: StatementTransaction[]
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
  createInvoiceFromOrder: (orderId: number, payload?: { items?: Array<{ sales_order_item_id: number; quantity: string; unit_price: string; discount_amount?: string }> }) =>
    api.post<Invoice>(`/api/v1/sales-orders/${orderId}/create-invoice`, payload),

  // Invoices
  listInvoices: (params: { page?: number; page_size?: number; customer_id?: number; status?: string; sales_order_id?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.set('page', params.page.toString())
    if (params.page_size) q.set('page_size', params.page_size.toString())
    if (params.customer_id) q.set('customer_id', params.customer_id.toString())
    if (params.status) q.set('status', params.status)
    if (params.sales_order_id) q.set('sales_order_id', params.sales_order_id.toString())
    return api.get<PaginatedInvoices>(`/api/v1/invoices?${q.toString()}`)
  },
  getInvoice: (id: number) => api.get<Invoice>(`/api/v1/invoices/${id}`),
  issueInvoice: (id: number, payload?: { issue_date?: string; due_date?: string }, idempotencyKey?: string) => {
    const headers: Record<string, string> = {}
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
    return api.post<Invoice>(`/api/v1/invoices/${id}/issue`, payload, headers)
  },
  voidInvoice: (id: number, reason?: string) => api.post<Invoice>(`/api/v1/invoices/${id}/void`, { reason }),

  // Payments
  listPayments: (params: { page?: number; page_size?: number; customer_id?: number; status?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.set('page', params.page.toString())
    if (params.page_size) q.set('page_size', params.page_size.toString())
    if (params.customer_id) q.set('customer_id', params.customer_id.toString())
    if (params.status) q.set('status', params.status)
    return api.get<PaginatedPayments>(`/api/v1/payments?${q.toString()}`)
  },
  getPayment: (id: number) => api.get<Payment>(`/api/v1/payments/${id}`),
  createPayment: (payload: PaymentCreatePayload, idempotencyKey?: string) => {
    const headers: Record<string, string> = {}
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
    return api.post<Payment>('/api/v1/payments', payload, headers)
  },
  allocatePayment: (paymentId: number, payload: { invoice_id: number; amount: string }) =>
    api.post<PaymentAllocation>(`/api/v1/payments/${paymentId}/allocations`, payload),
  voidPayment: (paymentId: number, reason?: string) =>
    api.post<Payment>(`/api/v1/payments/${paymentId}/void`, { reason }),

  // Credit Notes
  listCreditNotes: (params: { page?: number; page_size?: number; customer_id?: number; invoice_id?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.set('page', params.page.toString())
    if (params.page_size) q.set('page_size', params.page_size.toString())
    if (params.customer_id) q.set('customer_id', params.customer_id.toString())
    if (params.invoice_id) q.set('invoice_id', params.invoice_id.toString())
    return api.get<PaginatedCreditNotes>(`/api/v1/credit-notes?${q.toString()}`)
  },
  getCreditNote: (id: number) => api.get<CreditNote>(`/api/v1/credit-notes/${id}`),
  createCreditNote: (payload: CreditNoteCreatePayload) => api.post<CreditNote>('/api/v1/credit-notes', payload),

  // AR Statement
  getCustomerStatement: (customerId: number) =>
    api.get<CustomerStatement>(`/api/v1/customers/${customerId}/statement`),
}
