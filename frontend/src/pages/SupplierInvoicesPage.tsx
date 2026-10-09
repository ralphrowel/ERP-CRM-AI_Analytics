import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  DollarSign,
  FileCheck,
  Plus,
  RefreshCw,
  Scale,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type PurchaseOrder,
  purchaseOrdersApi,
  type Supplier,
  type SupplierInvoice,
  type SupplierInvoiceCreatePayload,
  type SupplierInvoiceItemPayload,
  supplierInvoicesApi,
  suppliersApi,
} from '../api/purchasing'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

interface BillLineDraft {
  po_item_id: number
  product_id: number
  product_name: string
  product_sku: string
  po_qty: number
  received_qty: number
  po_unit_cost: number
  billed_qty: string
  billed_unit_cost: string
}

export const SupplierInvoicesPage: React.FC = () => {
  const [invoices, setInvoices] = useState<SupplierInvoice[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [supplierFilter, setSupplierFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master Data
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [candidatePOs, setCandidatePOs] = useState<PurchaseOrder[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isVoidOpen, setIsVoidOpen] = useState(false)
  const [selectedInvoice, setSelectedInvoice] = useState<SupplierInvoice | null>(null)
  const [voidReason, setVoidReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Create Form State
  const [createPoId, setCreatePoId] = useState<number>(0)
  const [invoiceRef, setInvoiceRef] = useState<string>('')
  const [invoiceDate, setInvoiceDate] = useState<string>(() => new Date().toISOString().split('T')[0])
  const [dueDate, setDueDate] = useState<string>(() => {
    const d = new Date()
    d.setDate(d.getDate() + 30)
    return d.toISOString().split('T')[0]
  })
  const [invoiceNotes, setInvoiceNotes] = useState<string>('')
  const [billLines, setBillLines] = useState<BillLineDraft[]>([])

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [invRes, supRes] = await Promise.all([
        supplierInvoicesApi.list({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
        }),
        suppliersApi.list({ page: 1, page_size: 100 }),
      ])
      setInvoices(invRes.items)
      setTotal(invRes.total)
      setSuppliers(supRes.items)
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
      // POs that are sent, partially_received, received
      const [sentRes, partRes, recRes] = await Promise.all([
        purchaseOrdersApi.list({ status: 'sent', page_size: 100 }),
        purchaseOrdersApi.list({ status: 'partially_received', page_size: 100 }),
        purchaseOrdersApi.list({ status: 'received', page_size: 100 }),
      ])
      setCandidatePOs([...sentRes.items, ...partRes.items, ...recRes.items])
    } catch {
      // Non-fatal
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter, supplierFilter])

  const openCreateModal = async () => {
    setCreatePoId(0)
    setInvoiceRef('')
    setInvoiceDate(new Date().toISOString().split('T')[0])
    const d = new Date()
    d.setDate(d.getDate() + 30)
    setDueDate(d.toISOString().split('T')[0])
    setInvoiceNotes('')
    setBillLines([])
    await loadCandidatePOs()
    setIsCreateOpen(true)
  }

  const handlePoChange = async (poId: number) => {
    setCreatePoId(poId)
    if (!poId) {
      setBillLines([])
      return
    }

    try {
      const fullPo = await purchaseOrdersApi.get(poId)
      const lines: BillLineDraft[] = fullPo.items.map((item) => {
        const poQty = Number(item.quantity)
        const recQty = Number(item.quantity_received || 0)
        const unitCost = Number(item.unit_cost)
        return {
          po_item_id: item.id,
          product_id: item.product_id,
          product_name: item.product_name || `Product #${item.product_id}`,
          product_sku: item.product_sku || '',
          po_qty: poQty,
          received_qty: recQty,
          po_unit_cost: unitCost,
          // Suggest received quantity if received, otherwise po_qty
          billed_qty: (recQty > 0 ? recQty : poQty).toString(),
          billed_unit_cost: unitCost.toFixed(2),
        }
      })
      setBillLines(lines)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createPoId) {
      setGeneralError(new Error('Please select a Purchase Order.'))
      return
    }
    if (!invoiceRef.trim()) {
      setGeneralError(new Error('Supplier Invoice Reference # is required.'))
      return
    }

    const itemsToBill: SupplierInvoiceItemPayload[] = billLines
      .map((l) => ({
        purchase_order_item_id: l.po_item_id,
        quantity: parseFloat(l.billed_qty) || 0,
        unit_cost: parseFloat(l.billed_unit_cost) || 0,
      }))
      .filter((l) => Number(l.quantity) > 0)

    if (itemsToBill.length === 0) {
      setGeneralError(new Error('At least one item must have a billed quantity greater than 0.'))
      return
    }

    const payload: SupplierInvoiceCreatePayload = {
      purchase_order_id: createPoId,
      supplier_invoice_ref: invoiceRef.trim(),
      invoice_date: invoiceDate || undefined,
      due_date: dueDate || undefined,
      notes: invoiceNotes.trim() || undefined,
      items: itemsToBill,
    }

    setIsSubmitting(true)
    setConflictError(null)
    setGeneralError(null)

    try {
      const created = await supplierInvoicesApi.create(payload)
      setSuccessMessage(
        `Supplier Bill ${created.bill_no} created with status '${created.status.toUpperCase()}'. 3-Way Match executed.`
      )
      setIsCreateOpen(false)
      loadData()
      openDetailsModal(created)
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

  const openDetailsModal = async (inv: SupplierInvoice) => {
    try {
      const full = await supplierInvoicesApi.get(inv.id)
      setSelectedInvoice(full)
      setIsDetailsOpen(true)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const handleApprove = async (inv: SupplierInvoice) => {
    const isException = inv.status === 'exception'
    const confirmPrompt = isException
      ? `WARNING: Bill ${inv.bill_no} is currently in EXCEPTION status (${inv.match_notes || 'tolerance variance'}). Are you sure you want to approve this bill as a manager override?`
      : `Approve Supplier Bill ${inv.bill_no} for payment?`

    if (!window.confirm(confirmPrompt)) {
      return
    }

    setIsLoading(true)
    try {
      const updated = await supplierInvoicesApi.approve(inv.id)
      setSuccessMessage(`Supplier Bill ${updated.bill_no} approved for AP disbursement.`)
      setSelectedInvoice(updated)
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

  const handleVoidSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedInvoice) return
    if (!voidReason.trim()) {
      setGeneralError(new Error('Void reason is required.'))
      return
    }

    setIsSubmitting(true)
    try {
      const updated = await supplierInvoicesApi.void(selectedInvoice.id, voidReason.trim())
      setSuccessMessage(`Supplier Bill ${updated.bill_no} marked as void.`)
      setSelectedInvoice(updated)
      setIsVoidOpen(false)
      setVoidReason('')
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

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'matched':
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
            <ShieldCheck size={12} /> 3-Way Matched
          </span>
        )
      case 'exception':
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
            <AlertTriangle size={12} /> Exception
          </span>
        )
      case 'approved':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(99, 102, 241, 0.15)',
              color: '#818cf8',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <CheckCircle size={12} /> Approved
          </span>
        )
      case 'partially_paid':
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
            <Clock size={12} /> Partially Paid
          </span>
        )
      case 'paid':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(16, 185, 129, 0.2)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <DollarSign size={12} /> Paid
          </span>
        )
      case 'void':
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(148, 163, 184, 0.15)',
              color: '#94a3b8',
              border: '1px solid rgba(148, 163, 184, 0.3)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <XCircle size={12} /> Void
          </span>
        )
      case 'draft':
      default:
        return (
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: 'rgba(148, 163, 184, 0.1)',
              color: '#94a3b8',
              border: '1px solid rgba(148, 163, 184, 0.2)',
            }}
          >
            {status}
          </span>
        )
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
                background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
              }}
            >
              <Scale size={22} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-main)' }}>
                Supplier Invoices & 3-Way Match
              </h1>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Verify vendor bills against Purchase Orders and physical Goods Receipts with automatic tolerance variance checks.
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
              background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
            }}
          >
            <Plus size={16} /> Enter Vendor Bill
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
            <option value="matched">Matched (Ready to Approve)</option>
            <option value="exception">Exception (Mismatch)</option>
            <option value="approved">Approved</option>
            <option value="partially_paid">Partially Paid</option>
            <option value="paid">Paid</option>
            <option value="void">Void</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Supplier:</span>
          <select
            value={supplierFilter}
            onChange={(e) => {
              setSupplierFilter(e.target.value)
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
            <option value="">All Suppliers</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        {(statusFilter || supplierFilter) && (
          <button
            onClick={() => {
              setStatusFilter('')
              setSupplierFilter('')
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
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Bill #</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Vendor / Ref #</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Purchase Order</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Dates</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>3-Way Status</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Total</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Balance Due</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Loading Supplier Invoices...
                  </td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No supplier invoices found. Click "Enter Vendor Bill" to match and verify a new invoice.
                  </td>
                </tr>
              ) : (
                invoices.map((inv) => (
                  <tr
                    key={inv.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background-color 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.02)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: 'var(--primary)' }}>
                      {inv.bill_no}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                        {inv.supplier_name || `Supplier #${inv.supplier_id}`}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Ref: <span style={{ color: 'var(--text-main)' }}>{inv.supplier_invoice_ref}</span>
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                        <FileCheck size={14} style={{ color: 'var(--primary)' }} />
                        {inv.po_no || `PO #${inv.purchase_order_id}`}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      <div>Inv: {inv.invoice_date}</div>
                      <div>Due: {inv.due_date}</div>
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <div>{getStatusBadge(inv.status)}</div>
                      {inv.status === 'exception' && inv.match_notes && (
                        <div
                          style={{
                            fontSize: '0.725rem',
                            color: '#ef4444',
                            marginTop: '0.25rem',
                            maxWidth: '220px',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          title={inv.match_notes}
                        >
                          {inv.match_notes}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right', fontWeight: 600 }}>
                      ${Number(inv.grand_total).toFixed(2)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right', fontWeight: 600 }}>
                      <span style={{ color: Number(inv.balance_due) > 0 ? '#f59e0b' : '#10b981' }}>
                        ${Number(inv.balance_due).toFixed(2)}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => openDetailsModal(inv)}
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
                          Audit Match
                        </button>
                        {(inv.status === 'matched' || inv.status === 'exception' || inv.status === 'draft') && (
                          <button
                            onClick={() => handleApprove(inv)}
                            style={{
                              padding: '0.35rem 0.7rem',
                              backgroundColor:
                                inv.status === 'exception'
                                  ? 'rgba(239, 68, 68, 0.15)'
                                  : 'rgba(99, 102, 241, 0.15)',
                              border:
                                inv.status === 'exception'
                                  ? '1px solid rgba(239, 68, 68, 0.3)'
                                  : '1px solid rgba(99, 102, 241, 0.3)',
                              borderRadius: '6px',
                              color: inv.status === 'exception' ? '#ef4444' : '#818cf8',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            {inv.status === 'exception' ? 'Override & Approve' : 'Approve'}
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
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} bills
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

      {/* Modal: Create Supplier Bill */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Enter Vendor Bill (3-Way Match Verification)">
        <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
              Select Purchase Order to Bill Against *
            </label>
            <select
              value={createPoId}
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
              <option value={0}>-- Select Purchase Order --</option>
              {candidatePOs.map((po) => (
                <option key={po.id} value={po.id}>
                  {po.po_no} | {po.supplier_name || `Supplier #${po.supplier_id}`} (${Number(po.grand_total).toFixed(2)}) - Status: {po.status}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Vendor Invoice Ref / # *
              </label>
              <input
                type="text"
                required
                value={invoiceRef}
                onChange={(e) => setInvoiceRef(e.target.value)}
                placeholder="e.g. INV-98422"
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
                Invoice Date
              </label>
              <input
                type="date"
                required
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
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
                Payment Due Date
              </label>
              <input
                type="date"
                required
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
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

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
              Notes / Remarks
            </label>
            <input
              type="text"
              value={invoiceNotes}
              onChange={(e) => setInvoiceNotes(e.target.value)}
              placeholder="e.g. Received via supplier accounting portal"
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

          {/* Billed line items table */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, margin: 0 }}>
                Invoice Lines (PO Baseline Comparison)
              </label>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                System automatically executes 3-way match against physical receipts & price tolerances upon submission.
              </span>
            </div>

            {billLines.length === 0 ? (
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
                Select a Purchase Order above to load line items.
              </div>
            ) : (
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Product</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>PO Qty</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Physical Recv Qty</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>PO Unit Cost</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)', width: '110px' }}>
                        Billed Qty
                      </th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)', width: '110px' }}>
                        Billed Cost
                      </th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Subtotal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {billLines.map((line, idx) => {
                      const bQty = parseFloat(line.billed_qty) || 0
                      const bCost = parseFloat(line.billed_unit_cost) || 0
                      const sub = (bQty * bCost).toFixed(2)
                      const isQtyExceeded = bQty > line.received_qty
                      const isCostDiff = Math.abs(bCost - line.po_unit_cost) > 0.0001

                      return (
                        <tr key={line.po_item_id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '0.6rem 0.75rem' }}>
                            <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{line.product_name}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>SKU: {line.product_sku || 'N/A'}</div>
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>{line.po_qty}</td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, color: '#38bdf8' }}>
                            {line.received_qty}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                            ${line.po_unit_cost.toFixed(2)}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={line.billed_qty}
                              onChange={(e) => {
                                const val = e.target.value
                                setBillLines((prev) =>
                                  prev.map((l, i) => (i === idx ? { ...l, billed_qty: val } : l))
                                )
                              }}
                              style={{
                                width: '90px',
                                padding: '0.4rem',
                                backgroundColor: 'var(--bg-input)',
                                color: 'var(--text-main)',
                                border: isQtyExceeded ? '1px solid #f59e0b' : '1px solid var(--border-subtle)',
                                borderRadius: '6px',
                                textAlign: 'right',
                                fontSize: '0.85rem',
                              }}
                            />
                            {isQtyExceeded && (
                              <div style={{ fontSize: '0.65rem', color: '#f59e0b', marginTop: '2px' }}>
                                &gt; Recv ({line.received_qty})
                              </div>
                            )}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={line.billed_unit_cost}
                              onChange={(e) => {
                                const val = e.target.value
                                setBillLines((prev) =>
                                  prev.map((l, i) => (i === idx ? { ...l, billed_unit_cost: val } : l))
                                )
                              }}
                              style={{
                                width: '90px',
                                padding: '0.4rem',
                                backgroundColor: 'var(--bg-input)',
                                color: 'var(--text-main)',
                                border: isCostDiff ? '1px solid #f59e0b' : '1px solid var(--border-subtle)',
                                borderRadius: '6px',
                                textAlign: 'right',
                                fontSize: '0.85rem',
                              }}
                            />
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600 }}>
                            ${sub}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Action buttons */}
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
              disabled={isSubmitting || createPoId === 0}
              style={{
                padding: '0.625rem 1.5rem',
                background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: isSubmitting || createPoId === 0 ? 'not-allowed' : 'pointer',
                opacity: isSubmitting || createPoId === 0 ? 0.6 : 1,
              }}
            >
              {isSubmitting ? 'Verifying 3-Way Match...' : 'Submit & Match Bill'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Bill Details & Visual 3-Way Match Audit Grid */}
      {selectedInvoice && (
        <Modal
          isOpen={isDetailsOpen}
          onClose={() => setIsDetailsOpen(false)}
          title={`Supplier Bill Audit: ${selectedInvoice.bill_no}`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* 3-Way Match Banner */}
            {selectedInvoice.status === 'matched' ? (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  color: '#10b981',
                }}
              >
                <ShieldCheck size={24} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>3-Way Match Verified</div>
                  <div style={{ fontSize: '0.8rem', opacity: 0.9 }}>
                    All billed quantities match physical goods received, and unit prices comply with company tolerance thresholds.
                  </div>
                </div>
              </div>
            ) : selectedInvoice.status === 'exception' ? (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.12)',
                  border: '1px solid rgba(239, 68, 68, 0.35)',
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.75rem',
                  color: '#ef4444',
                }}
              >
                <AlertCircle size={24} style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>3-Way Match Exception Detected</div>
                  <div style={{ fontSize: '0.85rem', marginTop: '0.25rem', color: 'var(--text-main)' }}>
                    <strong>Discrepancy Details: </strong>
                    <span style={{ color: '#ef4444' }}>{selectedInvoice.match_notes || 'Tolerance or quantity mismatch.'}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', marginTop: '0.35rem', color: 'var(--text-muted)' }}>
                    Requires managerial override to approve for payment.
                  </div>
                </div>
              </div>
            ) : null}

            {/* Bill Summary Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '1rem',
                backgroundColor: 'rgba(255, 255, 255, 0.02)',
                padding: '1rem',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Status</span>
                <div style={{ marginTop: '0.25rem' }}>{getStatusBadge(selectedInvoice.status)}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Supplier</span>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {selectedInvoice.supplier_name || `#${selectedInvoice.supplier_id}`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Purchase Order</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--primary)' }}>
                  {selectedInvoice.po_no || `#${selectedInvoice.purchase_order_id}`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Invoice Ref #</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  {selectedInvoice.supplier_invoice_ref}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Grand Total</span>
                <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  ${Number(selectedInvoice.grand_total).toFixed(2)}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Balance Due</span>
                <span
                  style={{
                    fontSize: '1rem',
                    fontWeight: 700,
                    color: Number(selectedInvoice.balance_due) > 0 ? '#f59e0b' : '#10b981',
                  }}
                >
                  ${Number(selectedInvoice.balance_due).toFixed(2)}
                </span>
              </div>
            </div>

            {/* Visual 3-Way Match Grid */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>
                  3-Way Match Line Items Breakdown
                </h4>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Comparing PO Baseline vs Physical Goods Receipts vs Vendor Bill
                </span>
              </div>

              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>#</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Item</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Billed Qty</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Unit Cost</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Net</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Tax</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedInvoice.items?.map((item) => (
                      <tr key={item.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-muted)' }}>{item.line_no}</td>
                        <td style={{ padding: '0.6rem 0.75rem' }}>
                          <div style={{ fontWeight: 600 }}>{item.product_name || `Product #${item.product_id}`}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            SKU: {item.product_sku || 'N/A'} {item.description && `| ${item.description}`}
                          </div>
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600 }}>
                          {item.quantity} {item.uom}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                          ${Number(item.unit_cost).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                          ${Number(item.line_net).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          ${Number(item.line_tax).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600 }}>
                          ${Number(item.line_total).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Financial summary breakdown */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <div
                style={{
                  width: '260px',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.85rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Subtotal:</span>
                  <span>${Number(selectedInvoice.subtotal).toFixed(2)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Tax Total:</span>
                  <span>${Number(selectedInvoice.tax_total).toFixed(2)}</span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    paddingTop: '0.35rem',
                    borderTop: '1px solid var(--border-subtle)',
                    fontWeight: 700,
                  }}
                >
                  <span>Grand Total:</span>
                  <span style={{ color: 'var(--primary)' }}>${Number(selectedInvoice.grand_total).toFixed(2)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.35rem', color: '#10b981' }}>
                  <span>Paid so far:</span>
                  <span>-${Number(selectedInvoice.amount_paid).toFixed(2)}</span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginTop: '0.35rem',
                    fontWeight: 700,
                    color: Number(selectedInvoice.balance_due) > 0 ? '#f59e0b' : '#10b981',
                  }}
                >
                  <span>Balance Due:</span>
                  <span>${Number(selectedInvoice.balance_due).toFixed(2)}</span>
                </div>
              </div>
            </div>

            {/* Actions Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
              <div>
                {selectedInvoice.status !== 'void' && Number(selectedInvoice.amount_paid) === 0 && (
                  <button
                    onClick={() => setIsVoidOpen(true)}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: 'rgba(239, 68, 68, 0.1)',
                      border: '1px solid rgba(239, 68, 68, 0.25)',
                      borderRadius: '8px',
                      color: '#ef4444',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Void Bill
                  </button>
                )}
              </div>

              <div style={{ display: 'flex', gap: '0.75rem' }}>
                {(selectedInvoice.status === 'matched' ||
                  selectedInvoice.status === 'exception' ||
                  selectedInvoice.status === 'draft') && (
                  <button
                    onClick={() => handleApprove(selectedInvoice)}
                    style={{
                      padding: '0.625rem 1.25rem',
                      background:
                        selectedInvoice.status === 'exception'
                          ? 'linear-gradient(135deg, #f59e0b, #d97706)'
                          : 'linear-gradient(135deg, #10b981, #059669)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                    }}
                  >
                    {selectedInvoice.status === 'exception' ? 'Manager Override: Approve Bill' : 'Approve Bill for Payment'}
                  </button>
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

      {/* Modal: Void Supplier Bill */}
      <Modal isOpen={isVoidOpen} onClose={() => setIsVoidOpen(false)} title="Void Supplier Bill">
        <form onSubmit={handleVoidSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Voiding bill <strong>{selectedInvoice?.bill_no}</strong> will cancel the payable obligation.
            Please specify an audit reason:
          </p>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
              Reason for Voiding *
            </label>
            <input
              type="text"
              required
              value={voidReason}
              onChange={(e) => setVoidReason(e.target.value)}
              placeholder="e.g. Duplicate vendor invoice received, replaced by INV-9901"
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
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setIsVoidOpen(false)}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: 'transparent',
                border: '1px solid var(--border-subtle)',
                borderRadius: '6px',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !voidReason.trim()}
              style={{
                padding: '0.5rem 1.25rem',
                backgroundColor: '#ef4444',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: isSubmitting || !voidReason.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Voiding...' : 'Confirm Void'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
