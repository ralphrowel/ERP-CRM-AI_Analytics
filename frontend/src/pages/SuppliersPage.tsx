import React, { useEffect, useState } from 'react'
import {
  Building2,
  CheckCircle,
  Clock,
  Edit2,
  Package,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Product, productsApi } from '../api/products'
import {
  type Supplier,
  type SupplierCreatePayload,
  type SupplierProduct,
  type SupplierProductCreatePayload,
  suppliersApi,
  type SupplierUpdatePayload,
} from '../api/purchasing'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

export const SuppliersPage: React.FC = () => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [searchTerm, setSearchTerm] = useState('')
  const [activeFilter, setActiveFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master products for catalog linking
  const [availableProducts, setAvailableProducts] = useState<Product[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isCatalogOpen, setIsCatalogOpen] = useState(false)
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null)
  const [supplierProducts, setSupplierProducts] = useState<SupplierProduct[]>([])
  const [loadingProducts, setLoadingProducts] = useState(false)

  // Create form state
  const [createData, setCreateData] = useState<SupplierCreatePayload>({
    name: '',
    tin: '',
    email: '',
    phone: '',
    address: '',
    payment_terms_days: 30,
    is_active: true,
    notes: '',
  })

  // Edit form state
  const [editData, setEditData] = useState<{
    name: string
    tin: string
    email: string
    phone: string
    address: string
    payment_terms_days: number
    is_active: boolean
    notes: string
    version: number
  }>({
    name: '',
    tin: '',
    email: '',
    phone: '',
    address: '',
    payment_terms_days: 30,
    is_active: true,
    notes: '',
    version: 1,
  })

  // Add Catalog Product form state
  const [catalogFormData, setCatalogFormData] = useState<SupplierProductCreatePayload>({
    product_id: 0,
    supplier_sku: '',
    last_unit_cost: '',
    lead_time_days: 7,
    is_preferred: false,
  })

  const loadSuppliers = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const res = await suppliersApi.list({
        page,
        page_size: pageSize,
        search: searchTerm || undefined,
        is_active: activeFilter === '' ? undefined : activeFilter === 'true',
      })
      setSuppliers(res.items)
      setTotal(res.total)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load suppliers.'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  const loadProducts = async () => {
    try {
      const res = await productsApi.list({ page: 1, page_size: 200 })
      setAvailableProducts(res.items)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadSuppliers()
    loadProducts()
  }, [page, activeFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadSuppliers()
  }

  const handleCreateSupplier = async (e: React.FormEvent) => {
    e.preventDefault()
    setGeneralError(null)
    try {
      await suppliersApi.create({
        ...createData,
        tin: createData.tin || undefined,
        email: createData.email || undefined,
        phone: createData.phone || undefined,
        address: createData.address || undefined,
        notes: createData.notes || undefined,
      })
      setIsCreateOpen(false)
      setCreateData({
        name: '',
        tin: '',
        email: '',
        phone: '',
        address: '',
        payment_terms_days: 30,
        is_active: true,
        notes: '',
      })
      setSuccessMessage('Supplier registered successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadSuppliers()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create supplier.'))
      }
    }
  }

  const handleOpenEdit = (sup: Supplier) => {
    setSelectedSupplier(sup)
    setEditData({
      name: sup.name,
      tin: sup.tin || '',
      email: sup.email || '',
      phone: sup.phone || '',
      address: sup.address || '',
      payment_terms_days: sup.payment_terms_days,
      is_active: sup.is_active,
      notes: sup.notes || '',
      version: sup.version,
    })
    setConflictError(null)
    setGeneralError(null)
    setIsEditOpen(true)
  }

  const handleUpdateSupplier = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedSupplier) return
    setGeneralError(null)
    setConflictError(null)
    try {
      const payload: SupplierUpdatePayload = {
        name: editData.name,
        tin: editData.tin || null,
        email: editData.email || null,
        phone: editData.phone || null,
        address: editData.address || null,
        payment_terms_days: editData.payment_terms_days,
        is_active: editData.is_active,
        notes: editData.notes || null,
        version: editData.version,
      }
      await suppliersApi.update(selectedSupplier.id, payload)
      setIsEditOpen(false)
      setSelectedSupplier(null)
      setSuccessMessage('Supplier updated successfully.')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadSuppliers()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Conflict: This supplier record was modified in another session. Please reload.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to update supplier.'))
      }
    }
  }

  const handleOpenCatalog = async (sup: Supplier) => {
    setSelectedSupplier(sup)
    setIsCatalogOpen(true)
    setLoadingProducts(true)
    try {
      const prods = await suppliersApi.listProducts(sup.id)
      setSupplierProducts(prods)
    } catch {
      setSupplierProducts([])
    } finally {
      setLoadingProducts(false)
    }
  }

  const handleAddCatalogProduct = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedSupplier || !catalogFormData.product_id) return
    try {
      await suppliersApi.addProduct(selectedSupplier.id, {
        product_id: Number(catalogFormData.product_id),
        supplier_sku: catalogFormData.supplier_sku || undefined,
        last_unit_cost: catalogFormData.last_unit_cost ? Number(catalogFormData.last_unit_cost) : undefined,
        lead_time_days: catalogFormData.lead_time_days ? Number(catalogFormData.lead_time_days) : undefined,
        is_preferred: catalogFormData.is_preferred,
      })
      // reload catalog
      const prods = await suppliersApi.listProducts(selectedSupplier.id)
      setSupplierProducts(prods)
      setCatalogFormData({
        product_id: 0,
        supplier_sku: '',
        last_unit_cost: '',
        lead_time_days: 7,
        is_preferred: false,
      })
      loadSuppliers()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to link product to supplier catalog.'))
      }
    }
  }

  const handleRemoveCatalogProduct = async (productId: number) => {
    if (!selectedSupplier) return
    if (!confirm('Remove this product mapping from supplier catalog?')) return
    try {
      await suppliersApi.removeProduct(selectedSupplier.id, productId)
      const prods = await suppliersApi.listProducts(selectedSupplier.id)
      setSupplierProducts(prods)
      loadSuppliers()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to remove product from catalog.'))
      }
    }
  }

  return (
    <div>
      {/* Page Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
            Suppliers & Vendors
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Manage procurement suppliers, purchase catalogs, agreed unit costs, and lead times
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            id="reload-suppliers-btn"
            onClick={loadSuppliers}
            className="btn btn-secondary"
            title="Refresh List"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            id="create-supplier-btn"
            onClick={() => {
              setConflictError(null)
              setGeneralError(null)
              setIsCreateOpen(true)
            }}
            className="btn btn-primary"
          >
            <Plus size={16} />
            New Supplier
          </button>
        </div>
      </div>

      {/* Success Notification */}
      {successMessage && (
        <div
          style={{
            padding: '0.75rem 1rem',
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid #10b981',
            borderRadius: '8px',
            color: '#34d399',
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <CheckCircle size={18} />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Alerts */}
      {conflictError && <ConflictAlert onReload={loadSuppliers} message={conflictError} />}
      {generalError && <ProblemAlert error={generalError} />}

      {/* Filters Bar */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          padding: '1rem',
          marginBottom: '1.5rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <form
          onSubmit={handleSearchSubmit}
          style={{ display: 'flex', gap: '0.5rem', flex: 1, minWidth: '280px' }}
        >
          <div style={{ position: 'relative', flex: 1 }}>
            <Search
              size={16}
              style={{
                position: 'absolute',
                left: '0.75rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-dim)',
              }}
            />
            <input
              id="supplier-search-input"
              type="text"
              placeholder="Search by supplier name, code, TIN, email..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input"
              style={{ paddingLeft: '2.25rem', width: '100%' }}
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Search
          </button>
        </form>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Status:</label>
          <select
            id="supplier-status-filter"
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value)
              setPage(1)
            }}
            className="input"
            style={{ minWidth: '130px' }}
          >
            <option value="">All Statuses</option>
            <option value="true">Active Only</option>
            <option value="false">Inactive Only</option>
          </select>
        </div>
      </div>

      {/* Table Section */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        {isLoading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-dim)' }}>
            <RefreshCw size={28} className="animate-spin" style={{ margin: '0 auto 1rem' }} />
            <p>Loading suppliers directory...</p>
          </div>
        ) : suppliers.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-dim)' }}>
            <Building2 size={36} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-main)' }}>
              No suppliers found
            </p>
            <p style={{ fontSize: '0.85rem' }}>
              Create your first supplier or adjust your search filter.
            </p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr
                style={{
                  borderBottom: '1px solid var(--border-subtle)',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  fontSize: '0.75rem',
                  textTransform: 'uppercase',
                  color: 'var(--text-dim)',
                  letterSpacing: '0.05em',
                }}
              >
                <th style={{ padding: '0.85rem 1rem' }}>Supplier Code & Name</th>
                <th style={{ padding: '0.85rem 1rem' }}>TIN & Contact</th>
                <th style={{ padding: '0.85rem 1rem' }}>Address</th>
                <th style={{ padding: '0.85rem 1rem' }}>Payment Terms</th>
                <th style={{ padding: '0.85rem 1rem' }}>Catalog</th>
                <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((sup) => (
                <tr
                  key={sup.id}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    fontSize: '0.875rem',
                    transition: 'background-color 0.15s',
                  }}
                  className="table-row-hover"
                >
                  <td style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <span className="badge badge-indigo" style={{ fontWeight: 700 }}>
                        {sup.supplier_no}
                      </span>
                      <strong style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>
                        {sup.name}
                      </strong>
                    </div>
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <div style={{ fontSize: '0.825rem', color: 'var(--text-muted)' }}>
                      {sup.tin ? <div>TIN: {sup.tin}</div> : null}
                      {sup.email ? <div>{sup.email}</div> : null}
                      {sup.phone ? <div>{sup.phone}</div> : null}
                      {!sup.tin && !sup.email && !sup.phone && (
                        <span style={{ color: 'var(--text-dim)' }}>—</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '1rem', color: 'var(--text-muted)', fontSize: '0.825rem', maxWidth: '200px' }}>
                    {sup.address || <span style={{ color: 'var(--text-dim)' }}>No address</span>}
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <span className="badge badge-subtle">
                      <Clock size={12} /> Net {sup.payment_terms_days} Days
                    </span>
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <button
                      id={`supplier-catalog-btn-${sup.id}`}
                      onClick={() => handleOpenCatalog(sup)}
                      className="btn btn-secondary"
                      style={{ fontSize: '0.8rem', padding: '0.35rem 0.65rem' }}
                    >
                      <Package size={14} />
                      {sup.products?.length || 0} Products
                    </button>
                  </td>
                  <td style={{ padding: '1rem' }}>
                    {sup.is_active ? (
                      <span className="badge badge-emerald">
                        <CheckCircle size={12} /> Active
                      </span>
                    ) : (
                      <span className="badge badge-rose">
                        <XCircle size={12} /> Inactive
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '1rem', textAlign: 'right' }}>
                    <button
                      id={`edit-supplier-btn-${sup.id}`}
                      onClick={() => handleOpenEdit(sup)}
                      className="btn btn-secondary"
                      style={{ fontSize: '0.8rem', padding: '0.35rem 0.65rem' }}
                    >
                      <Edit2 size={13} />
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination Footer */}
        {total > pageSize && (
          <div
            style={{
              padding: '1rem',
              borderTop: '1px solid var(--border-subtle)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '0.85rem',
              color: 'var(--text-dim)',
            }}
          >
            <div>
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} suppliers
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="btn btn-secondary"
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
              >
                Previous
              </button>
              <button
                disabled={page * pageSize >= total}
                onClick={() => setPage((p) => p + 1)}
                className="btn btn-secondary"
                style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* CREATE SUPPLIER MODAL */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Register New Supplier"
      >
        <form onSubmit={handleCreateSupplier} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label className="label">
              Supplier Name <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <input
              id="create-supplier-name"
              type="text"
              required
              value={createData.name}
              onChange={(e) => setCreateData({ ...createData, name: e.target.value })}
              className="input"
              placeholder="e.g. Apex Industrial Supplies Corp."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">Tax Identification Number (TIN)</label>
              <input
                id="create-supplier-tin"
                type="text"
                value={createData.tin || ''}
                onChange={(e) => setCreateData({ ...createData, tin: e.target.value })}
                className="input"
                placeholder="000-123-456-000"
              />
            </div>
            <div>
              <label className="label">Payment Terms (Days)</label>
              <input
                id="create-supplier-terms"
                type="number"
                min="0"
                value={createData.payment_terms_days}
                onChange={(e) =>
                  setCreateData({ ...createData, payment_terms_days: parseInt(e.target.value) || 0 })
                }
                className="input"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">Email Address</label>
              <input
                id="create-supplier-email"
                type="email"
                value={createData.email || ''}
                onChange={(e) => setCreateData({ ...createData, email: e.target.value })}
                className="input"
                placeholder="purchasing@supplier.com"
              />
            </div>
            <div>
              <label className="label">Phone / Contact</label>
              <input
                id="create-supplier-phone"
                type="text"
                value={createData.phone || ''}
                onChange={(e) => setCreateData({ ...createData, phone: e.target.value })}
                className="input"
                placeholder="+63 2 8123 4567"
              />
            </div>
          </div>

          <div>
            <label className="label">Business Address</label>
            <textarea
              id="create-supplier-address"
              rows={2}
              value={createData.address || ''}
              onChange={(e) => setCreateData({ ...createData, address: e.target.value })}
              className="input"
              placeholder="Building, Street, City, Region, Zip Code"
            />
          </div>

          <div>
            <label className="label">Internal Notes / Delivery Instructions</label>
            <textarea
              id="create-supplier-notes"
              rows={2}
              value={createData.notes || ''}
              onChange={(e) => setCreateData({ ...createData, notes: e.target.value })}
              className="input"
              placeholder="e.g. Free shipping for orders above ₱50,000"
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button
              type="button"
              onClick={() => setIsCreateOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-create-supplier-btn" type="submit" className="btn btn-primary">
              Save Supplier
            </button>
          </div>
        </form>
      </Modal>

      {/* EDIT SUPPLIER MODAL */}
      <Modal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        title={`Edit Supplier: ${selectedSupplier?.supplier_no}`}
      >
        <form onSubmit={handleUpdateSupplier} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label className="label">
              Supplier Name <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <input
              id="edit-supplier-name"
              type="text"
              required
              value={editData.name}
              onChange={(e) => setEditData({ ...editData, name: e.target.value })}
              className="input"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">TIN</label>
              <input
                id="edit-supplier-tin"
                type="text"
                value={editData.tin}
                onChange={(e) => setEditData({ ...editData, tin: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="label">Payment Terms (Days)</label>
              <input
                id="edit-supplier-terms"
                type="number"
                min="0"
                value={editData.payment_terms_days}
                onChange={(e) =>
                  setEditData({ ...editData, payment_terms_days: parseInt(e.target.value) || 0 })
                }
                className="input"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">Email</label>
              <input
                id="edit-supplier-email"
                type="email"
                value={editData.email}
                onChange={(e) => setEditData({ ...editData, email: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="label">Phone</label>
              <input
                id="edit-supplier-phone"
                type="text"
                value={editData.phone}
                onChange={(e) => setEditData({ ...editData, phone: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="label">Address</label>
            <textarea
              id="edit-supplier-address"
              rows={2}
              value={editData.address}
              onChange={(e) => setEditData({ ...editData, address: e.target.value })}
              className="input"
            />
          </div>

          <div>
            <label className="label">Notes</label>
            <textarea
              id="edit-supplier-notes"
              rows={2}
              value={editData.notes}
              onChange={(e) => setEditData({ ...editData, notes: e.target.value })}
              className="input"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              id="edit-supplier-is-active"
              type="checkbox"
              checked={editData.is_active}
              onChange={(e) => setEditData({ ...editData, is_active: e.target.checked })}
              style={{ width: '16px', height: '16px' }}
            />
            <label htmlFor="edit-supplier-is-active" style={{ fontSize: '0.875rem', color: 'var(--text-main)', cursor: 'pointer' }}>
              Supplier is Active for Purchase Orders
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button
              type="button"
              onClick={() => setIsEditOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-edit-supplier-btn" type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </Modal>

      {/* SUPPLIER CATALOG MODAL */}
      <Modal
        isOpen={isCatalogOpen}
        onClose={() => setIsCatalogOpen(false)}
        title={`Supplier Catalog: ${selectedSupplier?.name} (${selectedSupplier?.supplier_no})`}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Add product to catalog section */}
          <div
            style={{
              padding: '1rem',
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', color: 'var(--text-main)' }}>
              Add Product to Supplier Catalog
            </h4>
            <form onSubmit={handleAddCatalogProduct} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label className="label">Product *</label>
                  <select
                    id="catalog-product-select"
                    required
                    value={catalogFormData.product_id}
                    onChange={(e) => setCatalogFormData({ ...catalogFormData, product_id: Number(e.target.value) })}
                    className="input"
                  >
                    <option value={0}>Select product from master list...</option>
                    {availableProducts.map((p) => (
                      <option key={p.id} value={p.id}>
                        [{p.sku}] {p.name} ({p.uom})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">Supplier SKU</label>
                  <input
                    id="catalog-supplier-sku"
                    type="text"
                    placeholder="Vendor's item code"
                    value={catalogFormData.supplier_sku || ''}
                    onChange={(e) => setCatalogFormData({ ...catalogFormData, supplier_sku: e.target.value })}
                    className="input"
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label className="label">Last / Quoted Cost (₱)</label>
                  <input
                    id="catalog-unit-cost"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={catalogFormData.last_unit_cost || ''}
                    onChange={(e) => setCatalogFormData({ ...catalogFormData, last_unit_cost: e.target.value })}
                    className="input"
                  />
                </div>
                <div>
                  <label className="label">Lead Time (Days)</label>
                  <input
                    id="catalog-lead-time"
                    type="number"
                    min="0"
                    value={catalogFormData.lead_time_days || ''}
                    onChange={(e) =>
                      setCatalogFormData({ ...catalogFormData, lead_time_days: parseInt(e.target.value) || 0 })
                    }
                    className="input"
                  />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', paddingTop: '1.25rem' }}>
                  <input
                    id="catalog-is-preferred"
                    type="checkbox"
                    checked={catalogFormData.is_preferred}
                    onChange={(e) => setCatalogFormData({ ...catalogFormData, is_preferred: e.target.checked })}
                    style={{ width: '16px', height: '16px' }}
                  />
                  <label htmlFor="catalog-is-preferred" style={{ fontSize: '0.8rem', color: 'var(--text-main)', cursor: 'pointer' }}>
                    Preferred Vendor
                  </label>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                <button id="add-to-catalog-btn" type="submit" className="btn btn-primary" style={{ fontSize: '0.85rem' }}>
                  <Plus size={14} /> Add to Catalog
                </button>
              </div>
            </form>
          </div>

          {/* Current Catalog Table */}
          <div>
            <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: 'var(--text-main)' }}>
              Catalog Items ({supplierProducts.length})
            </h4>
            {loadingProducts ? (
              <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-dim)' }}>
                Loading catalog...
              </div>
            ) : supplierProducts.length === 0 ? (
              <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
                No products configured for this supplier yet.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)', textAlign: 'left' }}>
                    <th style={{ padding: '0.5rem' }}>Product / SKU</th>
                    <th style={{ padding: '0.5rem' }}>Supplier SKU</th>
                    <th style={{ padding: '0.5rem' }}>Quoted Unit Cost</th>
                    <th style={{ padding: '0.5rem' }}>Lead Time</th>
                    <th style={{ padding: '0.5rem' }}>Status</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {supplierProducts.map((sp) => (
                    <tr key={sp.product_id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '0.5rem' }}>
                        <strong>{sp.product_name}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          SKU: {sp.product_sku} · {sp.product_uom}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem', color: 'var(--text-muted)' }}>
                        {sp.supplier_sku || '—'}
                      </td>
                      <td style={{ padding: '0.5rem', fontWeight: 600, color: 'var(--text-main)' }}>
                        {sp.last_unit_cost ? `₱${Number(sp.last_unit_cost).toLocaleString('en-PH', { minimumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td style={{ padding: '0.5rem', color: 'var(--text-muted)' }}>
                        {sp.lead_time_days ? `${sp.lead_time_days} days` : '—'}
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        {sp.is_preferred ? (
                          <span className="badge badge-emerald" style={{ fontSize: '0.7rem' }}>
                            Preferred
                          </span>
                        ) : (
                          <span className="badge badge-subtle" style={{ fontSize: '0.7rem' }}>
                            Standard
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                        <button
                          id={`remove-product-${sp.product_id}-btn`}
                          onClick={() => handleRemoveCatalogProduct(sp.product_id)}
                          className="btn btn-secondary"
                          style={{ padding: '0.25rem 0.5rem', color: 'var(--danger)', fontSize: '0.75rem' }}
                          title="Remove product from catalog"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}
