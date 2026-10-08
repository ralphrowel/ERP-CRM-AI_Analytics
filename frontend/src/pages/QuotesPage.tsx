import React, { useEffect, useState } from 'react'
import {
  CheckCircle,
  FileText,
  History,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Customer, customersApi } from '../api/customers'
import { type Product, productsApi } from '../api/products'
import {
  type Quote,
  type QuoteCreatePayload,
  type QuoteStatus,
  salesApi,
  type TaxRate,
} from '../api/sales'
import { ConflictAlert } from '../components/ConflictAlert'
import { LineItemsEditor } from '../components/LineItemsEditor'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

export const QuotesPage: React.FC = () => {
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master data for line items
  const [customers, setCustomers] = useState<Customer[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [taxRates, setTaxRates] = useState<TaxRate[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isRejectOpen, setIsRejectOpen] = useState(false)
  const [isCancelOpen, setIsCancelOpen] = useState(false)
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null)
  const [reasonInput, setReasonInput] = useState('')

  // Create form state
  const [formData, setFormData] = useState<QuoteCreatePayload>({
    customer_id: 0,
    valid_until: '',
    notes: '',
    items: [],
  })

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [quotesRes, custRes, prodRes, trRes] = await Promise.all([
        salesApi.listQuotes({ page, page_size: pageSize, status: statusFilter || undefined }),
        customersApi.list({ page: 1, page_size: 100 }),
        productsApi.list({ page: 1, page_size: 100 }),
        salesApi.listTaxRates(),
      ])
      setQuotes(quotesRes.items)
      setTotal(quotesRes.total)
      setCustomers(custRes.items)
      setProducts(prodRes.items)
      setTaxRates(trRes)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load quotes data'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter])

  const handleCreateQuote = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.customer_id) {
      setGeneralError(new Error('Please select a customer.'))
      return
    }
    if (formData.items.length === 0) {
      setGeneralError(new Error('Quote must contain at least one line item.'))
      return
    }

    try {
      const created = await salesApi.createQuote(formData)
      setIsCreateOpen(false)
      setFormData({ customer_id: 0, valid_until: '', notes: '', items: [] })
      setSuccessMessage(`Quote ${created.quote_no} created successfully`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create quote'))
      }
    }
  }

  const handleSend = async (q: Quote) => {
    try {
      await salesApi.sendQuote(q.id)
      setSuccessMessage(`Quote ${q.quote_no} sent to customer`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) setConflictError('Conflict: Quote was modified concurrently.')
        else setGeneralError(err)
      }
    }
  }

  const handleAccept = async (q: Quote) => {
    try {
      await salesApi.acceptQuote(q.id)
      setSuccessMessage(`Quote ${q.quote_no} accepted! Opportunity marked won if linked.`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) setConflictError('Conflict: Quote was modified concurrently.')
        else setGeneralError(err)
      }
    }
  }

  const handleCreateOrder = async (q: Quote) => {
    try {
      const order = await salesApi.createOrderFromQuote(q.id)
      setSuccessMessage(`Sales Order ${order.order_no} created from quote!`)
      setTimeout(() => setSuccessMessage(null), 5000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) setConflictError('Conflict: Quote was modified concurrently.')
        else setGeneralError(err)
      }
    }
  }

  const handleRejectConfirm = async () => {
    if (!selectedQuote) return
    try {
      await salesApi.rejectQuote(selectedQuote.id, reasonInput)
      setIsRejectOpen(false)
      setSelectedQuote(null)
      setSuccessMessage(`Quote marked rejected`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleCancelConfirm = async () => {
    if (!selectedQuote) return
    try {
      await salesApi.cancelQuote(selectedQuote.id, reasonInput)
      setIsCancelOpen(false)
      setSelectedQuote(null)
      setSuccessMessage(`Quote cancelled`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const formatCurrency = (val: string) =>
    new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(parseFloat(val || '0'))

  const getStatusBadge = (status: QuoteStatus) => {
    switch (status) {
      case 'draft':
        return <span className="badge badge-subtle">Draft</span>
      case 'sent':
        return <span className="badge badge-cyan">Sent</span>
      case 'accepted':
        return <span className="badge badge-emerald">Accepted</span>
      case 'rejected':
        return <span className="badge badge-rose">Rejected</span>
      case 'cancelled':
        return <span className="badge badge-rose">Cancelled</span>
      case 'expired':
        return <span className="badge badge-amber">Expired</span>
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f8fafc' }}>
            Commercial Quotes
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Document line-item proposals with 12% VAT calculations, price snapshots, and opportunity synchronization.
          </p>
        </div>

        <button
          className="btn btn-primary"
          onClick={() => {
            const d = new Date()
            d.setDate(d.getDate() + 30)
            setFormData({
              customer_id: customers[0]?.id || 0,
              valid_until: d.toISOString().split('T')[0],
              notes: '',
              items: [],
            })
            setIsCreateOpen(true)
          }}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <Plus size={16} /> New Commercial Quote
        </button>
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
        className="card"
        style={{
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          backgroundColor: 'var(--bg-surface)',
        }}
      >
        <select
          className="input-field"
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
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <button onClick={() => loadData()} className="btn btn-secondary" title="Refresh">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Quotes Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Quote #
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Customer Account
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Status
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Valid Until
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', textAlign: 'right' }}>
                Grand Total (₱)
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', textAlign: 'right' }}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  <RefreshCw className="animate-spin" size={20} style={{ margin: '0 auto 0.5rem' }} />
                  <div>Loading quotes ledger...</div>
                </td>
              </tr>
            ) : quotes.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  No quotes found.
                </td>
              </tr>
            ) : (
              quotes.map((q) => {
                const customer = customers.find((c) => c.id === q.customer_id)
                return (
                  <tr key={q.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontSize: '0.85rem', color: '#a5b4fc', fontWeight: 600 }}>
                      {q.quote_no}
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: '#f8fafc' }}>
                        {customer ? customer.name : `Customer #${q.customer_id}`}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                        {q.items.length} line item{q.items.length > 1 ? 's' : ''}
                      </div>
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>{getStatusBadge(q.status)}</td>
                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                      {q.valid_until || '—'}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: '0.9rem', color: '#38bdf8' }}>
                      {formatCurrency(q.grand_total)}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.35rem' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                          title="Audit Trail"
                          onClick={() => {
                            setSelectedQuote(q)
                            setIsHistoryOpen(true)
                          }}
                        >
                          <History size={13} />
                        </button>

                        {q.status === 'draft' && (
                          <>
                            <button
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                              onClick={() => handleSend(q)}
                            >
                              <Send size={12} /> Send
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => {
                                setSelectedQuote(q)
                                setReasonInput('')
                                setIsCancelOpen(true)
                              }}
                              title="Cancel Quote"
                            >
                              <XCircle size={13} />
                            </button>
                          </>
                        )}

                        {q.status === 'sent' && (
                          <>
                            <button
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', backgroundColor: 'var(--emerald-600)', borderColor: 'var(--emerald-600)' }}
                              onClick={() => handleAccept(q)}
                            >
                              Accept
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => {
                                setSelectedQuote(q)
                                setReasonInput('')
                                setIsRejectOpen(true)
                              }}
                              title="Reject Quote"
                            >
                              Reject
                            </button>
                          </>
                        )}

                        {q.status === 'accepted' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                            onClick={() => handleCreateOrder(q)}
                          >
                            <Sparkles size={12} /> Convert to Order
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

        {/* Pagination footer */}
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
            Showing {quotes.length > 0 ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, total)} of {total} quotes
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

      {/* Modal: Create Quote */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Commercial Quote">
        <form onSubmit={handleCreateQuote} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="form-label">Customer Account *</label>
              <select
                required
                className="input-field"
                value={formData.customer_id}
                onChange={(e) => setFormData({ ...formData, customer_id: Number(e.target.value) })}
              >
                <option value="">-- Select Customer --</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.customer_no}) - {c.status}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Valid Until</label>
              <input
                type="date"
                className="input-field"
                value={formData.valid_until || ''}
                onChange={(e) => setFormData({ ...formData, valid_until: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="form-label">Proposal Line Items</label>
            <LineItemsEditor
              items={formData.items}
              onChange={(newItems) => setFormData({ ...formData, items: newItems })}
              products={products}
              taxRates={taxRates}
            />
          </div>

          <div>
            <label className="form-label">Terms & Notes</label>
            <textarea
              rows={2}
              className="input-field"
              placeholder="Commercial delivery lead time, warranty terms..."
              value={formData.notes || ''}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <FileText size={16} /> Save Draft Quote
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Reject Quote */}
      <Modal isOpen={isRejectOpen} onClose={() => setIsRejectOpen(false)} title="Reject Quote">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Record customer rejection for <strong>{selectedQuote?.quote_no}</strong>:
          </p>
          <textarea
            rows={3}
            className="input-field"
            placeholder="Reason for rejection (e.g. Price too high, chose competitor)..."
            value={reasonInput}
            onChange={(e) => setReasonInput(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setIsRejectOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              style={{ backgroundColor: 'var(--rose-500)', borderColor: 'var(--rose-500)' }}
              onClick={handleRejectConfirm}
            >
              Confirm Rejection
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal: Cancel Quote */}
      <Modal isOpen={isCancelOpen} onClose={() => setIsCancelOpen(false)} title="Cancel Quote">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Are you sure you want to cancel <strong>{selectedQuote?.quote_no}</strong>?
          </p>
          <textarea
            rows={3}
            className="input-field"
            placeholder="Reason for cancellation..."
            value={reasonInput}
            onChange={(e) => setReasonInput(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setIsCancelOpen(false)}>
              Back
            </button>
            <button
              className="btn btn-primary"
              style={{ backgroundColor: 'var(--rose-500)', borderColor: 'var(--rose-500)' }}
              onClick={handleCancelConfirm}
            >
              Cancel Quote
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal: Status History */}
      <Modal
        isOpen={isHistoryOpen}
        onClose={() => {
          setIsHistoryOpen(false)
          setSelectedQuote(null)
        }}
        title={`Audit Trail: ${selectedQuote?.quote_no}`}
      >
        {selectedQuote && <StatusHistoryTimeline entityType="quote" entityId={selectedQuote.id} />}
      </Modal>
    </div>
  )
}
