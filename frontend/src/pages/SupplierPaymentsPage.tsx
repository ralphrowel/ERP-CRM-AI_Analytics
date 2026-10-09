import React, { useEffect, useState } from 'react'
import {
  ArrowRight,
  CheckCircle,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Wallet,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type Supplier,
  type SupplierPayment,
  type SupplierPaymentAllocationItem,
  type SupplierPaymentCreatePayload,
  type SupplierStatement,
  supplierInvoicesApi,
  supplierPaymentsApi,
  suppliersApi,
} from '../api/purchasing'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

interface BillAllocationDraft {
  bill_id: number
  bill_no: string
  supplier_invoice_ref: string
  due_date: string
  grand_total: number
  balance_due: number
  allocated_amount: string
}

export const SupplierPaymentsPage: React.FC = () => {
  const [payments, setPayments] = useState<SupplierPayment[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [supplierFilter, setSupplierFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master Data
  const [suppliers, setSuppliers] = useState<Supplier[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isVoidOpen, setIsVoidOpen] = useState(false)
  const [isStatementOpen, setIsStatementOpen] = useState(false)

  const [selectedPayment, setSelectedPayment] = useState<SupplierPayment | null>(null)
  const [statementSupplierId, setStatementSupplierId] = useState<number>(0)
  const [statementData, setStatementData] = useState<SupplierStatement | null>(null)
  const [isLoadingStatement, setIsLoadingStatement] = useState(false)
  const [voidReason, setVoidReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Create Payment State
  const [createSupplierId, setCreateSupplierId] = useState<number>(0)
  const [paymentAmount, setPaymentAmount] = useState<string>('')
  const [paymentDate, setPaymentDate] = useState<string>(() => new Date().toISOString().split('T')[0])
  const [paymentMethod, setPaymentMethod] = useState<string>('bank_transfer')
  const [referenceNo, setReferenceNo] = useState<string>('')
  const [paymentNotes, setPaymentNotes] = useState<string>('')
  const [eligibleBills, setEligibleBills] = useState<BillAllocationDraft[]>([])

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [payRes, supRes] = await Promise.all([
        supplierPaymentsApi.list({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
        }),
        suppliersApi.list({ page: 1, page_size: 100 }),
      ])
      setPayments(payRes.items)
      setTotal(payRes.total)
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

  useEffect(() => {
    loadData()
  }, [page, statusFilter, supplierFilter])

  const openCreateModal = async () => {
    setCreateSupplierId(0)
    setPaymentAmount('')
    setPaymentDate(new Date().toISOString().split('T')[0])
    setPaymentMethod('bank_transfer')
    setReferenceNo('')
    setPaymentNotes('')
    setEligibleBills([])
    setIsCreateOpen(true)
  }

  const handleSupplierChange = async (supplierId: number) => {
    setCreateSupplierId(supplierId)
    if (!supplierId) {
      setEligibleBills([])
      return
    }

    try {
      // Fetch bills with status approved or partially_paid
      const [appRes, partRes] = await Promise.all([
        supplierInvoicesApi.list({ supplier_id: supplierId, status: 'approved', page_size: 100 }),
        supplierInvoicesApi.list({ supplier_id: supplierId, status: 'partially_paid', page_size: 100 }),
      ])

      const combined = [...appRes.items, ...partRes.items]
      // Sort by due date ascending
      combined.sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime())

      const drafts: BillAllocationDraft[] = combined.map((b) => ({
        bill_id: b.id,
        bill_no: b.bill_no,
        supplier_invoice_ref: b.supplier_invoice_ref,
        due_date: b.due_date,
        grand_total: Number(b.grand_total),
        balance_due: Number(b.balance_due),
        allocated_amount: '0',
      }))

      setEligibleBills(drafts)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const handleAutoAllocate = () => {
    let remainingToAllocate = parseFloat(paymentAmount) || 0
    if (remainingToAllocate <= 0) {
      alert('Please enter a valid Payment Amount first.')
      return
    }

    const updated = eligibleBills.map((b) => {
      if (remainingToAllocate <= 0) {
        return { ...b, allocated_amount: '0' }
      }
      const canTake = Math.min(b.balance_due, remainingToAllocate)
      remainingToAllocate -= canTake
      return { ...b, allocated_amount: canTake.toFixed(2) }
    })

    setEligibleBills(updated)
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createSupplierId) {
      setGeneralError(new Error('Please select a supplier.'))
      return
    }

    const totalAmt = parseFloat(paymentAmount) || 0
    if (totalAmt <= 0) {
      setGeneralError(new Error('Payment amount must be greater than zero.'))
      return
    }

    // Build allocations
    const allocations: SupplierPaymentAllocationItem[] = eligibleBills
      .map((b) => ({
        supplier_invoice_id: b.bill_id,
        amount: parseFloat(b.allocated_amount) || 0,
      }))
      .filter((a) => Number(a.amount) > 0)

    const sumAlloc = allocations.reduce((acc, curr) => acc + Number(curr.amount), 0)
    if (sumAlloc > totalAmt + 0.001) {
      setGeneralError(
        new Error(
          `Allocated total ($${sumAlloc.toFixed(2)}) exceeds payment amount ($${totalAmt.toFixed(2)}).`
        )
      )
      return
    }

    const payload: SupplierPaymentCreatePayload = {
      supplier_id: createSupplierId,
      amount: totalAmt,
      payment_date: paymentDate || undefined,
      payment_method: paymentMethod,
      reference_no: referenceNo.trim() || undefined,
      notes: paymentNotes.trim() || undefined,
      allocations: allocations.length > 0 ? allocations : undefined,
    }

    setIsSubmitting(true)
    setConflictError(null)
    setGeneralError(null)

    try {
      const created = await supplierPaymentsApi.create(payload)
      setSuccessMessage(
        `Disbursement ${created.payment_no} of $${Number(created.amount).toFixed(2)} recorded and allocated successfully.`
      )
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

  const openDetailsModal = async (p: SupplierPayment) => {
    try {
      const full = await supplierPaymentsApi.get(p.id)
      setSelectedPayment(full)
      setIsDetailsOpen(true)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    }
  }

  const handleVoidSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPayment) return
    if (!voidReason.trim()) {
      setGeneralError(new Error('Void reason is required.'))
      return
    }

    setIsSubmitting(true)
    try {
      const updated = await supplierPaymentsApi.void(selectedPayment.id, voidReason.trim())
      setSuccessMessage(`Payment ${updated.payment_no} voided. All bill balances and allocations restored.`)
      setSelectedPayment(updated)
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

  const openStatementModal = async (supplierId?: number) => {
    const targetId = supplierId || Number(supplierFilter) || (suppliers[0]?.id ?? 0)
    if (!targetId) {
      alert('Please select or specify a supplier to view their financial statement.')
      return
    }

    setStatementSupplierId(targetId)
    setIsStatementOpen(true)
    setIsLoadingStatement(true)

    try {
      const stmt = await suppliersApi.getStatement(targetId)
      setStatementData(stmt)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    } finally {
      setIsLoadingStatement(false)
    }
  }

  const handleStatementSupplierChange = async (newId: number) => {
    setStatementSupplierId(newId)
    setIsLoadingStatement(true)
    try {
      const stmt = await suppliersApi.getStatement(newId)
      setStatementData(stmt)
    } catch (err: unknown) {
      setGeneralError(err as ApiError | Error)
    } finally {
      setIsLoadingStatement(false)
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
                background: 'linear-gradient(135deg, #10b981, #059669)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
              }}
            >
              <Wallet size={22} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-main)' }}>
                AP Payments & Allocations
              </h1>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Disburse vendor payments, allocate against approved bills with row locks, and reconcile supplier statements.
              </p>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => openStatementModal()}
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
            <FileSpreadsheet size={15} style={{ color: '#10b981' }} /> Supplier Statement
          </button>
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
              background: 'linear-gradient(135deg, #10b981, #059669)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
            }}
          >
            <Plus size={16} /> Record Payment
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
            <option value="posted">Posted</option>
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
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Payment #</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Supplier</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Date</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Method / Ref</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Amount</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Allocated</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Status</th>
                <th style={{ padding: '0.9rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Loading AP Payments...
                  </td>
                </tr>
              ) : payments.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No AP payments found. Click "Record Payment" to disburse funds against approved vendor bills.
                  </td>
                </tr>
              ) : (
                payments.map((p) => (
                  <tr
                    key={p.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background-color 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.02)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: '#10b981' }}>
                      {p.payment_no}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                        {p.supplier_name || `Supplier #${p.supplier_id}`}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      {p.payment_date}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <div style={{ textTransform: 'capitalize', color: 'var(--text-main)', fontSize: '0.85rem' }}>
                        {p.payment_method.replace('_', ' ')}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Ref: {p.reference_no || '—'}
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right', fontWeight: 700, color: 'var(--text-main)' }}>
                      ${Number(p.amount).toFixed(2)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right', fontWeight: 600, color: '#10b981' }}>
                      ${Number(p.amount_allocated).toFixed(2)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      {p.status === 'posted' ? (
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
                      ) : (
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
                          <XCircle size={12} /> Void
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => openDetailsModal(p)}
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
                          Allocations
                        </button>
                        {p.status === 'posted' && (
                          <button
                            onClick={() => {
                              setSelectedPayment(p)
                              setIsVoidOpen(true)
                            }}
                            style={{
                              padding: '0.35rem 0.7rem',
                              backgroundColor: 'rgba(239, 68, 68, 0.1)',
                              border: '1px solid rgba(239, 68, 68, 0.25)',
                              borderRadius: '6px',
                              color: '#ef4444',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            Void
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
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} payments
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

      {/* Modal: New Supplier Payment */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Record Vendor Payment (AP Disbursement)">
        <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
              Select Payee Supplier *
            </label>
            <select
              value={createSupplierId}
              onChange={(e) => handleSupplierChange(Number(e.target.value))}
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
              <option value={0}>-- Select Supplier --</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.supplier_no})
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Payment Amount ($) *
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
                placeholder="0.00"
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Payment Date
              </label>
              <input
                type="date"
                required
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
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
                Payment Method
              </label>
              <select
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
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
                <option value="bank_transfer">Bank Transfer / Wire</option>
                <option value="ach">ACH Direct Debit</option>
                <option value="check">Company Check</option>
                <option value="credit_card">Corporate Credit Card</option>
                <option value="cash">Petty Cash</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                Reference / Check / Wire #
              </label>
              <input
                type="text"
                value={referenceNo}
                onChange={(e) => setReferenceNo(e.target.value)}
                placeholder="e.g. WIRE-881923"
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
                Notes / Purpose
              </label>
              <input
                type="text"
                value={paymentNotes}
                onChange={(e) => setPaymentNotes(e.target.value)}
                placeholder="e.g. Q4 vendor settlement"
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

          {/* Bill allocations table */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, margin: 0 }}>
                Allocate Against Approved Bills
              </label>
              {eligibleBills.length > 0 && (
                <button
                  type="button"
                  onClick={handleAutoAllocate}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.6rem',
                    backgroundColor: 'rgba(16, 185, 129, 0.15)',
                    color: '#10b981',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  <ArrowRight size={12} /> Auto-allocate Earliest Bills
                </button>
              )}
            </div>

            {eligibleBills.length === 0 ? (
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
                {createSupplierId
                  ? 'No approved or partially paid bills pending for this supplier. Payment will be saved unallocated as on-account credit.'
                  : 'Select a payee supplier above to load outstanding approved bills.'}
              </div>
            ) : (
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Bill #</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Ref #</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Due Date</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Grand Total</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Balance Due</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)', width: '130px' }}>
                        Allocation ($)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {eligibleBills.map((b, idx) => (
                      <tr key={b.bill_id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600, color: 'var(--primary)' }}>
                          {b.bill_no}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem' }}>{b.supplier_invoice_ref}</td>
                        <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-muted)' }}>{b.due_date}</td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>${b.grand_total.toFixed(2)}</td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, color: '#f59e0b' }}>
                          ${b.balance_due.toFixed(2)}
                        </td>
                        <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                          <input
                            type="number"
                            min="0"
                            max={b.balance_due}
                            step="0.01"
                            value={b.allocated_amount}
                            onChange={(e) => {
                              const val = e.target.value
                              setEligibleBills((prev) =>
                                prev.map((item, i) => (i === idx ? { ...item, allocated_amount: val } : item))
                              )
                            }}
                            style={{
                              width: '100px',
                              padding: '0.4rem',
                              backgroundColor: 'var(--bg-input)',
                              color: 'var(--text-main)',
                              border:
                                parseFloat(b.allocated_amount) > b.balance_due
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
              disabled={isSubmitting || createSupplierId === 0 || !paymentAmount}
              style={{
                padding: '0.625rem 1.5rem',
                background: 'linear-gradient(135deg, #10b981, #059669)',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: isSubmitting || createSupplierId === 0 || !paymentAmount ? 'not-allowed' : 'pointer',
                opacity: isSubmitting || createSupplierId === 0 || !paymentAmount ? 0.6 : 1,
              }}
            >
              {isSubmitting ? 'Recording Disbursement...' : 'Execute Payment'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Payment Details & Allocations Breakdown */}
      {selectedPayment && (
        <Modal
          isOpen={isDetailsOpen}
          onClose={() => setIsDetailsOpen(false)}
          title={`AP Payment: ${selectedPayment.payment_no}`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
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
                <span
                  style={{
                    display: 'inline-block',
                    marginTop: '0.25rem',
                    fontWeight: 600,
                    color: selectedPayment.status === 'posted' ? '#10b981' : '#ef4444',
                  }}
                >
                  {selectedPayment.status.toUpperCase()}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Supplier</span>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {selectedPayment.supplier_name || `#${selectedPayment.supplier_id}`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Payment Date</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>{selectedPayment.payment_date}</span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Method / Ref</span>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  {selectedPayment.payment_method} {selectedPayment.reference_no && `(${selectedPayment.reference_no})`}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Total Paid</span>
                <span style={{ fontSize: '1.1rem', fontWeight: 700, color: '#10b981' }}>
                  ${Number(selectedPayment.amount).toFixed(2)}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Allocated</span>
                <span style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  ${Number(selectedPayment.amount_allocated).toFixed(2)}
                </span>
              </div>
            </div>

            {selectedPayment.status === 'void' && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.12)',
                  borderRadius: '6px',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  fontSize: '0.85rem',
                  color: '#ef4444',
                }}
              >
                <strong>Void Reason: </strong> {selectedPayment.void_reason} (Voided at {selectedPayment.voided_at})
              </div>
            )}

            {/* Allocations Table */}
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>
                Bill Allocations ({selectedPayment.allocations?.length || 0})
              </h4>
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                    <tr>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Bill #</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', color: 'var(--text-muted)' }}>Invoice Ref</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Amount Allocated</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)' }}>Allocated Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(!selectedPayment.allocations || selectedPayment.allocations.length === 0) ? (
                      <tr>
                        <td colSpan={4} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No specific bill allocations. Held on-account for supplier.
                        </td>
                      </tr>
                    ) : (
                      selectedPayment.allocations.map((a) => (
                        <tr key={a.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600, color: 'var(--primary)' }}>
                            {a.bill_no || `Bill #${a.supplier_invoice_id}`}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem' }}>{a.supplier_invoice_ref || '—'}</td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, color: '#10b981' }}>
                            ${Number(a.amount).toFixed(2)}
                          </td>
                          <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            {new Date(a.allocated_at).toLocaleString()}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
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
        </Modal>
      )}

      {/* Modal: Void Supplier Payment */}
      <Modal isOpen={isVoidOpen} onClose={() => setIsVoidOpen(false)} title="Void Supplier Payment">
        <form onSubmit={handleVoidSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Voiding payment <strong>{selectedPayment?.payment_no}</strong> will immediately reverse all bill allocations
            and restore unpaid balances on associated vendor bills.
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
              placeholder="e.g. Stop payment requested, wire recalled by treasury"
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
              {isSubmitting ? 'Voiding...' : 'Confirm Void & Rollback'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Supplier Financial Statement */}
      <Modal
        isOpen={isStatementOpen}
        onClose={() => setIsStatementOpen(false)}
        title="Supplier Statement of Account & Reconciliation"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Supplier selector inside modal */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Statement for:</span>
            <select
              value={statementSupplierId}
              onChange={(e) => handleStatementSupplierChange(Number(e.target.value))}
              style={{
                padding: '0.4rem 0.75rem',
                backgroundColor: 'var(--bg-input)',
                color: 'var(--text-main)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '6px',
                fontSize: '0.85rem',
                minWidth: '240px',
              }}
            >
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.supplier_no})
                </option>
              ))}
            </select>
          </div>

          {isLoadingStatement ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              Compiling supplier ledger statement...
            </div>
          ) : !statementData ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              No statement data available.
            </div>
          ) : (
            <>
              {/* Financial Summary Cards */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '1rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  padding: '1.25rem',
                  borderRadius: '10px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Total Invoiced</span>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-main)', marginTop: '0.25rem' }}>
                    ${Number(statementData.total_billed).toFixed(2)}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Total Paid</span>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#10b981', marginTop: '0.25rem' }}>
                    ${Number(statementData.total_paid).toFixed(2)}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Outstanding Payables</span>
                  <div
                    style={{
                      fontSize: '1.4rem',
                      fontWeight: 700,
                      color: Number(statementData.total_outstanding) > 0 ? '#f59e0b' : '#10b981',
                      marginTop: '0.25rem',
                    }}
                  >
                    ${Number(statementData.total_outstanding).toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Bills breakdown */}
              <div>
                <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>
                  Invoiced Bills ({statementData.bills?.length || 0})
                </h4>
                <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                    <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                      <tr>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Bill #</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Ref #</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Due Date</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: 'var(--text-muted)' }}>Total</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: 'var(--text-muted)' }}>Paid</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: 'var(--text-muted)' }}>Balance</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'center', color: 'var(--text-muted)' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {statementData.bills.map((b) => (
                        <tr key={b.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '0.5rem 0.6rem', fontWeight: 600, color: 'var(--primary)' }}>{b.bill_no}</td>
                          <td style={{ padding: '0.5rem 0.6rem' }}>{b.supplier_invoice_ref}</td>
                          <td style={{ padding: '0.5rem 0.6rem', color: 'var(--text-muted)' }}>{b.due_date}</td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right' }}>${Number(b.grand_total).toFixed(2)}</td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: '#10b981' }}>
                            ${Number(b.amount_paid).toFixed(2)}
                          </td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', fontWeight: 600, color: Number(b.balance_due) > 0 ? '#f59e0b' : '#10b981' }}>
                            ${Number(b.balance_due).toFixed(2)}
                          </td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center' }}>
                            <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', opacity: 0.85 }}>{b.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Payments breakdown */}
              <div>
                <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>
                  Recorded Disbursements ({statementData.payments?.length || 0})
                </h4>
                <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                    <thead style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                      <tr>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Payment #</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Date</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Method</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: 'var(--text-muted)' }}>Ref #</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: 'var(--text-muted)' }}>Amount</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: 'var(--text-muted)' }}>Allocated</th>
                        <th style={{ padding: '0.5rem 0.6rem', textAlign: 'center', color: 'var(--text-muted)' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {statementData.payments.map((p) => (
                        <tr key={p.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '0.5rem 0.6rem', fontWeight: 600, color: '#10b981' }}>{p.payment_no}</td>
                          <td style={{ padding: '0.5rem 0.6rem', color: 'var(--text-muted)' }}>{p.payment_date}</td>
                          <td style={{ padding: '0.5rem 0.6rem', textTransform: 'capitalize' }}>{p.payment_method}</td>
                          <td style={{ padding: '0.5rem 0.6rem', color: 'var(--text-muted)' }}>{p.reference_no || '—'}</td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', fontWeight: 600 }}>
                            ${Number(p.amount).toFixed(2)}
                          </td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'right', color: '#10b981' }}>
                            ${Number(p.amount_allocated).toFixed(2)}
                          </td>
                          <td style={{ padding: '0.5rem 0.6rem', textAlign: 'center' }}>
                            <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', opacity: 0.85 }}>{p.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                <button
                  onClick={() => setIsStatementOpen(false)}
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
            </>
          )}
        </div>
      </Modal>
    </div>
  )
}
