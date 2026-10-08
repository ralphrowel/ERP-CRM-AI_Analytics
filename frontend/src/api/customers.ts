import { api } from './client'

export interface CustomerAddress {
  id: number
  customer_id: number
  address_type: 'billing' | 'shipping'
  line1: string
  line2?: string | null
  barangay?: string | null
  city: string
  province?: string | null
  postal_code?: string | null
  country_code: string
  is_default: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Customer {
  id: number
  customer_no: string
  name: string
  customer_type: 'company' | 'individual'
  status: 'prospect' | 'active' | 'inactive'
  tin?: string | null
  email?: string | null
  phone?: string | null
  website?: string | null
  industry?: string | null
  payment_terms_days: number
  credit_limit?: string | null
  owner_user_id?: number | null
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
  addresses: CustomerAddress[]
}

export interface PaginatedCustomers {
  items: Customer[]
  total: number
  page: number
  page_size: number
}

export interface CustomerCreatePayload {
  name: string
  customer_type?: 'company' | 'individual'
  status?: 'prospect' | 'active' | 'inactive'
  tin?: string
  email?: string
  phone?: string
  website?: string
  industry?: string
  payment_terms_days?: number
  credit_limit?: string
  notes?: string
  initial_address?: {
    address_type: 'billing' | 'shipping'
    line1: string
    line2?: string
    city: string
    province?: string
    postal_code?: string
    country_code?: string
    is_default?: boolean
  }
}

export interface CustomerUpdatePayload {
  name?: string
  customer_type?: 'company' | 'individual'
  status?: 'prospect' | 'active' | 'inactive'
  tin?: string
  email?: string
  phone?: string
  website?: string
  industry?: string
  payment_terms_days?: number
  credit_limit?: string
  notes?: string
  version: number
}

export const customersApi = {
  list: (params: { page?: number; page_size?: number; status?: string; search?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.page) query.set('page', params.page.toString())
    if (params.page_size) query.set('page_size', params.page_size.toString())
    if (params.status) query.set('status', params.status)
    if (params.search) query.set('search', params.search)
    return api.get<PaginatedCustomers>(`/api/v1/customers?${query.toString()}`)
  },
  get: (id: number) => api.get<Customer>(`/api/v1/customers/${id}`),
  create: (data: CustomerCreatePayload) => api.post<Customer>('/api/v1/customers', data),
  update: (id: number, data: CustomerUpdatePayload) => api.patch<Customer>(`/api/v1/customers/${id}`, data),
  deactivate: (id: number) => api.post<Customer>(`/api/v1/customers/${id}/deactivate`),
  addAddress: (customerId: number, data: CustomerAddress) =>
    api.post<CustomerAddress>(`/api/v1/customers/${customerId}/addresses`, data),
}
