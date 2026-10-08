import React, { useEffect, useState } from 'react'
import { AlertCircle, CreditCard, FileText, Printer, Receipt } from 'lucide-react'
import { ApiError } from '../api/client'
import { type CustomerStatement, salesApi } from '../api/sales'
import { Modal } from './Modal'

interface Props {
  customerId: number
  customerName?: string
  isOpen: boolean
  onClose: () => void
}

export const CustomerStatementModal: React.FC<Props> = ({
  customerId,
  customerName,
  isOpen,
  onClose,
}) => {
  const [statement, setStatement] = useState<CustomerStatement | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && customerId) {
      loadStatement()
    }
  }, [isOpen, customerId])

  const loadStatement = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await salesApi.getCustomerStatement(customerId)
      setStatement(data)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.problem.detail)
      } else {
        setError('Failed to load customer statement.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const formatMoney = (val: string | number) => {
    const num = Number(val || 0)
    return `₱${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const handlePrint = () => {
    window.print()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Accounts Receivable Statement - ${statement?.customer_name || customerName || 'Customer'}`}
      maxWidth="900px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        {error && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: '0.375rem',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid var(--rose-500)',
              color: 'var(--rose-400)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.85rem',
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
            Loading statement transactions...
          </div>
        ) : statement ? (
          <>
            {/* Top print button & metadata */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingBottom: '0.75rem',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>As of Statement Date:</div>
                <div style={{ fontWeight: 600, color: 'var(--text-bright)' }}>{statement.statement_date}</div>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handlePrint}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
              >
                <Printer size={15} /> Print Statement
              </button>
            </div>

            {/* Summary KPI Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: '0.75rem',
              }}
            >
              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                  Total Invoiced
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-bright)' }}>
                  {formatMoney(statement.total_invoiced)}
                </div>
              </div>

              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                  Total Payments
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--emerald-400)' }}>
                  {formatMoney(statement.total_paid)}
                </div>
              </div>

              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                  Credit Notes
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--amber-400)' }}>
                  {formatMoney(statement.total_credited)}
                </div>
              </div>

              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                  Customer Credit
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--sky-400)' }}>
                  {formatMoney(statement.unallocated_credit)}
                </div>
              </div>

              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.5rem',
                  background: 'rgba(99, 102, 241, 0.08)',
                  border: '1px solid var(--brand-500)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--brand-300)', marginBottom: '0.25rem' }}>
                  Net AR Balance
                </div>
                <div
                  style={{
                    fontSize: '1.15rem',
                    fontWeight: 700,
                    color: Number(statement.open_ar_balance) > 0 ? 'var(--rose-400)' : 'var(--emerald-400)',
                  }}
                >
                  {formatMoney(statement.open_ar_balance)}
                </div>
              </div>
            </div>

            {/* Transactions Ledger Table */}
            <div>
              <h4 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-bright)' }}>
                Activity Ledger & Running Balance
              </h4>
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: '0.375rem', overflow: 'hidden' }}>
                <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-page)', borderBottom: '1px solid var(--border-subtle)' }}>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left' }}>Date</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left' }}>Type</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left' }}>Document #</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left' }}>Reference</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Invoiced (Debit)</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Paid / Credited</th>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Running Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statement.transactions.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-dim)' }}>
                          No recorded financial transactions for this customer.
                        </td>
                      </tr>
                    ) : (
                      statement.transactions.map((tx, idx) => {
                        const isInvoiced = Number(tx.amount_invoiced) > 0
                        const isPaid = Number(tx.amount_paid) > 0
                        return (
                          <tr
                            key={idx}
                            style={{
                              borderBottom: '1px solid var(--border-subtle)',
                              background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                            }}
                          >
                            <td style={{ padding: '0.6rem 0.75rem' }}>{tx.date}</td>
                            <td style={{ padding: '0.6rem 0.75rem' }}>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  padding: '0.15rem 0.45rem',
                                  borderRadius: '0.25rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 500,
                                  background:
                                    tx.doc_type === 'invoice'
                                      ? 'rgba(99, 102, 241, 0.12)'
                                      : tx.doc_type === 'payment'
                                      ? 'rgba(16, 185, 129, 0.12)'
                                      : 'rgba(245, 158, 11, 0.12)',
                                  color:
                                    tx.doc_type === 'invoice'
                                      ? 'var(--brand-300)'
                                      : tx.doc_type === 'payment'
                                      ? 'var(--emerald-400)'
                                      : 'var(--amber-400)',
                                }}
                              >
                                {tx.doc_type === 'invoice' && <FileText size={12} />}
                                {tx.doc_type === 'payment' && <CreditCard size={12} />}
                                {tx.doc_type === 'credit_note' && <Receipt size={12} />}
                                {tx.doc_type.replace('_', ' ').toUpperCase()}
                              </span>
                            </td>
                            <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600 }}>{tx.doc_no}</td>
                            <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-dim)' }}>{tx.reference || '—'}</td>
                            <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: isInvoiced ? 600 : 400 }}>
                              {isInvoiced ? formatMoney(tx.amount_invoiced) : '—'}
                            </td>
                            <td
                              style={{
                                padding: '0.6rem 0.75rem',
                                textAlign: 'right',
                                color: isPaid ? 'var(--emerald-400)' : 'inherit',
                                fontWeight: isPaid ? 600 : 400,
                              }}
                            >
                              {isPaid ? `(${formatMoney(tx.amount_paid)})` : '—'}
                            </td>
                            <td
                              style={{
                                padding: '0.6rem 0.75rem',
                                textAlign: 'right',
                                fontWeight: 700,
                                color: Number(tx.running_balance) > 0 ? 'var(--text-bright)' : 'var(--emerald-400)',
                              }}
                            >
                              {formatMoney(tx.running_balance)}
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  )
}
