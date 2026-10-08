import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Eye,
  FileCheck,
  FileText,
  History,
  Printer,
  Receipt,
  RefreshCw,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Customer, customersApi } from '../api/customers'
import {
  type CreditNoteCreatePayload,
  type Invoice,
  type InvoiceStatus,
  salesApi,
} from '../api/sales'
import { ConflictAlert } from '../components/ConflictAlert'
import { CustomerStatementModal } from '../components/CustomerStatementModal'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

export const InvoicesPage: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [customerFilter, setCustomerFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master data
  const [customers, setCustomers] = useState<Customer[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isVoidOpen, setIsVoidOpen] = useState(false)
  const [isCreditNoteOpen, setIsCreditNoteOpen] = useState(false)
  const [isStatementOpen, setIsStatementOpen] = useState(false)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [voidReason, setVoidReason] = useState('')
  const [creditReason, setCreditReason] = useState('discount')

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [invRes, custRes] = await Promise.all([
        salesApi.listInvoices({
          page,
          page_size: pageSize,
          status: statusFilter || undefined,
          customer_id: customerFilter ? Number(customerFilter) : undefined,
        }),
        customersApi.list({ page: 1, page_size: 100 }),
      ])
      setInvoices(invRes.items)
      setTotal(invRes.total)
      setCustomers(custRes.items)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load invoices data'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter, customerFilter])

  const formatMoney = (val: string | number) => {
    const num = Number(val || 0)
    return `₱${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const getStatusBadge = (status: InvoiceStatus) => {
    const styles: Record<InvoiceStatus, { bg: string; color: string; label: string }> = {
      draft: { bg: 'rgba(148, 163, 184, 0.12)', color: 'var(--text-dim)', label: 'Draft' },
      issued: { bg: 'rgba(59, 130, 246, 0.12)', color: 'var(--sky-400)', label: 'Issued' },
      partially_paid: { bg: 'rgba(245, 158, 11, 0.12)', color: 'var(--amber-400)', label: 'Partially Paid' },
      paid: { bg: 'rgba(16, 185, 129, 0.12)', color: 'var(--emerald-400)', label: 'Paid' },
      void: { bg: 'rgba(239, 68, 68, 0.12)', color: 'var(--rose-400)', label: 'Void' },
    }
    const s = styles[status] || styles.draft
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.25rem',
          padding: '0.2rem 0.55rem',
          borderRadius: '9999px',
          fontSize: '0.75rem',
          fontWeight: 600,
          background: s.bg,
          color: s.color,
          textTransform: 'uppercase',
          letterSpacing: '0.025em',
        }}
      >
        {s.label}
      </span>
    )
  }

  const handleIssueInvoice = async (inv: Invoice) => {
    try {
      const idempotencyKey = crypto.randomUUID()
      const updated = await salesApi.issueInvoice(inv.id, {}, idempotencyKey)
      setSuccessMessage(`Invoice ${updated.invoice_no} officially issued successfully!`)
      if (selectedInvoice?.id === inv.id) {
        setSelectedInvoice(updated)
      }
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.problem.detail)
      } else if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to issue invoice'))
      }
    }
  }

  const handleVoidInvoice = async () => {
    if (!selectedInvoice) return
    try {
      const updated = await salesApi.voidInvoice(selectedInvoice.id, voidReason)
      setSuccessMessage(`Invoice ${updated.invoice_no || selectedInvoice.id} has been voided.`)
      setIsVoidOpen(false)
      if (selectedInvoice.id === updated.id) {
        setSelectedInvoice(updated)
      }
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.problem.detail)
      } else if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to void invoice'))
      }
    }
  }

  const handleCreateCreditNote = async () => {
    if (!selectedInvoice) return
    try {
      const payload: CreditNoteCreatePayload = {
        invoice_id: selectedInvoice.id,
        reason: creditReason,
      }
      const cn = await salesApi.createCreditNote(payload)
      setSuccessMessage(`Credit Note ${cn.credit_note_no} created and applied successfully!`)
      setIsCreditNoteOpen(false)
      loadData()
      // Refresh current invoice details
      const refreshed = await salesApi.getInvoice(selectedInvoice.id)
      setSelectedInvoice(refreshed)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create credit note'))
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-bright)' }}>
            Invoices & Accounts Receivable
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-dim)', fontSize: '0.875rem' }}>
            Philippine BIR-compliant tax invoices, gapless numbering, snapshots, and receivables tracking.
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

      {conflictError && <ConflictAlert message={conflictError} onReload={loadData} />}
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
            <option value="draft">Draft</option>
            <option value="issued">Issued</option>
            <option value="partially_paid">Partially Paid</option>
            <option value="paid">Paid</option>
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

      {/* Invoices Table */}
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
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Invoice #</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Customer</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Issue Date</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Due Date</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Grand Total</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Paid / Credited</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Balance Due</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Status</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  Loading invoices...
                </td>
              </tr>
            ) : invoices.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  No invoices found. Generate an invoice from confirmed Sales Orders.
                </td>
              </tr>
            ) : (
              invoices.map((inv) => {
                const customer = customers.find((c) => c.id === inv.customer_id)
                const todayStr = new Date().toISOString().split('T')[0]
                const isOverdue =
                  inv.due_date &&
                  inv.due_date < todayStr &&
                  ['issued', 'partially_paid'].includes(inv.status)

                return (
                  <tr
                    key={inv.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>
                      {inv.invoice_no ? (
                        <span style={{ color: 'var(--brand-300)' }}>{inv.invoice_no}</span>
                      ) : (
                        <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Draft (Unissued)</span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 500, color: 'var(--text-bright)' }}>
                        {inv.customer_name_snapshot || customer?.name || `Customer #${inv.customer_id}`}
                      </div>
                      {inv.customer_tin_snapshot && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          TIN: {inv.customer_tin_snapshot}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--text-dim)' }}>
                      {inv.issue_date || '—'}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      {inv.due_date ? (
                        <span style={{ color: isOverdue ? 'var(--rose-400)' : 'var(--text-dim)', fontWeight: isOverdue ? 600 : 400 }}>
                          {inv.due_date} {isOverdue && '⚠️ Overdue'}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                      {formatMoney(inv.grand_total)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                      <div>Paid: {formatMoney(inv.amount_paid)}</div>
                      {Number(inv.amount_credited) > 0 && (
                        <div style={{ color: 'var(--amber-400)' }}>Credit: {formatMoney(inv.amount_credited)}</div>
                      )}
                    </td>
                    <td
                      style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'right',
                        fontWeight: 700,
                        color: Number(inv.balance_due) > 0 ? 'var(--rose-400)' : 'var(--emerald-400)',
                      }}
                    >
                      {formatMoney(inv.balance_due)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {getStatusBadge(inv.status)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem' }}
                          onClick={() => {
                            setSelectedInvoice(inv)
                            setIsDetailsOpen(true)
                          }}
                          title="View Printable Invoice"
                        >
                          <Eye size={12} /> View
                        </button>

                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                          onClick={() => {
                            setSelectedInvoice(inv)
                            setIsHistoryOpen(true)
                          }}
                          title="View Transition History"
                        >
                          <History size={12} />
                        </button>

                        {inv.status === 'draft' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                            onClick={() => handleIssueInvoice(inv)}
                            title="Officially Issue Invoice"
                          >
                            <FileCheck size={12} /> Issue
                          </button>
                        )}

                        {['issued', 'partially_paid'].includes(inv.status) && (
                          <>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem', color: 'var(--amber-400)' }}
                              onClick={() => {
                                setSelectedInvoice(inv)
                                setIsCreditNoteOpen(true)
                              }}
                              title="Issue Credit Note"
                            >
                              <Receipt size={12} /> Credit Note
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => {
                                setSelectedInvoice(inv)
                                setVoidReason('')
                                setIsVoidOpen(true)
                              }}
                              title="Void Invoice"
                            >
                              <XCircle size={12} /> Void
                            </button>
                          </>
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
            Showing {invoices.length > 0 ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, total)} of {total} invoices
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

      {/* Details / Printable BIR Invoice Modal */}
      {selectedInvoice && (
        <Modal
          isOpen={isDetailsOpen}
          onClose={() => setIsDetailsOpen(false)}
          title={`Invoice: ${selectedInvoice.invoice_no || `Draft #${selectedInvoice.id}`}`}
          maxWidth="950px"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Top action row */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingBottom: '0.75rem',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Document Status:</span>
                {getStatusBadge(selectedInvoice.status)}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsStatementOpen(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}
                >
                  <FileText size={14} /> Customer AR Statement
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => window.print()}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}
                >
                  <Printer size={14} /> Print BIR Layout
                </button>
              </div>
            </div>

            {/* Printable BIR Invoice Container */}
            <div
              id="printable-invoice"
              style={{
                background: 'var(--bg-page)',
                padding: '1.5rem',
                borderRadius: '0.5rem',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                flexDirection: 'column',
                gap: '1.5rem',
              }}
            >
              {/* Header: Company & Official Title */}
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid var(--brand-500)', paddingBottom: '1rem' }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800, color: 'var(--brand-300)' }}>
                    ANTIGRAVITY SYSTEMS PHILIPPINES CORP.
                  </h2>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                    VAT Reg. TIN: 009-876-543-000 | BIR CAS Accredited
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                    Enterprise Tower 1, Ayala Avenue, Makati City, Metro Manila
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '0.05em', color: 'var(--text-bright)' }}>
                    SALES INVOICE
                  </div>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--brand-300)', marginTop: '0.25rem' }}>
                    {selectedInvoice.invoice_no || 'DRAFT (PRE-ISSUE)'}
                  </div>
                </div>
              </div>

              {/* Customer & Document Information */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                  gap: '1.5rem',
                  fontSize: '0.85rem',
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--text-dim)', marginBottom: '0.35rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>
                    Billed To (Customer):
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-bright)' }}>
                    {selectedInvoice.customer_name_snapshot || 'Customer Name'}
                  </div>
                  <div style={{ color: 'var(--text-dim)', marginTop: '0.15rem' }}>
                    TIN: {selectedInvoice.customer_tin_snapshot || 'N/A'}
                  </div>
                  <div style={{ color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                    Address: {selectedInvoice.billing_address_snapshot || 'No registered billing address'}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '0.75rem 1rem', borderRadius: '0.375rem', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.35rem 1rem' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Invoice Date:</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{selectedInvoice.issue_date || 'Draft'}</span>
                    <span style={{ color: 'var(--text-dim)' }}>Due Date:</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{selectedInvoice.due_date || '—'}</span>
                    <span style={{ color: 'var(--text-dim)' }}>Currency:</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{selectedInvoice.currency_code} (PHP)</span>
                    {selectedInvoice.sales_order_id && (
                      <>
                        <span style={{ color: 'var(--text-dim)' }}>Origin Order:</span>
                        <span style={{ fontWeight: 600, color: 'var(--brand-300)' }}>SO #{selectedInvoice.sales_order_id}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Line Items Table */}
              <div>
                <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-card)', borderBottom: '1px solid var(--border-subtle)' }}>
                      <th style={{ padding: '0.5rem', textAlign: 'center', width: '40px' }}>#</th>
                      <th style={{ padding: '0.5rem', textAlign: 'left' }}>Item Description</th>
                      <th style={{ padding: '0.5rem', textAlign: 'center', width: '60px' }}>UoM</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '80px' }}>Qty</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '100px' }}>Unit Price</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '80px' }}>Discount</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '80px' }}>VAT Rate</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '100px' }}>Line Net</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '100px' }}>VAT (12%)</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right', width: '110px' }}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedInvoice.items?.map((it) => (
                      <tr key={it.id || it.line_no} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.5rem', textAlign: 'center' }}>{it.line_no}</td>
                        <td style={{ padding: '0.5rem', fontWeight: 500 }}>{it.description}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'center', color: 'var(--text-dim)' }}>{it.uom}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>{Number(it.quantity).toFixed(2)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>{formatMoney(it.unit_price)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', color: Number(it.discount_amount) > 0 ? 'var(--amber-400)' : 'var(--text-dim)' }}>
                          {formatMoney(it.discount_amount)}
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-dim)' }}>
                          {(Number(it.tax_rate) * 100).toFixed(0)}%
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>{formatMoney(it.line_net)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>{formatMoney(it.line_tax)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>{formatMoney(it.line_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Financial Totals Breakdown & Statutory VAT Display */}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <div
                  style={{
                    width: '340px',
                    background: 'var(--bg-card)',
                    padding: '1rem',
                    borderRadius: '0.375rem',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.5rem',
                    fontSize: '0.85rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-dim)' }}>
                    <span>VATable Sales (Subtotal):</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{formatMoney(selectedInvoice.subtotal)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-dim)' }}>
                    <span>Value Added Tax (12%):</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{formatMoney(selectedInvoice.tax_total)}</span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      borderTop: '1px solid var(--border-subtle)',
                      paddingTop: '0.5rem',
                      fontWeight: 700,
                      fontSize: '0.95rem',
                    }}
                  >
                    <span>Total Amount Due:</span>
                    <span style={{ color: 'var(--brand-300)' }}>{formatMoney(selectedInvoice.grand_total)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--emerald-400)', paddingTop: '0.25rem' }}>
                    <span>Total Payments Allocated:</span>
                    <span>- {formatMoney(selectedInvoice.amount_paid)}</span>
                  </div>
                  {Number(selectedInvoice.amount_credited) > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--amber-400)' }}>
                      <span>Credit Notes Applied:</span>
                      <span>- {formatMoney(selectedInvoice.amount_credited)}</span>
                    </div>
                  )}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      borderTop: '2px solid var(--brand-500)',
                      paddingTop: '0.5rem',
                      fontWeight: 800,
                      fontSize: '1.05rem',
                      color: Number(selectedInvoice.balance_due) > 0 ? 'var(--rose-400)' : 'var(--emerald-400)',
                    }}
                  >
                    <span>Remaining Balance Due:</span>
                    <span>{formatMoney(selectedInvoice.balance_due)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Credit Note Modal */}
      {selectedInvoice && (
        <Modal
          isOpen={isCreditNoteOpen}
          onClose={() => setIsCreditNoteOpen(false)}
          title={`Create Credit Note for Invoice ${selectedInvoice.invoice_no || selectedInvoice.id}`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-dim)' }}>
              Issuing a credit note will directly reduce the outstanding balance due on this invoice and record an audit adjustment.
            </p>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Reason for Credit Note:
              </label>
              <select
                className="input"
                value={creditReason}
                onChange={(e) => setCreditReason(e.target.value)}
              >
                <option value="discount">Price Discount / Rebate</option>
                <option value="pricing_error">Pricing Error Correction</option>
                <option value="damaged">Damaged Goods Upon Receipt</option>
                <option value="returned">Product Return</option>
                <option value="other">Other Commercial Adjustment</option>
              </select>
            </div>
            <div
              style={{
                padding: '0.75rem',
                borderRadius: '0.375rem',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-dim)' }}>Current Balance Due:</span>
                <span style={{ fontWeight: 700, color: 'var(--rose-400)' }}>{formatMoney(selectedInvoice.balance_due)}</span>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setIsCreditNoteOpen(false)}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" onClick={handleCreateCreditNote}>
                Issue Credit Note
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Void Invoice Confirmation Modal */}
      {selectedInvoice && (
        <Modal
          isOpen={isVoidOpen}
          onClose={() => setIsVoidOpen(false)}
          title={`Void Invoice ${selectedInvoice.invoice_no || selectedInvoice.id}`}
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
              Warning: Voiding is irreversible. It restores invoiced quantities on the parent order.
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.35rem' }}>
                Reason for Voiding:
              </label>
              <textarea
                className="input"
                rows={3}
                placeholder="Reason for voiding this invoice..."
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
                onClick={handleVoidInvoice}
              >
                Confirm Void
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Status History Timeline Modal */}
      {selectedInvoice && (
        <Modal
          isOpen={isHistoryOpen}
          onClose={() => setIsHistoryOpen(false)}
          title={`History: Invoice ${selectedInvoice.invoice_no || selectedInvoice.id}`}
        >
          <StatusHistoryTimeline entityType="invoice" entityId={selectedInvoice.id} />
        </Modal>
      )}

      {/* Customer Statement Modal */}
      {selectedInvoice && (
        <CustomerStatementModal
          customerId={selectedInvoice.customer_id}
          customerName={selectedInvoice.customer_name_snapshot || undefined}
          isOpen={isStatementOpen}
          onClose={() => setIsStatementOpen(false)}
        />
      )}
    </div>
  )
}
