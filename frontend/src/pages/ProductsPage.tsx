import React, { useEffect, useState } from 'react'
import {
  Boxes,
  CheckCircle,
  Edit2,
  FolderPlus,
  Package,
  Plus,
  RefreshCw,
  Search,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type Product,
  type ProductCategory,
  type ProductCreatePayload,
  productsApi,
  type ProductUpdatePayload,
} from '../api/products'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

export const ProductsPage: React.FC = () => {
  const [products, setProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<ProductCategory[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCatId, setSelectedCatId] = useState<number | undefined>(undefined)
  const [isLoading, setIsLoading] = useState(true)

  // Errors & Conflict
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)

  // Forms
  const [formData, setFormData] = useState<ProductCreatePayload>({
    sku: '',
    name: '',
    description: '',
    category_id: null,
    product_type: 'stock',
    uom: 'pc',
    list_price: '150.0000',
  })

  const [editFormData, setEditFormData] = useState<ProductUpdatePayload>({
    sku: '',
    name: '',
    description: '',
    category_id: null,
    product_type: 'stock',
    uom: 'pc',
    list_price: '0.0000',
    version: 1,
  })

  const [newCategoryName, setNewCategoryName] = useState('')

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [prodRes, catRes] = await Promise.all([
        productsApi.list({
          page,
          page_size: pageSize,
          search: searchTerm || undefined,
          category_id: selectedCatId,
        }),
        productsApi.listCategories(),
      ])
      setProducts(prodRes.items)
      setTotal(prodRes.total)
      setCategories(catRes)
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, selectedCatId])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadData()
  }

  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault()
    setGeneralError(null)
    try {
      await productsApi.create(formData)
      setIsCreateOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const openEditModal = (prod: Product) => {
    setSelectedProduct(prod)
    setConflictError(null)
    setGeneralError(null)
    setEditFormData({
      sku: prod.sku,
      name: prod.name,
      description: prod.description || '',
      category_id: prod.category_id,
      product_type: prod.product_type,
      uom: prod.uom,
      list_price: prod.list_price,
      version: prod.version,
    })
    setIsEditOpen(true)
  }

  const handleUpdateProduct = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedProduct) return
    setConflictError(null)
    setGeneralError(null)

    try {
      await productsApi.update(selectedProduct.id, editFormData)
      setIsEditOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError(
            'This product was modified by another transaction. Please reload before saving again.'
          )
        } else {
          setGeneralError(err)
        }
      }
    }
  }

  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newCategoryName.trim()) return
    try {
      await productsApi.createCategory(newCategoryName.trim())
      setNewCategoryName('')
      setIsCategoryModalOpen(false)
      const catRes = await productsApi.listCategories()
      setCategories(catRes)
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleDeactivate = async (id: number) => {
    if (!confirm('Are you sure you want to deactivate this product?')) return
    try {
      await productsApi.deactivate(id)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
            Product Catalog & Items
          </h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Inventory master data, VAT-exclusive catalog pricing (NUMERIC 19,4), and categories.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => setIsCategoryModalOpen(true)}
            className="btn btn-secondary"
          >
            <FolderPlus size={16} /> New Category
          </button>
          <button
            id="btn-create-product"
            onClick={() => setIsCreateOpen(true)}
            className="btn btn-primary"
          >
            <Plus size={16} /> New Product
          </button>
        </div>
      </div>

      {conflictError && <ConflictAlert onReload={loadData} message={conflictError} />}
      {generalError && <ProblemAlert error={generalError} onDismiss={() => setGeneralError(null)} />}

      {/* Filter and Search Bar */}
      <div
        className="glass-panel"
        style={{
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.5rem',
        }}
      >
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '0.5rem', flex: 1, maxWidth: '400px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)' }}
            />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by SKU or item name..."
              className="input-field"
              style={{ paddingLeft: '2.2rem' }}
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Filter
          </button>
        </form>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Category:</span>
          <select
            value={selectedCatId || ''}
            onChange={(e) => {
              setSelectedCatId(e.target.value ? parseInt(e.target.value) : undefined)
              setPage(1)
            }}
            className="input-field"
            style={{ width: 'auto', padding: '0.4rem 0.75rem' }}
          >
            <option value="">All Categories</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>

          <button onClick={loadData} className="btn btn-secondary" title="Refresh">
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel erp-table-container">
        <table className="erp-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Product Name</th>
              <th>Type</th>
              <th>Category</th>
              <th>UOM</th>
              <th>List Price (PHP)</th>
              <th>Status</th>
              <th>Version</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-dim)' }}>
                  {isLoading ? 'Loading catalog items...' : 'No products found.'}
                </td>
              </tr>
            ) : (
              products.map((p) => {
                const cat = categories.find((c) => c.id === p.category_id)
                return (
                  <tr key={p.id}>
                    <td>
                      <span className="code-pill">{p.sku}</span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      {p.description && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{p.description}</div>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-subtle">
                        {p.product_type === 'stock' ? <Package size={11} /> : <Boxes size={11} />}
                        {p.product_type}
                      </span>
                    </td>
                    <td>{cat?.name || '—'}</td>
                    <td>
                      <span style={{ fontWeight: 600, color: 'var(--text-dim)' }}>{p.uom}</span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      ₱{parseFloat(p.list_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                    </td>
                    <td>
                      {p.is_active ? (
                        <span className="badge badge-emerald"><CheckCircle size={12} /> Active</span>
                      ) : (
                        <span className="badge badge-rose"><XCircle size={12} /> Inactive</span>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-subtle">v{p.version}</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                        <button
                          onClick={() => openEditModal(p)}
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.65rem' }}
                          title="Edit Product"
                        >
                          <Edit2 size={13} /> Edit
                        </button>
                        {p.is_active && (
                          <button
                            onClick={() => handleDeactivate(p.id)}
                            className="btn btn-danger"
                            style={{ padding: '0.35rem 0.65rem' }}
                            title="Deactivate"
                          >
                            <XCircle size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: '1rem',
          fontSize: '0.85rem',
          color: 'var(--text-muted)',
        }}
      >
        <span>
          Showing {products.length} of {total} products
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="btn btn-secondary"
            style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
          >
            Previous
          </button>
          <span style={{ padding: '0.3rem 0.5rem', alignSelf: 'center' }}>Page {page}</span>
          <button
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
            className="btn btn-secondary"
            style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
          >
            Next
          </button>
        </div>
      </div>

      {/* Create Product Modal */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Product" maxWidth="560px">
        <form onSubmit={handleCreateProduct} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>SKU *</label>
              <input
                type="text"
                required
                value={formData.sku}
                onChange={(e) => setFormData({ ...formData, sku: e.target.value.toUpperCase() })}
                className="input-field"
                placeholder="SKU-001"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Product Name *</label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="input-field"
                placeholder="Industrial Valve Assembly 50mm"
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Category</label>
            <select
              value={formData.category_id || ''}
              onChange={(e) => setFormData({ ...formData, category_id: e.target.value ? parseInt(e.target.value) : null })}
              className="input-field"
            >
              <option value="">No Category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Type</label>
              <select
                value={formData.product_type}
                onChange={(e) => setFormData({ ...formData, product_type: e.target.value as 'stock' | 'service' })}
                className="input-field"
              >
                <option value="stock">Stock Item</option>
                <option value="service">Service</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Unit (UOM)</label>
              <select
                value={formData.uom}
                onChange={(e) => setFormData({ ...formData, uom: e.target.value as 'pc' | 'box' | 'pack' | 'kg' | 'l' | 'm' | 'hr' })}
                className="input-field"
              >
                <option value="pc">Piece (pc)</option>
                <option value="box">Box (box)</option>
                <option value="pack">Pack (pack)</option>
                <option value="kg">Kilogram (kg)</option>
                <option value="l">Liter (l)</option>
                <option value="m">Meter (m)</option>
                <option value="hr">Hour (hr)</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>List Price (₱) *</label>
              <input
                type="text"
                required
                value={formData.list_price}
                onChange={(e) => setFormData({ ...formData, list_price: e.target.value })}
                className="input-field"
                placeholder="150.0000"
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Description</label>
            <textarea
              rows={2}
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="input-field"
              placeholder="Technical specifications, notes..."
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsCreateOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Create Product
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Product Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`Edit Product: ${selectedProduct?.sku}`}>
        <form onSubmit={handleUpdateProduct} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Product Name</label>
            <input
              type="text"
              required
              value={editFormData.name}
              onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
              className="input-field"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Category</label>
              <select
                value={editFormData.category_id || ''}
                onChange={(e) =>
                  setEditFormData({ ...editFormData, category_id: e.target.value ? parseInt(e.target.value) : null })
                }
                className="input-field"
              >
                <option value="">No Category</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>List Price (₱)</label>
              <input
                type="text"
                value={editFormData.list_price}
                onChange={(e) => setEditFormData({ ...editFormData, list_price: e.target.value })}
                className="input-field"
              />
            </div>
          </div>

          <div
            style={{
              padding: '0.75rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(0, 0, 0, 0.25)',
              border: '1px solid var(--border-subtle)',
              fontSize: '0.775rem',
              color: 'var(--text-dim)',
            }}
          >
            Optimistic lock token: <strong>version {editFormData.version}</strong>.
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsEditOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </Modal>

      {/* New Category Modal */}
      <Modal isOpen={isCategoryModalOpen} onClose={() => setIsCategoryModalOpen(false)} title="Add Product Category" maxWidth="440px">
        <form onSubmit={handleCreateCategory} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Category Name *</label>
            <input
              type="text"
              required
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              className="input-field"
              placeholder="e.g. Electrical Components"
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsCategoryModalOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Category
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
