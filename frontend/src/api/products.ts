import { api } from './client'

export interface ProductCategory {
  id: number
  name: string
  parent_id?: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Product {
  id: number
  sku: string
  name: string
  description?: string | null
  category_id?: number | null
  tax_rate_id?: number | null
  product_type: 'stock' | 'service'
  uom: 'pc' | 'box' | 'pack' | 'kg' | 'l' | 'm' | 'hr'
  list_price: string
  reorder_point?: string
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface PaginatedProducts {
  items: Product[]
  total: number
  page: number
  page_size: number
}

export interface ProductCreatePayload {
  sku: string
  name: string
  description?: string
  category_id?: number | null
  product_type?: 'stock' | 'service'
  uom?: 'pc' | 'box' | 'pack' | 'kg' | 'l' | 'm' | 'hr'
  list_price: string
  reorder_point?: string
}

export interface ProductUpdatePayload {
  sku?: string
  name?: string
  description?: string
  category_id?: number | null
  product_type?: 'stock' | 'service'
  uom?: 'pc' | 'box' | 'pack' | 'kg' | 'l' | 'm' | 'hr'
  list_price?: string
  reorder_point?: string
  is_active?: boolean
  version: number
}

export const productsApi = {
  list: (params: { page?: number; page_size?: number; category_id?: number; search?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.page) query.set('page', params.page.toString())
    if (params.page_size) query.set('page_size', params.page_size.toString())
    if (params.category_id) query.set('category_id', params.category_id.toString())
    if (params.search) query.set('search', params.search)
    return api.get<PaginatedProducts>(`/api/v1/products?${query.toString()}`)
  },
  get: (id: number) => api.get<Product>(`/api/v1/products/${id}`),
  create: (data: ProductCreatePayload) => api.post<Product>('/api/v1/products', data),
  update: (id: number, data: ProductUpdatePayload) => api.patch<Product>(`/api/v1/products/${id}`, data),
  deactivate: (id: number) => api.post<Product>(`/api/v1/products/${id}/deactivate`),

  listCategories: () => api.get<ProductCategory[]>('/api/v1/product-categories'),
  createCategory: (name: string, parent_id?: number | null) =>
    api.post<ProductCategory>('/api/v1/product-categories', { name, parent_id }),
}
