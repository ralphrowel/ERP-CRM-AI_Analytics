import React, { useEffect, useState } from 'react'
import {
  Building,
  CheckCircle,
  Clock,
  Edit2,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  User,
  UserX,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type Customer,
  type CustomerCreatePayload,
  customersApi,
  type CustomerUpdatePayload,
} from '../api/customers'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Errors & Conflict state
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null)

  // Form states
  const [formData, setFormData] = useState<CustomerCreatePayload>({
    name: '',
    customer_type: 'company',
    status: 'active',
    tin: '',
    email: '',
    phone: '',
    website: '',
    industry: '',
    payment_terms_days: 30,
    credit_limit: '50000.00',
    notes: '',
    initial_address: {
      address_type: 'billing',
      line1: '',
      city: 'Makati City',
      province: 'Metro Manila',
      postal_code: '1200',
      country_code: 'PH',
      is_default: true,
    },
  })

  const [editFormData, setEditFormData] = useState<{
    name: string
    customer_type: 'company' | 'individual'
    status: 'prospect' | 'active' | 'inactive'
    email: string
    phone: string
    payment_terms_days: number
    credit_limit: string
    version: number
  }>({
    name: '',
    customer_type: 'company',
    status: 'active',
    email: '',
    phone: '',
    payment_terms_days: 0,
    credit_limit: '',
    version: 1,
  })

  const loadCustomers = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const res = await customersApi.list({
        page,
        page_size: pageSize,
        search: searchTerm || undefined,
        status: statusFilter || undefined,
      })
      setCustomers(res.items)
      setTotal(res.total)
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadCustomers()
  }, [page, statusFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadCustomers()
  }

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault()
    setGeneralError(null)
    try {
      await customersApi.create(formData)
      setIsCreateOpen(false)
      loadCustomers()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const openEditModal = (cust: Customer) => {
    setSelectedCustomer(cust)
    setConflictError(null)
    setGeneralError(null)
    setEditFormData({
      name: cust.name,
      customer_type: cust.customer_type,
      status: cust.status,
      email: cust.email || '',
      phone: cust.phone || '',
      payment_terms_days: cust.payment_terms_days,
      credit_limit: cust.credit_limit || '',
      version: cust.version, // optimistic locking token
    })
    setIsEditOpen(true)
  }

  const handleUpdateCustomer = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCustomer) return
    setConflictError(null)
    setGeneralError(null)

    const payload: CustomerUpdatePayload = {
      name: editFormData.name,
      customer_type: editFormData.customer_type,
      status: editFormData.status,
      email: editFormData.email || undefined,
      phone: editFormData.phone || undefined,
      payment_terms_days: editFormData.payment_terms_days,
      credit_limit: editFormData.credit_limit || undefined,
      version: editFormData.version, // optimistic lock check
    }

    try {
      await customersApi.update(selectedCustomer.id, payload)
      setIsEditOpen(false)
      loadCustomers()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError(
            'This customer was modified by another transaction or browser tab. Please reload to see the updated record before trying again.'
          )
        } else {
          setGeneralError(err)
        }
      }
    }
  }

  const handleDeactivate = async (id: number) => {
    if (!confirm('Are you sure you want to deactivate this customer?')) return
    try {
      await customersApi.deactivate(id)
      loadCustomers()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <span className="badge badge-emerald"><CheckCircle size={12} /> Active</span>
      case 'prospect':
        return <span className="badge badge-amber"><Clock size={12} /> Prospect</span>
      case 'inactive':
        return <span className="badge badge-rose"><UserX size={12} /> Inactive</span>
      default:
        return <span className="badge badge-subtle">{status}</span>
    }
  }

  return (
    <div>
      {/* Page Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
            Customer Master Data
          </h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Manage commercial accounts, prospects, and addresses with optimistic concurrency control.
          </p>
        </div>

        <button
          id="btn-create-customer"
          onClick={() => setIsCreateOpen(true)}
          className="btn btn-primary"
        >
          <Plus size={16} /> New Customer
        </button>
      </div>

      {conflictError && <ConflictAlert onReload={loadCustomers} message={conflictError} />}
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
              id="customer-search-input"
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by name, code (CUS-...), email..."
              className="input-field"
              style={{ paddingLeft: '2.2rem' }}
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Filter
          </button>
        </form>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Status:</span>
          <select
            id="customer-status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            className="input-field"
            style={{ width: 'auto', padding: '0.4rem 0.75rem' }}
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="prospect">Prospect</option>
            <option value="inactive">Inactive</option>
          </select>

          <button onClick={loadCustomers} className="btn btn-secondary" title="Refresh">
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel erp-table-container">
        <table className="erp-table">
          <thead>
            <tr>
              <th>Customer No</th>
              <th>Customer Name</th>
              <th>Type</th>
              <th>Status</th>
              <th>Email / Contact</th>
              <th>Payment Terms</th>
              <th>Version</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-dim)' }}>
                  {isLoading ? 'Loading customers...' : 'No customer records found.'}
                </td>
              </tr>
            ) : (
              customers.map((c) => (
                <tr key={c.id}>
                  <td>
                    <span className="code-pill">{c.customer_no}</span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{c.name}</div>
                    {c.addresses && c.addresses.length > 0 && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '3px' }}>
                        <MapPin size={11} /> {c.addresses[0].city}, {c.addresses[0].province}
                      </div>
                    )}
                  </td>
                  <td>
                    <span style={{ fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {c.customer_type === 'company' ? <Building size={14} /> : <User size={14} />}
                      {c.customer_type}
                    </span>
                  </td>
                  <td>{getStatusBadge(c.status)}</td>
                  <td>
                    <div style={{ fontSize: '0.85rem' }}>{c.email || '—'}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{c.phone || ''}</div>
                  </td>
                  <td>
                    {c.payment_terms_days === 0 ? 'Cash on Delivery (0d)' : `${c.payment_terms_days} days`}
                  </td>
                  <td>
                    <span className="badge badge-subtle">v{c.version}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                      <button
                        onClick={() => openEditModal(c)}
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.65rem' }}
                        title="Edit Customer"
                      >
                        <Edit2 size={13} /> Edit
                      </button>
                      {c.status !== 'inactive' && (
                        <button
                          onClick={() => handleDeactivate(c.id)}
                          className="btn btn-danger"
                          style={{ padding: '0.35rem 0.65rem' }}
                          title="Deactivate"
                        >
                          <UserX size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
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
          Showing {customers.length} of {total} records
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

      {/* Create Customer Modal */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Customer" maxWidth="620px">
        <form onSubmit={handleCreateCustomer} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Customer Name *</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="input-field"
              placeholder="e.g. Acme Industrial Philippines, Inc."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Account Type</label>
              <select
                value={formData.customer_type}
                onChange={(e) => setFormData({ ...formData, customer_type: e.target.value as 'company' | 'individual' })}
                className="input-field"
              >
                <option value="company">Corporate / Company</option>
                <option value="individual">Individual</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Initial Status</label>
              <select
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value as 'active' | 'prospect' | 'inactive' })}
                className="input-field"
              >
                <option value="active">Active Customer</option>
                <option value="prospect">Prospect</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Email</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="input-field"
                placeholder="billing@acme.ph"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Phone</label>
              <input
                type="text"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                className="input-field"
                placeholder="+63 2 8123 4567"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Payment Terms (Days)</label>
              <input
                type="number"
                min="0"
                value={formData.payment_terms_days}
                onChange={(e) => setFormData({ ...formData, payment_terms_days: parseInt(e.target.value) || 0 })}
                className="input-field"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Credit Limit (₱ PHP)</label>
              <input
                type="text"
                value={formData.credit_limit}
                onChange={(e) => setFormData({ ...formData, credit_limit: e.target.value })}
                className="input-field"
                placeholder="50000.00"
              />
            </div>
          </div>

          {/* Initial Address */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.85rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', letterSpacing: '0.06em' }}>
              Primary Billing Address
            </span>
            <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <input
                type="text"
                value={formData.initial_address?.line1}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    initial_address: { ...formData.initial_address!, line1: e.target.value },
                  })
                }
                className="input-field"
                placeholder="Street Address / Building (Line 1)"
              />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <input
                  type="text"
                  value={formData.initial_address?.city}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      initial_address: { ...formData.initial_address!, city: e.target.value },
                    })
                  }
                  className="input-field"
                  placeholder="City (e.g. Makati)"
                />
                <input
                  type="text"
                  value={formData.initial_address?.province}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      initial_address: { ...formData.initial_address!, province: e.target.value },
                    })
                  }
                  className="input-field"
                  placeholder="Province (e.g. Metro Manila)"
                />
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsCreateOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Create Customer
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Customer Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`Edit Customer: ${selectedCustomer?.customer_no}`}>
        <form onSubmit={handleUpdateCustomer} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Customer Name</label>
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
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Status</label>
              <select
                value={editFormData.status}
                onChange={(e) =>
                  setEditFormData({ ...editFormData, status: e.target.value as 'active' | 'prospect' | 'inactive' })
                }
                className="input-field"
              >
                <option value="active">Active</option>
                <option value="prospect">Prospect</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Account Type</label>
              <select
                value={editFormData.customer_type}
                onChange={(e) =>
                  setEditFormData({ ...editFormData, customer_type: e.target.value as 'company' | 'individual' })
                }
                className="input-field"
              >
                <option value="company">Corporate</option>
                <option value="individual">Individual</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Email</label>
              <input
                type="email"
                value={editFormData.email}
                onChange={(e) => setEditFormData({ ...editFormData, email: e.target.value })}
                className="input-field"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Phone</label>
              <input
                type="text"
                value={editFormData.phone}
                onChange={(e) => setEditFormData({ ...editFormData, phone: e.target.value })}
                className="input-field"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Payment Terms (Days)</label>
              <input
                type="number"
                min="0"
                value={editFormData.payment_terms_days}
                onChange={(e) => setEditFormData({ ...editFormData, payment_terms_days: parseInt(e.target.value) || 0 })}
                className="input-field"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Credit Limit (₱)</label>
              <input
                type="text"
                value={editFormData.credit_limit}
                onChange={(e) => setEditFormData({ ...editFormData, credit_limit: e.target.value })}
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
            Concurrency Token: <strong>version {editFormData.version}</strong>. If another user saves first, this update will safely be rejected with HTTP 409 Conflict.
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsEditOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button id="save-customer-edit-btn" type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
