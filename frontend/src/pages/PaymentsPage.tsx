import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  FileText,
  Plus,
  RefreshCw,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Customer, customersApi } from '../api/customers'
import {
  type Invoice,
  type Payment,
  type PaymentCreatePayload,
  type PaymentMethod,
  salesApi,
} from '../api/sales'
import { CustomerStatementModal } from '../components/CustomerStatementModal'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

export const PaymentsPage: React.FC = () => {
  const [payments, setPayments] = useState<Payment[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [customerFilter, setCustomerFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master data
  const [customers, setCustomers] = useState<Customer[]>([])

  // Notifications
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isRecordOpen, setIsRecordOpen] = useState(false)
  const [isAllocateOpen, setIsAllocateOpen] = useState(false)
  const [isVoidOpen, setIsVoidOpen] = useState(false)
  const [isStatementOpen, setIsStatementOpen] = useState(false)
  const [selectedPayment, setSelectedPayment] = useState<Payment | null>(null)
  const [statementCustomerId, setStatementCustomerId] = useState<number | null>(null)
  const [voidReason, setVoidReason] = useState('')

  // Record payment form
  const [customerId, setCustomerId] = useState<number>(0)
  const [paymentDate, setPaymentDate] = useState<string>(new Date().toISOString().split('T')[0])
  const [method, setMethod] = useState<PaymentMethod>('bank_transfer')
  const [referenceNo, setReferenceNo] = useState('')
  const [amount, setAmount] = useState('')
  const [openInvoices, setOpenInvoices] = useState<Invoice[]>([])
  const [allocations, setAllocations] = useState<Record<number, string>>({})

  // Manual allocation on existing payment
  const [allocateInvoiceId, setAllocateInvoiceId] = useState<number>(0)
  const [allocateAmount, setAllocateAmount] = useState<string>('')

  const loadData = async () => {
    setIsLoading(true)
    setGeneralError(null)
    try {
      const [payRes, custRes] = await Promise.all([
        salesApi.listPayments({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          customer_id: customerFilter ? Number(customerFilter) : undefined,
        }),
        customersApi.list({ page: 1, page_size: 100 }),
      ])
      setPayments(payRes.items)
      setTotal(payRes.total)
      setCustomers(custRes.items)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load payments data'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter, customerFilter])

  // Load customer open invoices when customer changes in Record Payment modal
  useEffect(() => {
    if (customerId) {
      salesApi
        .listInvoices({ customer_id: customerId })
        .then((res) => {
          const unpaid = res.items.filter((i) => ['issued', 'partially_paid'].includes(i.status))
          setOpenInvoices(unpaid)
          setAllocations({})
        })
        .catch(() => {
          setOpenInvoices([])
        })
    } else {
      setOpenInvoices([])
      setAllocations({})
    }
  }, [customerId])

  const formatMoney = (val: string | number) => {
    const num = Number(val || 0)
    return `₱${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const handleAutoAllocate = () => {
    const totalPayment = Number(amount || 0)
    if (totalPayment <= 0) return

    let remaining = totalPayment
    const newAllocs: Record<number, string> = {}

    // Sort by issue date ascending (oldest first)
    const sorted = [...openInvoices].sort((a, b) => {
      const da = a.issue_date || ''
      const db = b.issue_date || ''
      return da.localeCompare(db)
    })

    for (const inv of sorted) {
      if (remaining <= 0) break
      const due = Number(inv.balance_due)
      const alloc = Math.min(remaining, due)
      if (alloc > 0) {
        newAllocs[inv.id] = alloc.toFixed(2)
        remaining -= alloc
      }
    }

    setAllocations(newAllocs)
  }

  const handleRecordPayment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!customerId) {
      setGeneralError(new Error('Please select a customer.'))
      return
    }
    const numAmount = Number(amount)
    if (isNaN(numAmount) || numAmount <= 0) {
      setGeneralError(new Error('Please enter a valid positive payment amount.'))
      return
    }

    const allocList = Object.entries(allocations)
      .map(([invId, allocAmt]) => ({
        invoice_id: Number(invId),
        amount: allocAmt,
      }))
      .filter((a) => Number(a.amount) > 0)

    try {
      const payload: PaymentCreatePayload = {
        customer_id: customerId,
        payment_date: paymentDate,
        method,
        reference_no: referenceNo || null,
        amount: Number(amount).toFixed(2),
        allocations: allocList.length > 0 ? allocList : undefined,
      }
      const idempotencyKey = crypto.randomUUID()
      const newPay = await salesApi.createPayment(payload, idempotencyKey)
      setSuccessMessage(`Payment ${newPay.payment_no} recorded successfully!`)
      setIsRecordOpen(false)
      // Reset form
      setCustomerId(0)
      setAmount('')
      setReferenceNo('')
      setAllocations({})
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to record payment'))
      }
    }
  }

  const handleOpenAllocateModal = async (pay: Payment) => {
    setSelectedPayment(pay)
    setAllocateInvoiceId(0)
    setAllocateAmount('')
    setIsAllocateOpen(true)
    try {
      const res = await salesApi.listInvoices({ customer_id: pay.customer_id })
      const unpaid = res.items.filter((i) => ['issued', 'partially_paid'].includes(i.status))
      setOpenInvoices(unpaid)
    } catch {
      setOpenInvoices([])
    }
  }

  const handleExecuteAllocation = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPayment || !allocateInvoiceId || !allocateAmount) return
    try {
      await salesApi.allocatePayment(selectedPayment.id, {
        invoice_id: allocateInvoiceId,
        amount: Number(allocateAmount).toFixed(2),
      })
      setSuccessMessage(`Allocated ${formatMoney(allocateAmount)} to invoice successfully!`)
      setIsAllocateOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to allocate payment'))
      }
    }
  }

  const handleVoidPayment = async () => {
    if (!selectedPayment) return
    try {
      await salesApi.voidPayment(selectedPayment.id, voidReason)
      setSuccessMessage(`Payment ${selectedPayment.payment_no} voided; allocations reversed.`)
      setIsVoidOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to void payment'))
      }
    }
  }

  const getMethodBadge = (m: PaymentMethod) => {
    const labels: Record<PaymentMethod, string> = {
      cash: 'Cash',
      bank_transfer: 'Bank Transfer',
      check: 'Check',
      gcash: 'GCash',
      maya: 'Maya',
      card: 'Credit/Debit Card',
    }
    return (
      <span
        style={{
          padding: '0.15rem 0.45rem',
          borderRadius: '0.25rem',
          background: 'var(--bg-page)',
          border: '1px solid var(--border-subtle)',
          fontSize: '0.75rem',
          color: 'var(--text-bright)',
        }}
      >
        {labels[m] || m}
      </span>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-bright)' }}>
            Payments & Collections
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-dim)', fontSize: '0.875rem' }}>
            Receive payments, manage customer credits, and allocate across open customer invoices.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className="btn btn-secondary"
            onClick={loadData}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setIsRecordOpen(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
          >
            <Plus size={16} /> Record Payment
          </button>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '0.375rem',
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid var(--emerald-500)',
            color: 'var(--emerald-400)',
            fontSize: '0.85rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{successMessage}</span>
          <button
            onClick={() => setSuccessMessage(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {generalError && <ProblemAlert error={generalError} />}

      {/* Filter Bar */}
      <div
        style={{
          display: 'flex',
          gap: '1rem',
          background: 'var(--bg-card)',
          padding: '0.75rem 1rem',
          borderRadius: '0.5rem',
          border: '1px solid var(--border-subtle)',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Status:</span>
          <select
            className="input"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.85rem', width: 'auto' }}
          >
            <option value="">All Statuses</option>
            <option value="posted">Posted</option>
            <option value="void">Void</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Customer:</span>
          <select
            className="input"
            value={customerFilter}
            onChange={(e) => {
              setCustomerFilter(e.target.value)
              setPage(1)
            }}
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.85rem', width: 'auto' }}
          >
            <option value="">All Customers</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id.toString()}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Payments Table */}
      <div
        style={{
          background: 'var(--bg-card)',
          borderRadius: '0.5rem',
          border: '1px solid var(--border-subtle)',
          overflow: 'hidden',
        }}
      >
        <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ background: 'var(--bg-page)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Payment #</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Customer</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Date</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Method</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Ref #</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Amount</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Allocated</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Unallocated Credit</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Status</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={10} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  Loading payments...
                </td>
              </tr>
            ) : payments.length === 0 ? (
              <tr>
                <td colSpan={10} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  No payment records found. Click "Record Payment" to post a collection.
                </td>
              </tr>
            ) : (
              payments.map((p) => {
                const customer = customers.find((c) => c.id === p.customer_id)
                const unallocatedNum = Number(p.unallocated_amount || 0)
                const isVoid = p.status === 'void'

                return (
                  <tr
                    key={p.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      opacity: isVoid ? 0.6 : 1,
                    }}
                  >
                    <td style={{ padding: '0.75rem 1rem', fontWeight: 600, color: 'var(--brand-300)' }}>
                      {p.payment_no}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 500, color: 'var(--text-bright)' }}>
                        {customer?.name || `Customer #${p.customer_id}`}
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--text-dim)' }}>{p.payment_date}</td>
                    <td style={{ padding: '0.75rem 1rem' }}>{getMethodBadge(p.method)}</td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--text-dim)' }}>{p.reference_no || '—'}</td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, color: 'var(--emerald-400)' }}>
                      {formatMoney(p.amount)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--text-dim)' }}>
                      {formatMoney(p.amount_allocated)}
                    </td>
                    <td
                      style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'right',
                        fontWeight: unallocatedNum > 0 ? 700 : 400,
                        color: unallocatedNum > 0 ? 'var(--sky-400)' : 'var(--text-dim)',
                      }}
                    >
                      {formatMoney(p.unallocated_amount)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '9999px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: isVoid ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                          color: isVoid ? 'var(--rose-400)' : 'var(--emerald-400)',
                          textTransform: 'uppercase',
                        }}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem' }}
                          onClick={() => {
                            setStatementCustomerId(p.customer_id)
                            setIsStatementOpen(true)
                          }}
                          title="View Customer Statement"
                        >
                          <FileText size={12} /> Statement
                        </button>

                        {!isVoid && unallocatedNum > 0 && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem' }}
                            onClick={() => handleOpenAllocateModal(p)}
                            title="Allocate remaining credit to invoices"
                          >
                            <ArrowRight size={12} /> Allocate
                          </button>
                        )}

                        {!isVoid && (
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                            onClick={() => {
                              setSelectedPayment(p)
                              setVoidReason('')
                              setIsVoidOpen(true)
                            }}
                            title="Void Payment"
                          >
                            <XCircle size={12} />
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

        {/* Pagination */}
        <div
          style={{
            padding: '0.75rem 1rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.85rem',
            color: 'var(--text-dim)',
          }}
        >
          <div>
            Showing {payments.length > 0 ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, total)} of {total} payments
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
            >
              Previous
            </button>
            <button
              className="btn btn-secondary"
              disabled={page * pageSize >= total}
              onClick={() => setPage(page + 1)}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Record Payment Modal */}
      <Modal
        isOpen={isRecordOpen}
        onClose={() => setIsRecordOpen(false)}
        title="Record Customer Payment"
        maxWidth="720px"
      >
        <form onSubmit={handleRecordPayment} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Customer *
              </label>
              <select
                className="input"
                value={customerId}
                onChange={(e) => setCustomerId(Number(e.target.value))}
                required
              >
                <option value={0}>Select Customer</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Payment Date *
              </label>
              <input
                type="date"
                className="input"
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Payment Method *
              </label>
              <select
                className="input"
                value={method}
                onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              >
                <option value="bank_transfer">Bank Transfer (BDO / BPI / Metrobank)</option>
                <option value="check">Check</option>
                <option value="cash">Cash</option>
                <option value="gcash">GCash</option>
                <option value="maya">Maya</option>
                <option value="card">Credit / Debit Card</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Reference / Check #
              </label>
              <input
                type="text"
                className="input"
                placeholder="e.g. BDO-TXN-12345"
                value={referenceNo}
                onChange={(e) => setReferenceNo(e.target.value)}
              />
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Payment Amount (PHP) *
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                className="input"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
                style={{ fontSize: '1.1rem', fontWeight: 700 }}
              />
            </div>
          </div>

          {/* Allocation Grid */}
          {openInvoices.length > 0 && (
            <div
              style={{
                marginTop: '0.5rem',
                border: '1px solid var(--border-subtle)',
                borderRadius: '0.375rem',
                padding: '0.75rem',
                background: 'var(--bg-card)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-bright)' }}>
                  Allocate to Open Invoices ({openInvoices.length})
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleAutoAllocate}
                  style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                >
                  Auto-allocate (Oldest First)
                </button>
              </div>

              <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                <table className="table" style={{ width: '100%', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <th style={{ textAlign: 'left', padding: '0.4rem' }}>Invoice #</th>
                      <th style={{ textAlign: 'left', padding: '0.4rem' }}>Issue Date</th>
                      <th style={{ textAlign: 'right', padding: '0.4rem' }}>Balance Due</th>
                      <th style={{ textAlign: 'right', padding: '0.4rem', width: '140px' }}>Allocate (₱)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openInvoices.map((inv) => (
                      <tr key={inv.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.4rem', fontWeight: 600 }}>{inv.invoice_no || `Draft #${inv.id}`}</td>
                        <td style={{ padding: '0.4rem', color: 'var(--text-dim)' }}>{inv.issue_date}</td>
                        <td style={{ padding: '0.4rem', textAlign: 'right', fontWeight: 600, color: 'var(--rose-400)' }}>
                          {formatMoney(inv.balance_due)}
                        </td>
                        <td style={{ padding: '0.4rem', textAlign: 'right' }}>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max={inv.balance_due}
                            className="input"
                            style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem', textAlign: 'right' }}
                            placeholder="0.00"
                            value={allocations[inv.id] || ''}
                            onChange={(e) => {
                              const val = e.target.value
                              setAllocations((prev) => ({
                                ...prev,
                                [inv.id]: val,
                              }))
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.75rem' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsRecordOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Post Payment
            </button>
          </div>
        </form>
      </Modal>

      {/* Manual Allocation Modal for existing payment */}
      {selectedPayment && (
        <Modal
          isOpen={isAllocateOpen}
          onClose={() => setIsAllocateOpen(false)}
          title={`Allocate Credit from Payment ${selectedPayment.payment_no}`}
        >
          <form onSubmit={handleExecuteAllocation} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div
              style={{
                padding: '0.75rem',
                borderRadius: '0.375rem',
                background: 'rgba(14, 165, 233, 0.1)',
                border: '1px solid var(--sky-500)',
                color: 'var(--sky-400)',
                fontSize: '0.85rem',
              }}
            >
              Available Unallocated Credit: <strong>{formatMoney(selectedPayment.unallocated_amount)}</strong>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Target Invoice:
              </label>
              <select
                className="input"
                value={allocateInvoiceId}
                onChange={(e) => {
                  const id = Number(e.target.value)
                  setAllocateInvoiceId(id)
                  const target = openInvoices.find((i) => i.id === id)
                  if (target) {
                    const maxAllowed = Math.min(Number(selectedPayment.unallocated_amount), Number(target.balance_due))
                    setAllocateAmount(maxAllowed.toFixed(2))
                  }
                }}
                required
              >
                <option value={0}>Select Open Invoice</option>
                {openInvoices.map((inv) => (
                  <option key={inv.id} value={inv.id}>
                    {inv.invoice_no || `Draft #${inv.id}`} (Due: {formatMoney(inv.balance_due)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Allocation Amount:
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max={selectedPayment.unallocated_amount}
                className="input"
                value={allocateAmount}
                onChange={(e) => setAllocateAmount(e.target.value)}
                required
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setIsAllocateOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary">
                Confirm Allocation
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Void Payment Modal */}
      {selectedPayment && (
        <Modal
          isOpen={isVoidOpen}
          onClose={() => setIsVoidOpen(false)}
          title={`Void Payment ${selectedPayment.payment_no}`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div
              style={{
                padding: '0.75rem',
                borderRadius: '0.375rem',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid var(--rose-500)',
                color: 'var(--rose-400)',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertTriangle size={16} />
              Warning: Voiding this payment reverses all allocations and increases the balance due on paid invoices.
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Void Reason:
              </label>
              <textarea
                className="input"
                rows={3}
                placeholder="Reason for voiding payment..."
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setIsVoidOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ color: 'var(--rose-400)', borderColor: 'var(--rose-500)' }}
                onClick={handleVoidPayment}
              >
                Confirm Void
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Customer Statement Modal */}
      {statementCustomerId && (
        <CustomerStatementModal
          customerId={statementCustomerId}
          isOpen={isStatementOpen}
          onClose={() => setIsStatementOpen(false)}
        />
      )}
    </div>
  )
}
