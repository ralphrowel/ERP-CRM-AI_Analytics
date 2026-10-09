import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Building2,
  CheckCircle,
  FileCheck,
  FileText,
  History,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Warehouse as WarehouseIcon,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Warehouse, warehousesApi } from '../api/inventory'
import { type Product, productsApi } from '../api/products'
import {
  type PurchaseOrder,
  type PurchaseOrderCreatePayload,
  type PurchaseOrderItemPayload,
  purchaseOrdersApi,
  type Supplier,
  suppliersApi,
} from '../api/purchasing'
import { type TaxRate, salesApi } from '../api/sales'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

interface LineDraft {
  product_id: number
  description: string
  uom: string
  quantity: string
  unit_cost: string
  tax_rate_id: number
}

export const PurchaseOrdersPage: React.FC = () => {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [supplierFilter, setSupplierFilter] = useState<string>('')
  const [warehouseFilter, setWarehouseFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master Data
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [taxRates, setTaxRates] = useState<TaxRate[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<PurchaseOrder | null>(null)
  const [closeReason, setCloseReason] = useState('')

  // Create Form State
  const [createSupplierId, setCreateSupplierId] = useState<number>(0)
  const [createWarehouseId, setCreateWarehouseId] = useState<number>(0)
  const [createOrderDate, setCreateOrderDate] = useState<string>(
    () => new Date().toISOString().split('T')[0]
  )
  const [createExpectedDate, setCreateExpectedDate] = useState<string>('')
  const [createNotes, setCreateNotes] = useState<string>('')
  const [createLines, setCreateLines] = useState<LineDraft[]>([])

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [poRes, supRes, whRes, prodRes, trRes] = await Promise.all([
        purchaseOrdersApi.list({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
          warehouse_id: warehouseFilter ? Number(warehouseFilter) : undefined,
        }),
        suppliersApi.list({ page: 1, page_size: 100, is_active: true }),
        warehousesApi.list(true),
        productsApi.list({ page: 1, page_size: 200 }),
        salesApi.listTaxRates(),
      ])
      setOrders(poRes.items)
      setTotal(poRes.total)
      setSuppliers(supRes.items)
      setWarehouses(whRes)
      setProducts(prodRes.items)
      setTaxRates(trRes)

      // Set default warehouse if none selected
      if (createWarehouseId === 0 && whRes.length > 0) {
        const def = whRes.find((w) => w.is_default) || whRes[0]
        setCreateWarehouseId(def.id)
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load purchase orders data.'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter, supplierFilter, warehouseFilter])

  const formatCurrency = (val: string | number) =>
    new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(
      typeof val === 'number' ? val : parseFloat(val || '0')
    )

  const getStatusBadge = (status: PurchaseOrder['status']) => {
    switch (status) {
      case 'draft':
        return <span className="badge badge-subtle">Draft</span>
      case 'sent':
        return <span className="badge badge-indigo">Sent</span>
      case 'partially_received':
        return <span className="badge badge-amber">Partially Received</span>
      case 'received':
        return <span className="badge badge-emerald">Received</span>
      case 'closed':
        return <span className="badge badge-cyan">Short-Closed</span>
      case 'cancelled':
        return <span className="badge badge-rose">Cancelled</span>
      default:
        return <span className="badge badge-subtle">{status}</span>
    }
  }

  // Create PO Line Management
  const handleAddLine = () => {
    const defaultProduct = products[0]
    const defaultTax = taxRates.find((t) => t.is_default) || taxRates[0]
    setCreateLines([
      ...createLines,
      {
        product_id: defaultProduct ? defaultProduct.id : 0,
        description: defaultProduct ? defaultProduct.name : '',
        uom: defaultProduct ? defaultProduct.uom : 'pc',
        quantity: '1',
        unit_cost: '0.00',
        tax_rate_id: defaultTax ? defaultTax.id : 1,
      },
    ])
  }

  const handleProductSelect = (index: number, productId: number) => {
    const prod = products.find((p) => p.id === productId)
    if (!prod) return
    const updated = [...createLines]
    updated[index].product_id = productId
    updated[index].description = prod.name
    updated[index].uom = prod.uom
    if (prod.tax_rate_id) {
      updated[index].tax_rate_id = prod.tax_rate_id
    }
    setCreateLines(updated)
  }

  const handleLineChange = (index: number, field: keyof LineDraft, value: string | number) => {
    const updated = [...createLines]
    // @ts-expect-error dynamic update
    updated[index][field] = value
    setCreateLines(updated)
  }

  const handleRemoveLine = (index: number) => {
    setCreateLines(createLines.filter((_, i) => i !== index))
  }

  // Calculated totals for draft lines
  const calculateDraftTotals = () => {
    let subtotal = 0
    let taxTotal = 0
    createLines.forEach((l) => {
      const q = parseFloat(l.quantity) || 0
      const c = parseFloat(l.unit_cost) || 0
      const net = Math.round(q * c * 100) / 100
      const rateObj = taxRates.find((t) => t.id === l.tax_rate_id)
      const rate = rateObj ? parseFloat(String(rateObj.rate)) : 0.12
      const tax = Math.round(net * rate * 100) / 100
      subtotal += net
      taxTotal += tax
    })
    return {
      subtotal,
      taxTotal,
      grandTotal: subtotal + taxTotal,
    }
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createSupplierId) {
      setGeneralError(new Error('Please select a supplier.'))
      return
    }
    if (!createWarehouseId) {
      setGeneralError(new Error('Please select a delivery warehouse.'))
      return
    }
    if (createLines.length === 0) {
      setGeneralError(new Error('Purchase order must contain at least one line item.'))
      return
    }

    const payloadItems: PurchaseOrderItemPayload[] = createLines.map((l) => ({
      product_id: l.product_id,
      description: l.description,
      uom: l.uom,
      quantity: parseFloat(l.quantity) || 1,
      unit_cost: parseFloat(l.unit_cost) || 0,
      tax_rate_id: l.tax_rate_id,
    }))

    const payload: PurchaseOrderCreatePayload = {
      supplier_id: createSupplierId,
      warehouse_id: createWarehouseId,
      order_date: createOrderDate,
      expected_date: createExpectedDate || undefined,
      notes: createNotes || undefined,
      items: payloadItems,
    }

    try {
      const created = await purchaseOrdersApi.create(payload)
      setIsCreateOpen(false)
      setCreateLines([])
      setCreateNotes('')
      setCreateExpectedDate('')
      setSuccessMessage(`Purchase Order ${created.po_no} created successfully!`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create purchase order.'))
      }
    }
  }

  // PO Actions
  const handleSendPO = async (po: PurchaseOrder) => {
    if (!confirm(`Send Purchase Order ${po.po_no} to supplier ${po.supplier_name}? This will lock addresses and payment terms.`)) return
    try {
      await purchaseOrdersApi.send(po.id)
      setSuccessMessage(`Purchase Order ${po.po_no} transitioned to SENT!`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Version conflict: Purchase Order was updated elsewhere. Please reload.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to send purchase order.'))
      }
    }
  }

  const handleCancelPO = async (po: PurchaseOrder) => {
    if (!confirm(`Are you sure you want to cancel Purchase Order ${po.po_no}? This action cannot be reversed.`)) return
    try {
      await purchaseOrdersApi.cancel(po.id)
      setSuccessMessage(`Purchase Order ${po.po_no} was cancelled.`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Version conflict: Purchase Order was updated elsewhere. Please reload.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to cancel purchase order.'))
      }
    }
  }

  const handleOpenCloseModal = (po: PurchaseOrder) => {
    setSelectedOrder(po)
    setCloseReason('')
    setIsCloseModalOpen(true)
  }

  const handleCloseSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrder) return
    if (!closeReason || closeReason.trim().length < 3) {
      setGeneralError(new Error('A short-close reason of at least 3 characters is required.'))
      return
    }
    try {
      await purchaseOrdersApi.close(selectedOrder.id, closeReason.trim())
      setIsCloseModalOpen(false)
      setSelectedOrder(null)
      setSuccessMessage(`Purchase Order was short-closed.`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Version conflict: Record was updated in another session.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to short-close purchase order.'))
      }
    }
  }

  const handleViewDetails = (po: PurchaseOrder) => {
    setSelectedOrder(po)
    setIsDetailsOpen(true)
  }

  const draftTotals = calculateDraftTotals()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc' }}>
            Purchase Orders (Procurement)
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Procurement commitments, supplier contractual snapshots, VAT calculations, and inbound receipt tracking
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => loadData()} className="btn btn-secondary" title="Refresh">
            <RefreshCw size={15} /> Refresh
          </button>
          <button
            id="create-po-btn"
            onClick={() => {
              if (suppliers.length === 0) {
                setGeneralError(new Error('Please register at least one active supplier first.'))
                return
              }
              setCreateSupplierId(suppliers[0]?.id || 0)
              setCreateLines([])
              setIsCreateOpen(true)
              handleAddLine()
            }}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Plus size={16} /> New Purchase Order
          </button>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="badge badge-emerald" style={{ padding: '0.75rem 1rem', fontSize: '0.875rem' }}>
          <CheckCircle size={16} /> {successMessage}
        </div>
      )}
      {conflictError && <ConflictAlert message={conflictError} onReload={() => loadData()} />}
      {generalError && <ProblemAlert error={generalError} onDismiss={() => setGeneralError(null)} />}

      {/* Filter Bar */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Status:</label>
          <select
            id="po-status-filter"
            className="input"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            style={{ minWidth: '150px' }}
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="partially_received">Partially Received</option>
            <option value="received">Fully Received</option>
            <option value="closed">Short-Closed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Supplier:</label>
          <select
            id="po-supplier-filter"
            className="input"
            value={supplierFilter}
            onChange={(e) => {
              setSupplierFilter(e.target.value)
              setPage(1)
            }}
            style={{ minWidth: '180px' }}
          >
            <option value="">All Suppliers</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.supplier_no})
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Warehouse:</label>
          <select
            id="po-warehouse-filter"
            className="input"
            value={warehouseFilter}
            onChange={(e) => {
              setWarehouseFilter(e.target.value)
              setPage(1)
            }}
            style={{ minWidth: '160px' }}
          >
            <option value="">All Warehouses</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.code} - {w.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Orders Table */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.02)',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              <th style={{ padding: '0.85rem 1rem' }}>PO Number</th>
              <th style={{ padding: '0.85rem 1rem' }}>Supplier</th>
              <th style={{ padding: '0.85rem 1rem' }}>Order Date</th>
              <th style={{ padding: '0.85rem 1rem' }}>Destination WH</th>
              <th style={{ padding: '0.85rem 1rem' }}>Status</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Grand Total (₱)</th>
              <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  <RefreshCw className="animate-spin" size={24} style={{ margin: '0 auto 0.5rem' }} />
                  <div>Loading purchase orders...</div>
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  <FileText size={36} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                  <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>No purchase orders found</div>
                  <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                    Create your first purchase order to initiate procurement.
                  </div>
                </td>
              </tr>
            ) : (
              orders.map((po) => (
                <tr
                  key={po.id}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    fontSize: '0.875rem',
                    transition: 'background-color 0.15s',
                  }}
                  className="table-row-hover"
                >
                  <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontWeight: 600, color: '#a5b4fc' }}>
                    <span
                      id={`po-row-${po.po_no}`}
                      onClick={() => handleViewDetails(po)}
                      style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      title="Click to view full PO details"
                    >
                      {po.po_no}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ fontWeight: 600, color: '#f8fafc' }}>
                      {po.supplier_name || `Supplier #${po.supplier_id}`}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      {po.items.length} line item{po.items.length !== 1 ? 's' : ''}
                    </div>
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                    {po.order_date}
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span
                      style={{
                        padding: '0.2rem 0.5rem',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        color: '#a5b4fc',
                        fontSize: '0.75rem',
                        fontFamily: 'monospace',
                      }}
                    >
                      {po.warehouse_code || 'DEFAULT'}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>{getStatusBadge(po.status)}</td>
                  <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: '0.9rem', color: '#38bdf8' }}>
                    {formatCurrency(po.grand_total)}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.35rem' }}>
                      <button
                        id={`po-view-btn-${po.id}`}
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                        title="View PO Details"
                        onClick={() => handleViewDetails(po)}
                      >
                        <FileText size={13} />
                      </button>
                      <button
                        id={`po-history-btn-${po.id}`}
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                        title="Status History Audit Trail"
                        onClick={() => {
                          setSelectedOrder(po)
                          setIsHistoryOpen(true)
                        }}
                      >
                        <History size={13} />
                      </button>

                      {/* State transitions */}
                      {po.status === 'draft' && (
                        <>
                          <button
                            id={`po-send-btn-${po.id}`}
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem' }}
                            onClick={() => handleSendPO(po)}
                            title="Send PO to Supplier (Snapshots Addresses & Terms)"
                          >
                            <Send size={12} /> Send
                          </button>
                          <button
                            id={`po-cancel-btn-${po.id}`}
                            className="btn btn-secondary"
                            style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--danger)' }}
                            onClick={() => handleCancelPO(po)}
                            title="Cancel Purchase Order"
                          >
                            <XCircle size={13} />
                          </button>
                        </>
                      )}

                      {po.status === 'sent' && (
                        <button
                          id={`po-cancel-btn-${po.id}`}
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--danger)' }}
                          onClick={() => handleCancelPO(po)}
                          title="Cancel PO (Zero items received)"
                        >
                          <XCircle size={13} /> Cancel
                        </button>
                      )}

                      {po.status === 'partially_received' && (
                        <button
                          id={`po-close-btn-${po.id}`}
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem', color: '#38bdf8' }}
                          onClick={() => handleOpenCloseModal(po)}
                          title="Short-Close Purchase Order (Supplier cannot deliver remainder)"
                        >
                          <FileCheck size={13} /> Short-Close
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

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
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} orders
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

      {/* CREATE PURCHASE ORDER MODAL */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create New Purchase Order"
      >
        <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">
                Supplier <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <select
                id="create-po-supplier"
                className="input"
                required
                value={createSupplierId}
                onChange={(e) => setCreateSupplierId(Number(e.target.value))}
              >
                <option value={0}>Select a supplier...</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.supplier_no}) · Net {s.payment_terms_days}d
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label">
                Delivery Destination Warehouse <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <select
                id="create-po-warehouse"
                className="input"
                required
                value={createWarehouseId}
                onChange={(e) => setCreateWarehouseId(Number(e.target.value))}
              >
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    [{w.code}] {w.name} {w.is_default ? '(Default)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="label">Order Date</label>
              <input
                id="create-po-date"
                type="date"
                className="input"
                required
                value={createOrderDate}
                onChange={(e) => setCreateOrderDate(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Expected Delivery Date</label>
              <input
                id="create-po-expected-date"
                type="date"
                className="input"
                value={createExpectedDate}
                onChange={(e) => setCreateExpectedDate(e.target.value)}
              />
            </div>
          </div>

          {/* Line Items Editor */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label className="label" style={{ margin: 0, fontWeight: 700 }}>
                Order Line Items ({createLines.length})
              </label>
              <button
                type="button"
                id="po-add-line-btn"
                onClick={handleAddLine}
                className="btn btn-secondary"
                style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
              >
                <Plus size={14} /> Add Line
              </button>
            </div>

            <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'rgba(255,255,255,0.02)', textAlign: 'left', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '0.5rem 0.75rem' }}>Product</th>
                    <th style={{ padding: '0.5rem', width: '90px' }}>Qty</th>
                    <th style={{ padding: '0.5rem', width: '70px' }}>UoM</th>
                    <th style={{ padding: '0.5rem', width: '110px' }}>Unit Cost (₱)</th>
                    <th style={{ padding: '0.5rem', width: '110px' }}>Tax Rate</th>
                    <th style={{ padding: '0.5rem', width: '90px', textAlign: 'right' }}>Net (₱)</th>
                    <th style={{ padding: '0.5rem', width: '40px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {createLines.map((line, idx) => {
                    const q = parseFloat(line.quantity) || 0
                    const c = parseFloat(line.unit_cost) || 0
                    const lineNet = Math.round(q * c * 100) / 100
                    return (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.5rem 0.75rem' }}>
                          <select
                            className="input"
                            style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                            value={line.product_id}
                            onChange={(e) => handleProductSelect(idx, Number(e.target.value))}
                          >
                            {products.map((p) => (
                              <option key={p.id} value={p.id}>
                                [{p.sku}] {p.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number"
                            step="0.001"
                            min="0.001"
                            className="input"
                            style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                            value={line.quantity}
                            onChange={(e) => handleLineChange(idx, 'quantity', e.target.value)}
                          />
                        </td>
                        <td style={{ padding: '0.5rem', color: 'var(--text-muted)' }}>
                          {line.uom}
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className="input"
                            style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                            value={line.unit_cost}
                            onChange={(e) => handleLineChange(idx, 'unit_cost', e.target.value)}
                          />
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <select
                            className="input"
                            style={{ fontSize: '0.8rem', padding: '0.35rem' }}
                            value={line.tax_rate_id}
                            onChange={(e) => handleLineChange(idx, 'tax_rate_id', Number(e.target.value))}
                          >
                            {taxRates.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name} ({(parseFloat(String(t.rate)) * 100).toFixed(0)}%)
                              </option>
                            ))}
                          </select>
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>
                          ₱{lineNet.toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                          <button
                            type="button"
                            onClick={() => handleRemoveLine(idx)}
                            style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}
                            title="Remove line"
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pricing Totals Box */}
          <div
            style={{
              padding: '0.85rem 1rem',
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '2rem',
              fontSize: '0.875rem',
            }}
          >
            <div>
              <span style={{ color: 'var(--text-dim)' }}>Subtotal: </span>
              <strong>₱{draftTotals.subtotal.toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-dim)' }}>Input Tax (VAT): </span>
              <strong>₱{draftTotals.taxTotal.toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-dim)' }}>Grand Total: </span>
              <strong style={{ color: '#38bdf8', fontSize: '1rem' }}>
                ₱{draftTotals.grandTotal.toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </strong>
            </div>
          </div>

          <div>
            <label className="label">Notes / Terms</label>
            <textarea
              className="input"
              rows={2}
              value={createNotes}
              onChange={(e) => setCreateNotes(e.target.value)}
              placeholder="e.g. Include Certificate of Analysis and Packing List."
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setIsCreateOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-create-po-btn" type="submit" className="btn btn-primary">
              Create Purchase Order
            </button>
          </div>
        </form>
      </Modal>

      {/* VIEW DETAILS MODAL */}
      <Modal
        isOpen={isDetailsOpen}
        onClose={() => setIsDetailsOpen(false)}
        title={`Purchase Order: ${selectedOrder?.po_no}`}
      >
        {selectedOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Status & Highlights */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.75rem 1rem',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Lifecycle Status:</span>
                {getStatusBadge(selectedOrder.status)}
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                Version: <span style={{ fontFamily: 'monospace', color: '#a5b4fc' }}>v{selectedOrder.version}</span>
              </div>
            </div>

            {/* Snapshots Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div
                style={{
                  padding: '0.85rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', color: 'var(--text-main)', fontWeight: 600, fontSize: '0.85rem' }}>
                  <Building2 size={15} /> Supplier Details & Terms
                </div>
                <div style={{ fontSize: '0.85rem', color: '#f8fafc', fontWeight: 600 }}>
                  {selectedOrder.supplier_name}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                  Snapshot Address: {selectedOrder.supplier_address_snapshot || 'None registered'}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  Payment Terms: Net {selectedOrder.payment_terms_days_snapshot} Days
                </div>
              </div>

              <div
                style={{
                  padding: '0.85rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', color: 'var(--text-main)', fontWeight: 600, fontSize: '0.85rem' }}>
                  <WarehouseIcon size={15} /> Delivery Destination
                </div>
                <div style={{ fontSize: '0.85rem', color: '#f8fafc', fontWeight: 600 }}>
                  [{selectedOrder.warehouse_code}] {selectedOrder.warehouse_name}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                  Warehouse Address: {selectedOrder.warehouse_address_snapshot || 'Default warehouse location'}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  Order Date: {selectedOrder.order_date} {selectedOrder.expected_date ? `· Expected: ${selectedOrder.expected_date}` : ''}
                </div>
              </div>
            </div>

            {/* Items Table */}
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: 'var(--text-main)' }}>
                Purchased Line Items
              </h4>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)', textAlign: 'left' }}>
                    <th style={{ padding: '0.5rem' }}>#</th>
                    <th style={{ padding: '0.5rem' }}>Product / SKU</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Ordered</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Received</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Unit Cost</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Line Net</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Tax</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Line Total</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedOrder.items.map((it) => (
                    <tr key={it.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '0.5rem', color: 'var(--text-dim)' }}>{it.line_no}</td>
                      <td style={{ padding: '0.5rem' }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{it.product_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{it.product_sku} · {it.uom}</div>
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>
                        {Number(it.quantity).toLocaleString()}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                        <span
                          className={`badge ${Number(it.quantity_received) >= Number(it.quantity) ? 'badge-emerald' : Number(it.quantity_received) > 0 ? 'badge-amber' : 'badge-subtle'}`}
                          style={{ fontSize: '0.75rem' }}
                        >
                          {Number(it.quantity_received).toLocaleString()}
                        </span>
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                        {formatCurrency(it.unit_cost)}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                        {formatCurrency(it.line_net)}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-dim)' }}>
                        {formatCurrency(it.line_tax)}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, color: '#38bdf8' }}>
                        {formatCurrency(it.line_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Totals Summary */}
            <div
              style={{
                padding: '0.85rem 1.25rem',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '2.5rem',
                fontSize: '0.9rem',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-dim)' }}>Subtotal: </span>
                <strong>{formatCurrency(selectedOrder.subtotal)}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-dim)' }}>Input Tax: </span>
                <strong>{formatCurrency(selectedOrder.tax_total)}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-dim)' }}>Grand Total: </span>
                <strong style={{ color: '#38bdf8', fontSize: '1.05rem' }}>
                  {formatCurrency(selectedOrder.grand_total)}
                </strong>
              </div>
            </div>

            {selectedOrder.notes && (
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', backgroundColor: 'rgba(255,255,255,0.01)', padding: '0.75rem', borderRadius: '6px' }}>
                <strong>PO Notes:</strong> {selectedOrder.notes}
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* SHORT-CLOSE MODAL */}
      <Modal
        isOpen={isCloseModalOpen}
        onClose={() => setIsCloseModalOpen(false)}
        title={`Short-Close Purchase Order: ${selectedOrder?.po_no}`}
      >
        <form onSubmit={handleCloseSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ padding: '0.75rem', backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', color: '#fbbf24', fontSize: '0.85rem' }}>
            <AlertTriangle size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
            Short-closing this purchase order marks remaining unfulfilled quantities as cancelled. A business justification is required.
          </div>

          <div>
            <label className="label">
              Short-Close Reason <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <textarea
              id="short-close-reason-input"
              className="input"
              required
              rows={3}
              value={closeReason}
              onChange={(e) => setCloseReason(e.target.value)}
              placeholder="e.g. Supplier notified discontinuation of remaining balance."
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={() => setIsCloseModalOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-short-close-btn" type="submit" className="btn btn-primary" style={{ backgroundColor: '#0284c7' }}>
              Confirm Short-Close
            </button>
          </div>
        </form>
      </Modal>

      {/* AUDIT TRAIL / STATUS HISTORY MODAL */}
      <Modal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        title={`Audit Trail: ${selectedOrder?.po_no}`}
      >
        {selectedOrder && (
          <StatusHistoryTimeline entityType="purchase_order" entityId={selectedOrder.id} />
        )}
      </Modal>
    </div>
  )
}
