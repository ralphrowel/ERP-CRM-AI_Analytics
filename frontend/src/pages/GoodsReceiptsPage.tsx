import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Boxes,
  CheckCircle,
  FileCheck,
  Plus,
  RefreshCw,
  Truck,
  Warehouse as WarehouseIcon,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Warehouse, warehousesApi } from '../api/inventory'
import {
  type GoodsReceipt,
  type GoodsReceiptCreatePayload,
  goodsReceiptsApi,
  type PurchaseOrder,
  purchaseOrdersApi,
} from '../api/purchasing'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

interface ReceiptLineDraft {
  po_item_id: number
  product_id: number
  product_name: string
  product_sku: string
  ordered_qty: number
  already_received_qty: number
  remaining_qty: number
  receive_qty: string
}

export const GoodsReceiptsPage: React.FC = () => {
  const [receipts, setReceipts] = useState<GoodsReceipt[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [warehouseFilter, setWarehouseFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master Data
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [candidatePOs, setCandidatePOs] = useState<PurchaseOrder[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [selectedReceipt, setSelectedReceipt] = useState<GoodsReceipt | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Create Form State
  const [selectedPoId, setSelectedPoId] = useState<number>(0)
  const [deliveryRef, setDeliveryRef] = useState<string>('')
  const [receiptNotes, setReceiptNotes] = useState<string>('')
  const [receiptLines, setReceiptLines] = useState<ReceiptLineDraft[]>([])
  const [autoPost, setAutoPost] = useState<boolean>(true)

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [grRes, whRes] = await Promise.all([
        goodsReceiptsApi.list({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          warehouse_id: warehouseFilter ? Number(warehouseFilter) : undefined,
        }),
        warehousesApi.list(true),
      ])
      setReceipts(grRes.items)
      setTotal(grRes.total)
      setWarehouses(whRes)
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.message)
      } else {
        setGeneralError(err as ApiError | Error)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const loadCandidatePOs = async () => {
    try {
      // Fetch open POs (sent or partially_received)
      const [sentRes, partRes] = await Promise.all([
        purchaseOrdersApi.list({ status: 'sent', page_size: 100 }),
        purchaseOrdersApi.list({ status: 'partially_received', page_size: 100 }),
      ])
      setCandidatePOs([...sentRes.items, ...partRes.items])
    } catch {
      // Non-fatal
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter, warehouseFilter])

  const openCreateModal = async () => {
    setSelectedPoId(0)
    setDeliveryRef('')
    setReceiptNotes('')
    setReceiptLines([])
    setAutoPost(true)
    await loadCandidatePOs()
    setIsCreateOpen(true)
  }

  const handlePoChange = async (poId: number) => {
    setSelectedPoId(poId)
    if (!poId) {
      setReceiptLines([])
      return
    }

    try {
      const fullPo = await purchaseOrdersApi.get(poId)
      const lines: ReceiptLineDraft[] = fullPo.items.map((item) => {
        const ord = Number(item.quantity)
        const rec = Number(item.quantity_received || 0)
        const rem = Math.max(0, ord - rec)
        return {
          po_item_id: item.id,
          product_id: item.product_id,
          product_name: item.product_name || `Product #${item.product_id}`,
          product_sku: item.product_sku || '',
          ordered_qty: ord,
          already_received_qty: rec,
          remaining_qty: rem,
          receive_qty: rem.toString(),
        }
      })
      setReceiptLines(lines)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPoId) {
      setGeneralError(new Error('Please select an active Purchase Order'))
      return
    }

    // Filter lines where receive_qty > 0
    const itemsToReceive = receiptLines
      .map((l) => ({
        purchase_order_item_id: l.po_item_id,
        quantity: parseFloat(l.receive_qty) || 0,
      }))
      .filter((l) => l.quantity > 0)

    if (itemsToReceive.length === 0) {
      setGeneralError(new Error('At least one item must have a receive quantity greater than 0.'))
      return
    }

    // Over-receipt client check
    for (const line of receiptLines) {
      const qty = parseFloat(line.receive_qty) || 0
      if (qty > line.remaining_qty) {
        setGeneralError(
          new Error(
            `Line ${line.product_name} cannot receive ${qty} (exceeds remaining ${line.remaining_qty}). Zero over-receipt enforced.`
          )
        )
        return
      }
    }

    const payload: GoodsReceiptCreatePayload = {
      purchase_order_id: selectedPoId,
      supplier_delivery_ref: deliveryRef.trim() || undefined,
      notes: receiptNotes.trim() || undefined,
      items: itemsToReceive,
    }

    setIsSubmitting(true)
    setConflictError(null)
    setGeneralError(null)

    try {
      const created = await goodsReceiptsApi.create(payload)
      if (autoPost) {
        await goodsReceiptsApi.post(created.id)
        setSuccessMessage(`Goods Receipt ${created.gr_no} created and posted to inventory successfully.`)
      } else {
        setSuccessMessage(`Goods Receipt ${created.gr_no} saved as draft.`)
      }
      setIsCreateOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.message)
      } else {
        setGeneralError(err as ApiError | Error)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handlePostReceipt = async (receipt: GoodsReceipt) => {
    if (!window.confirm(`Post Goods Receipt ${receipt.gr_no} to inventory? This will update stock levels and Weighted Average Cost (WAC).`)) {
      return
    }

    setIsLoading(true)
    try {
      await goodsReceiptsApi.post(receipt.id)
      setSuccessMessage(`Goods Receipt ${receipt.gr_no} posted successfully. Inventory & WAC updated.`)
      if (selectedReceipt?.id === receipt.id) {
        const updated = await goodsReceiptsApi.get(receipt.id)
        setSelectedReceipt(updated)
      }
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.message)
      } else {
        setGeneralError(err as ApiError | Error)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancelReceipt = async (receipt: GoodsReceipt) => {
    if (!window.confirm(`Cancel draft Goods Receipt ${receipt.gr_no}?`)) {
      return
    }

    setIsLoading(true)
    try {
      await goodsReceiptsApi.cancel(receipt.id)
      setSuccessMessage(`Goods Receipt ${receipt.gr_no} cancelled.`)
      if (selectedReceipt?.id === receipt.id) {
        setIsDetailsOpen(false)
      }
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.message)
      } else {
        setGeneralError(err as ApiError | Error)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const openDetailsModal = async (receipt: GoodsReceipt) => {
    try {
      const full = await goodsReceiptsApi.get(receipt.id)
      setSelectedReceipt(full)
      setIsDetailsOpen(true)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'posted':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: '#10b981',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <CheckCircle size={12} /> Posted
          </span>
        )
      case 'draft':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(245, 158, 11, 0.15)',
              color: '#f59e0b',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <AlertTriangle size={12} /> Draft
          </span>
        )
      case 'cancelled':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <XCircle size={12} /> Cancelled
          </span>
        )
      default:
        return <span>{status}</span>
    }
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '2rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                boxShadow: '0 4px 12px rgba(14, 165, 233, 0.3)',
              }}
            >
              <Boxes size={22} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-main)' }}>
                Goods Receipts & Stock Intake
              </h1>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Receive delivery batches against Purchase Orders, enforce strict zero-over-receipt limits, and recalculate inventory WAC.
              </p>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => loadData()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.625rem 1rem',
              backgroundColor: 'var(--bg-card)',
              color: 'var(--text-main)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              fontSize: '0.875rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
          <button
            onClick={openCreateModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.625rem 1.25rem',
              background: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(14, 165, 233, 0.3)',
            }}
          >
            <Plus size={16} /> Receive Delivery
          </button>
        </div>
      </div>

      {/* Notifications */}
      {conflictError && <ConflictAlert message={conflictError} onReload={loadData} />}
      {generalError && <ProblemAlert error={generalError} />}
      {successMessage && (
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            borderRadius: '8px',
            color: '#10b981',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <CheckCircle size={18} />
            <span>{successMessage}</span>
          </div>
          <button
            onClick={() => setSuccessMessage(null)}
            style={{ background: 'none', border: 'none', color: '#10b981', cursor: 'pointer' }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Filters Bar */}
      <div
        style={{
          display: 'flex',
          gap: '1rem',
          backgroundColor: 'var(--bg-card)',
          padding: '1rem 1.25rem',
          borderRadius: '10px',
          border: '1px solid var(--border-subtle)',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: 'var(--bg-input)',
              color: 'var(--text-main)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              fontSize: '0.85rem',
            }}
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="posted">Posted</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Warehouse:</span>
          <select
            value={warehouseFilter}
            onChange={(e) => {
              setWarehouseFilter(e.target.value)
              setPage(1)
            }}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: 'var(--bg-input)',
              color: 'var(--text-main)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              fontSize: '0.85rem',
            }}
          >
            <option value="">All Warehouses</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.code} - {w.name}
              </option>
            ))}
          </select>
        </div>

        {(statusFilter || warehouseFilter) && (
          <button
            onClick={() => {
              setStatusFilter('')
              setWarehouseFilter('')
              setPage(1)
            }}
            style={{
              fontSize: '0.8rem',
              color: 'var(--text-muted)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Table */}
      <div
        style={{
          backgroundColor: 'var(--bg-card)',
          borderRadius: '12px',
          border: '1px solid var(--border-subtle)',
          overflow: 'hidden',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'rgba(255, 255, 255, 0.02)' }}>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>GR Number</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Purchase Order</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Warehouse</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Delivery Ref</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Status</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Received At</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Items</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Loading Goods Receipts...
                  </td>
                </tr>
              ) : receipts.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No goods receipts found. Create one by clicking "Receive Delivery".
                  </td>
                </tr>
              ) : (
                receipts.map((gr) => (
                  <tr
                    key={gr.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background-color 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.02)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: 'var(--primary)' }}>
                      {gr.gr_no}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                          color: 'var(--text-main)',
                        }}
                      >
                        <FileCheck size={14} style={{ color: 'var(--primary)' }} />
                        {gr.po_no || `PO #${gr.purchase_order_id}`}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', color: 'var(--text-main)' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                        <WarehouseIcon size={14} style={{ color: 'var(--text-muted)' }} />
                        {gr.warehouse_code ? `${gr.warehouse_code} - ${gr.warehouse_name}` : `Warehouse #${gr.warehouse_id}`}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', color: 'var(--text-muted)' }}>
                      {gr.supplier_delivery_ref ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                          <Truck size={13} /> {gr.supplier_delivery_ref}
                        </span>
                      ) : (
                        <span style={{ opacity: 0.5 }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>{getStatusBadge(gr.status)}</td>
                    <td style={{ padding: '1rem 1.25rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      {gr.received_at ? new Date(gr.received_at).toLocaleString() : 'Pending'}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span
                        style={{
                          backgroundColor: 'rgba(255, 255, 255, 0.05)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                        }}
                      >
                        {gr.items?.length || 0} line(s)
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => openDetailsModal(gr)}
                          style={{
                            padding: '0.35rem 0.7rem',
                            backgroundColor: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: '6px',
                            color: 'var(--text-main)',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                          }}
                        >
                          View Details
                        </button>
                        {gr.status === 'draft' && (
                          <>
                            <button
                              onClick={() => handlePostReceipt(gr)}
                              style={{
                                padding: '0.35rem 0.7rem',
                                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                border: '1px solid rgba(16, 185, 129, 0.3)',
                                borderRadius: '6px',
                                color: '#10b981',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                cursor: 'pointer',
                              }}
                            >
                              Post Stock
                            </button>
                            <button
                              onClick={() => handleCancelReceipt(gr)}
                              style={{
                                padding: '0.35rem 0.7rem',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.25)',
                                borderRadius: '6px',
                                color: '#ef4444',
                                fontSize: '0.75rem',
                                cursor: 'pointer',
                              }}
                            >
                              Cancel
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > pageSize && (
          <div
            style={{
              padding: '1rem 1.5rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid var(--border-subtle)',
              fontSize: '0.875rem',
            }}
          >
            <span style={{ color: 'var(--text-muted)' }}>
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} receipts
            </span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                style={{
                  padding: '0.35rem 0.75rem',
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-main)',
                  cursor: page <= 1 ? 'not-allowed' : 'pointer',
                  opacity: page <= 1 ? 0.5 : 1,
                }}
              >
                Previous
              </button>
              <button
                disabled={page * pageSize >= total}
                onClick={() => setPage(page + 1)}
                style={{
                  padding: '0.35rem 0.75rem',
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  color: 'var(--text-main)',
                  cursor: page * pageSize >= total ? 'not-allowed' : 'pointer',
                  opacity: page * pageSize >= total ? 0.5 : 1,
                }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: New Goods Receipt */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Receive Delivery (Goods Receipt)">
        <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
              Select Active Purchase Order *
            </label>
            <select
              value={selectedPoId}
              onChange={(e) => handlePoChange(Number(e.target.value))}
              required
              style={{
                width: '100%',
                padding: '0.625rem',
                backgroundColor: 'var(--bg-input)',
                color: 'var(--text-main)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                fontSize: '0.875rem',
              }}
            >
              <option value={0}>-- Select Purchase Order (Sent / Partially Received) --</option>
              {candidatePOs.map((po) => (
                <option key={po.id} value={po.id}>
                  {po.po_no} | {po.supplier_name || `Supplier #${po.supplier_id}`} | {po.warehouse_name || `Warehouse #${po.warehouse_id}`} ({po.status})
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Supplier Delivery Ref / BOL #
              </label>
              <input
                type="text"
                value={deliveryRef}
                onChange={(e) => setDeliveryRef(e.target.value)}
                placeholder="e.g. WAYBILL-98214"
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Intake Notes
              </label>
              <input
                type="text"
                value={receiptNotes}
                onChange={(e) => setReceiptNotes(e.target.value)}
                placeholder="e.g. Inspected dock bay 3, pallets in good order"
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                }}
              />
            </div>
          </div>

          {/* Line items table */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, margin: 0 }}>
                Receiving Line Quantities
              </label>
              <span style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: 500 }}>
                Strict zero over-receipt protection active
              </span>
            </div>

            {receiptLines.length === 0 ? (
              <div
                style={{
                  padding: '1.5rem',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '8px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '0.85rem',
                }}
              >
                Select a Purchase Order above to view items to receive.
              </div>
            ) : (
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Product</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Ordered</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Received</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Remaining</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)', width: '130px' }}>
                        Qty to Receive
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {receiptLines.map((line, idx) => (
                      <tr key={line.po_item_id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.6rem 0.75rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{line.product_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>SKU: {line.product_sku || 'N/A'}</div>
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>{line.ordered_qty}</td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          {line.already_received_qty}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, color: line.remaining_qty > 0 ? '#38bdf8' : 'var(--text-muted)' }}>
                          {line.remaining_qty}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                          <input
                            type="number"
                            min="0"
                            max={line.remaining_qty}
                            step="any"
                            value={line.receive_qty}
                            onChange={(e) => {
                              const val = e.target.value
                              setReceiptLines((prev) =>
                                prev.map((l, i) => (i === idx ? { ...l, receive_qty: val } : l))
                              )
                            }}
                            style={{
                              width: '100px',
                              padding: '0.4rem',
                              backgroundColor: 'var(--bg-input)',
                              color: 'var(--text-main)',
                              border:
                                parseFloat(line.receive_qty) > line.remaining_qty
                                  ? '1px solid #ef4444'
                                  : '1px solid var(--border-subtle)',
                              borderRadius: '6px',
                              textAlign: 'right',
                              fontSize: '0.85rem',
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Auto-post checkbox */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
            <input
              type="checkbox"
              id="autoPost"
              checked={autoPost}
              onChange={(e) => setAutoPost(e.target.checked)}
              style={{ width: '16px', height: '16px', cursor: 'pointer' }}
            />
            <label htmlFor="autoPost" style={{ fontSize: '0.85rem', cursor: 'pointer', color: 'var(--text-main)' }}>
              <strong>Post immediately upon creation</strong> (updates stock ledger and recalculates Weighted Average Cost now)
            </label>
          </div>

          {/* Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button
              type="button"
              onClick={() => setIsCreateOpen(false)}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: 'transparent',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || selectedPoId === 0}
              style={{
                padding: '0.625rem 1.5rem',
                background: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: isSubmitting || selectedPoId === 0 ? 'not-allowed' : 'pointer',
                opacity: isSubmitting || selectedPoId === 0 ? 0.6 : 1,
              }}
            >
              {isSubmitting ? 'Processing...' : autoPost ? 'Create & Post Receipt' : 'Save as Draft'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Goods Receipt Details */}
      {selectedReceipt && (
        <Modal isOpen={isDetailsOpen} onClose={() => setIsDetailsOpen(false)} title={`Goods Receipt: ${selectedReceipt.gr_no}`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '1rem',
                backgroundColor: 'rgba(255, 255, 255, 0.02)',
                padding: '1rem',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Status</span>
                <div style={{ marginTop: '0.25rem' }}>{getStatusBadge(selectedReceipt.status)}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Purchase Order</span>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {selectedReceipt.po_no || `#${selectedReceipt.purchase_order_id}`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Warehouse</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  {selectedReceipt.warehouse_code ? `${selectedReceipt.warehouse_code} - ${selectedReceipt.warehouse_name}` : `#${selectedReceipt.warehouse_id}`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Delivery Ref</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  {selectedReceipt.supplier_delivery_ref || 'None'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Received Date</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>
                  {selectedReceipt.received_at ? new Date(selectedReceipt.received_at).toLocaleString() : 'Not posted'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Created At</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>
                  {new Date(selectedReceipt.created_at).toLocaleString()}
                </span>
              </div>
            </div>

            {selectedReceipt.notes && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '6px',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.85rem',
                }}
              >
                <strong style={{ color: 'var(--text-muted)' }}>Notes: </strong>
                <span>{selectedReceipt.notes}</span>
              </div>
            )}

            {/* Items table */}
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>Received Inventory Lines</h4>
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Item</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Qty Received</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Unit Cost</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Total Line Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedReceipt.items?.map((item) => {
                      const qty = Number(item.quantity)
                      const cost = Number(item.unit_cost)
                      const lineCost = (qty * cost).toFixed(2)
                      return (
                        <tr key={item.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '0.6rem 0.75rem' }}>
                            <div style={{ fontWeight: 600 }}>{item.product_name || `Product #${item.product_id}`}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              SKU: {item.product_sku || 'N/A'}
                            </div>
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, color: '#10b981' }}>
                            {qty}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                            ${cost.toFixed(4)}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600 }}>
                            ${lineCost}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
              <div>
                {selectedReceipt.status === 'posted' && (
                  <span style={{ fontSize: '0.8rem', color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <CheckCircle size={15} /> Physical stock successfully committed to ledger & WAC updated.
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                {selectedReceipt.status === 'draft' && (
                  <>
                    <button
                      onClick={() => handleCancelReceipt(selectedReceipt)}
                      style={{
                        padding: '0.625rem 1.25rem',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        color: '#ef4444',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                    >
                      Cancel Draft
                    </button>
                    <button
                      onClick={() => handlePostReceipt(selectedReceipt)}
                      style={{
                        padding: '0.625rem 1.25rem',
                        background: 'linear-gradient(135deg, #10b981, #059669)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontWeight: 600,
                        boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                      }}
                    >
                      Post Receipt to Inventory
                    </button>
                  </>
                )}
                <button
                  onClick={() => setIsDetailsOpen(false)}
                  style={{
                    padding: '0.625rem 1.25rem',
                    backgroundColor: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: 'var(--text-main)',
                    cursor: 'pointer',
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
