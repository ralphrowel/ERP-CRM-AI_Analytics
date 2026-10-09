import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  Edit2,
  Filter,
  RefreshCw,
  Sliders,
  X,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type ApprovalDecisionPayload,
  type ApprovalRequest,
  type ApprovalRequestStatus,
  type ApprovalRule,
  type ApprovalRuleUpdatePayload,
  workflowApi,
} from '../api/workflow'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { useAuth } from '../context/AuthContext'

export const ApprovalsPage: React.FC = () => {
  const { user, hasPermission, isSuperuser } = useAuth()

  // Tabs: 'inbox' | 'rules'
  const [activeTab, setActiveTab] = useState<'inbox' | 'rules'>('inbox')

  // Inbox filters
  const [statusFilter, setStatusFilter] = useState<ApprovalRequestStatus | 'all'>('pending')
  const [entityFilter, setEntityFilter] = useState<string>('all')

  // Data states
  const [requests, setRequests] = useState<ApprovalRequest[]>([])
  const [totalRequests, setTotalRequests] = useState(0)
  const [rules, setRules] = useState<ApprovalRule[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Feedback states
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Decision Modal
  const [selectedRequest, setSelectedRequest] = useState<ApprovalRequest | null>(null)
  const [decisionAction, setDecisionAction] = useState<'approved' | 'rejected'>('approved')
  const [decisionComment, setDecisionComment] = useState('')
  const [isDeciding, setIsDeciding] = useState(false)

  // Rule Edit Modal
  const [selectedRule, setSelectedRule] = useState<ApprovalRule | null>(null)
  const [editDesc, setEditDesc] = useState('')
  const [editAmount, setEditAmount] = useState('')
  const [editPct, setEditPct] = useState('')
  const [editPerm, setEditPerm] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [isSavingRule, setIsSavingRule] = useState(false)

  const canDecide = isSuperuser || hasPermission('approval_request:decide')
  const canManageRules = isSuperuser || hasPermission('approval_rule:update')

  const fetchData = async () => {
    setIsLoading(true)
    setGeneralError(null)
    setConflictError(null)
    try {
      const [reqsRes, rulesRes] = await Promise.all([
        workflowApi.listRequests({
          status: statusFilter === 'all' ? undefined : statusFilter,
          entity_type: entityFilter === 'all' ? undefined : entityFilter,
          page: 1,
          page_size: 50,
        }),
        workflowApi.listRules(),
      ])
      setRequests(reqsRes.items)
      setTotalRequests(reqsRes.total)
      setRules(rulesRes)
    } catch (err: unknown) {
      if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [statusFilter, entityFilter])

  // Handle Decision
  const handleOpenDecision = (req: ApprovalRequest, action: 'approved' | 'rejected') => {
    setSelectedRequest(req)
    setDecisionAction(action)
    setDecisionComment('')
    setConflictError(null)
  }

  const handleSubmitDecision = async () => {
    if (!selectedRequest) return
    setIsDeciding(true)
    setGeneralError(null)
    setConflictError(null)

    try {
      const payload: ApprovalDecisionPayload = {
        decision: decisionAction,
        comment: decisionComment.trim() || null,
      }
      await workflowApi.decideRequest(selectedRequest.id, payload)
      setSuccessMessage(
        `Request #${selectedRequest.id} successfully ${decisionAction === 'approved' ? 'approved' : 'rejected'}.`
      )
      setSelectedRequest(null)
      fetchData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.problem?.detail || 'This approval request was modified concurrently.')
      } else if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setIsDeciding(false)
    }
  }

  // Handle Rule Edit
  const handleOpenEditRule = (rule: ApprovalRule) => {
    setSelectedRule(rule)
    setEditDesc(rule.description || '')
    setEditAmount(rule.threshold_amount ? String(rule.threshold_amount) : '')
    setEditPct(rule.threshold_pct ? String(Number(rule.threshold_pct) * 100) : '')
    setEditPerm(rule.approver_permission)
    setEditActive(rule.is_active)
    setConflictError(null)
  }

  const handleSaveRule = async () => {
    if (!selectedRule) return
    setIsSavingRule(true)
    setGeneralError(null)
    setConflictError(null)

    try {
      const payload: ApprovalRuleUpdatePayload = {
        description: editDesc.trim() || null,
        threshold_amount: editAmount.trim() ? editAmount.trim() : null,
        threshold_pct: editPct.trim() ? (parseFloat(editPct) / 100).toFixed(4) : null,
        approver_permission: editPerm.trim() || undefined,
        is_active: editActive,
        version: selectedRule.version,
      }
      await workflowApi.updateRule(selectedRule.id, payload)
      setSuccessMessage(`Rule '${selectedRule.code}' updated successfully without redeployment.`)
      setSelectedRule(null)
      fetchData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(
          err.problem?.detail || 'Approval rule was updated by another administrator. Please refresh.'
        )
      } else if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setIsSavingRule(false)
    }
  }

  // Summary counts
  const pendingCount = requests.filter((r) => r.status === 'pending').length
  const approvedCount = requests.filter((r) => r.status === 'approved').length
  const rejectedCount = requests.filter((r) => r.status === 'rejected').length

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
          <h1
            style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              color: 'var(--text-main)',
              letterSpacing: '-0.02em',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
            }}
          >
            <CheckCircle2 size={28} color="var(--primary)" />
            Workflow Engine & Approvals
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Multi-tier separation-of-duties governance, spend limits, and dynamic thresholds.
          </p>
        </div>

        <button
          onClick={fetchData}
          disabled={isLoading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.6rem 1.1rem',
            backgroundColor: 'var(--bg-card)',
            color: 'var(--text-main)',
            border: '1px solid var(--border-card)',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 500,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          <RefreshCw size={15} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Global Alerts */}
      {generalError && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ProblemAlert error={generalError} onDismiss={() => setGeneralError(null)} />
        </div>
      )}
      {conflictError && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ConflictAlert message={conflictError} onReload={fetchData} />
        </div>
      )}
      {successMessage && (
        <div
          style={{
            marginBottom: '1.5rem',
            padding: '1rem 1.25rem',
            borderRadius: '8px',
            backgroundColor: 'var(--emerald-bg)',
            border: '1px solid var(--emerald-border)',
            color: 'var(--emerald)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Check size={18} />
            <span>{successMessage}</span>
          </div>
          <button
            onClick={() => setSuccessMessage(null)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--emerald)',
              cursor: 'pointer',
            }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Quick Metrics Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <div
          className="glass-panel"
          style={{
            padding: '1.25rem',
            borderLeft: '4px solid var(--amber)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <Clock size={28} color="var(--amber)" />
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Pending In Queue
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--amber)' }}>
              {pendingCount}
            </div>
          </div>
        </div>

        <div
          className="glass-panel"
          style={{
            padding: '1.25rem',
            borderLeft: '4px solid var(--emerald)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <CheckCircle2 size={28} color="var(--emerald)" />
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Approved
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--emerald)' }}>
              {approvedCount}
            </div>
          </div>
        </div>

        <div
          className="glass-panel"
          style={{
            padding: '1.25rem',
            borderLeft: '4px solid var(--rose)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <XCircle size={28} color="var(--rose)" />
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Rejected
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--rose)' }}>
              {rejectedCount}
            </div>
          </div>
        </div>

        <div
          className="glass-panel"
          style={{
            padding: '1.25rem',
            borderLeft: '4px solid var(--primary)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <Sliders size={28} color="var(--primary)" />
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Active Rules
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--primary)' }}>
              {rules.filter((r) => r.is_active).length}
            </div>
          </div>
        </div>
      </div>

      {/* Main Tabs Navigation */}
      <div
        style={{
          display: 'flex',
          gap: '1rem',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '1.5rem',
        }}
      >
        <button
          onClick={() => setActiveTab('inbox')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.75rem 1.25rem',
            backgroundColor: 'transparent',
            border: 'none',
            borderBottom: activeTab === 'inbox' ? '2px solid var(--primary)' : '2px solid transparent',
            color: activeTab === 'inbox' ? 'var(--primary)' : 'var(--text-muted)',
            fontWeight: 600,
            fontSize: '0.95rem',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          <Clock size={18} />
          Approvals Queue
          {pendingCount > 0 && (
            <span
              style={{
                backgroundColor: 'var(--amber-bg)',
                color: 'var(--amber)',
                fontSize: '0.75rem',
                padding: '0.1rem 0.5rem',
                borderRadius: '9999px',
                border: '1px solid var(--amber-border)',
              }}
            >
              {pendingCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('rules')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.75rem 1.25rem',
            backgroundColor: 'transparent',
            border: 'none',
            borderBottom: activeTab === 'rules' ? '2px solid var(--primary)' : '2px solid transparent',
            color: activeTab === 'rules' ? 'var(--primary)' : 'var(--text-muted)',
            fontWeight: 600,
            fontSize: '0.95rem',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          <Sliders size={18} />
          Dynamic Threshold Rules
        </button>
      </div>

      {/* TAB 1: APPROVALS QUEUE */}
      {activeTab === 'inbox' && (
        <div>
          {/* Filter Bar */}
          <div
            className="glass-panel"
            style={{
              padding: '1rem 1.25rem',
              marginBottom: '1.5rem',
              display: 'flex',
              gap: '1.5rem',
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Filter size={16} color="var(--text-muted)" />
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as any)}
                style={{
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.4rem 0.8rem',
                  fontSize: '0.85rem',
                }}
              >
                <option value="pending">Pending Review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="all">All Statuses</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Entity:</span>
              <select
                value={entityFilter}
                onChange={(e) => setEntityFilter(e.target.value)}
                style={{
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.4rem 0.8rem',
                  fontSize: '0.85rem',
                }}
              >
                <option value="all">All Documents</option>
                <option value="sales_order">Sales Orders</option>
                <option value="purchase_order">Purchase Orders</option>
              </select>
            </div>

            <span style={{ marginLeft: 'auto', fontSize: '0.85rem', color: 'var(--text-dim)' }}>
              Showing {requests.length} of {totalRequests} items
            </span>
          </div>

          {/* Requests Table */}
          <div className="glass-panel" style={{ overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderBottom: '1px solid var(--border-subtle)',
                  }}
                >
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    ID / Ref
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Entity & Document
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Triggered Rule
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Requested By
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Status
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Decision / Notes
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {requests.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      style={{
                        padding: '3rem',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                      }}
                    >
                      No approval requests matching the current filters.
                    </td>
                  </tr>
                ) : (
                  requests.map((req) => {
                    const isSelfRequest = user?.id === req.requested_by

                    return (
                      <tr
                        key={req.id}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          transition: 'background-color 0.15s ease',
                        }}
                      >
                        <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: 'var(--text-main)' }}>
                          #{req.id}
                        </td>
                        <td style={{ padding: '1rem 1.25rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize' }}>
                            {req.entity_type.replace('_', ' ')}
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                            Document ID: {req.entity_id}
                          </div>
                        </td>
                        <td style={{ padding: '1rem 1.25rem' }}>
                          <span
                            style={{
                              backgroundColor: 'rgba(99, 102, 241, 0.1)',
                              color: 'var(--primary)',
                              border: '1px solid rgba(99, 102, 241, 0.25)',
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                            }}
                          >
                            {req.rule_code}
                          </span>
                        </td>
                        <td style={{ padding: '1rem 1.25rem' }}>
                          <div style={{ color: 'var(--text-main)', fontSize: '0.9rem' }}>
                            {req.requester_name}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                            {new Date(req.requested_at).toLocaleString()}
                          </div>
                        </td>
                        <td style={{ padding: '1rem 1.25rem' }}>
                          {req.status === 'pending' && (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                backgroundColor: 'var(--amber-bg)',
                                color: 'var(--amber)',
                                border: '1px solid var(--amber-border)',
                                padding: '0.25rem 0.6rem',
                                borderRadius: '9999px',
                                fontSize: '0.8rem',
                                fontWeight: 600,
                              }}
                            >
                              <Clock size={12} /> Pending
                            </span>
                          )}
                          {req.status === 'approved' && (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                backgroundColor: 'var(--emerald-bg)',
                                color: 'var(--emerald)',
                                border: '1px solid var(--emerald-border)',
                                padding: '0.25rem 0.6rem',
                                borderRadius: '9999px',
                                fontSize: '0.8rem',
                                fontWeight: 600,
                              }}
                            >
                              <CheckCircle2 size={12} /> Approved
                            </span>
                          )}
                          {req.status === 'rejected' && (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                backgroundColor: 'var(--rose-bg)',
                                color: 'var(--rose)',
                                border: '1px solid var(--rose-border)',
                                padding: '0.25rem 0.6rem',
                                borderRadius: '9999px',
                                fontSize: '0.8rem',
                                fontWeight: 600,
                              }}
                            >
                              <XCircle size={12} /> Rejected
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '1rem 1.25rem', fontSize: '0.85rem' }}>
                          {req.decider_name ? (
                            <div>
                              <div style={{ color: 'var(--text-main)' }}>
                                Decided by: {req.decider_name}
                              </div>
                              {req.comment && (
                                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', marginTop: '0.2rem' }}>
                                  "{req.comment}"
                                </div>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--text-dim)' }}>Awaiting decision</span>
                          )}
                        </td>
                        <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                          {req.status === 'pending' ? (
                            isSelfRequest ? (
                              <div
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.35rem',
                                  backgroundColor: 'rgba(239, 68, 68, 0.08)',
                                  color: 'var(--rose)',
                                  border: '1px solid var(--rose-border)',
                                  padding: '0.3rem 0.6rem',
                                  borderRadius: '6px',
                                  fontSize: '0.75rem',
                                }}
                                title="Separation of duties invariant: Requesters cannot approve or reject their own requests."
                              >
                                <AlertCircle size={13} />
                                Self-Request (Locked)
                              </div>
                            ) : canDecide ? (
                              <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                                <button
                                  onClick={() => handleOpenDecision(req, 'approved')}
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.3rem',
                                    padding: '0.35rem 0.75rem',
                                    backgroundColor: 'var(--emerald-bg)',
                                    color: 'var(--emerald)',
                                    border: '1px solid var(--emerald-border)',
                                    borderRadius: '6px',
                                    fontSize: '0.8rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  <Check size={14} /> Approve
                                </button>
                                <button
                                  onClick={() => handleOpenDecision(req, 'rejected')}
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.3rem',
                                    padding: '0.35rem 0.75rem',
                                    backgroundColor: 'var(--rose-bg)',
                                    color: 'var(--rose)',
                                    border: '1px solid var(--rose-border)',
                                    borderRadius: '6px',
                                    fontSize: '0.8rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  <X size={14} /> Reject
                                </button>
                              </div>
                            ) : (
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                                Reviewer auth required
                              </span>
                            )
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                              Completed
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: DYNAMIC THRESHOLD RULES (ADMIN) */}
      {activeTab === 'rules' && (
        <div>
          <div
            style={{
              marginBottom: '1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)' }}>
                Configurable Approval Rules Register
              </h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Thresholds are evaluated dynamically at runtime from PostgreSQL without code redeployment.
              </p>
            </div>
          </div>

          <div className="glass-panel" style={{ overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderBottom: '1px solid var(--border-subtle)',
                  }}
                >
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Rule Code
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Target Entity
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Description
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Configured Threshold
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Required Approver Permission
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Status
                  </th>
                  <th style={{ padding: '0.9rem 1.25rem', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr
                    key={rule.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background-color 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: 'var(--primary)' }}>
                      {rule.code}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textTransform: 'capitalize' }}>
                      {rule.entity_type.replace('_', ' ')}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', color: 'var(--text-main)', fontSize: '0.875rem' }}>
                      {rule.description || '—'}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      {rule.threshold_amount ? (
                        <span style={{ fontWeight: 600, color: 'var(--emerald)' }}>
                          ₱{Number(rule.threshold_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                      ) : rule.threshold_pct ? (
                        <span style={{ fontWeight: 600, color: 'var(--cyan)' }}>
                          {(Number(rule.threshold_pct) * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-dim)' }}>Condition Trigger</span>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <code
                        style={{
                          backgroundColor: 'rgba(255, 255, 255, 0.05)',
                          padding: '0.2rem 0.4rem',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          color: 'var(--text-main)',
                        }}
                      >
                        {rule.approver_permission}
                      </code>
                    </td>
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span
                        style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: '9999px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: rule.is_active ? 'var(--emerald-bg)' : 'rgba(255, 255, 255, 0.05)',
                          color: rule.is_active ? 'var(--emerald)' : 'var(--text-dim)',
                          border: rule.is_active ? '1px solid var(--emerald-border)' : '1px solid var(--border-subtle)',
                        }}
                      >
                        {rule.is_active ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                      {canManageRules ? (
                        <button
                          onClick={() => handleOpenEditRule(rule)}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '0.35rem 0.75rem',
                            backgroundColor: 'var(--bg-card)',
                            color: 'var(--text-main)',
                            border: '1px solid var(--border-card)',
                            borderRadius: '6px',
                            fontSize: '0.8rem',
                            fontWeight: 500,
                            cursor: 'pointer',
                          }}
                        >
                          <Edit2 size={13} /> Edit
                        </button>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          Read-Only
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* DECISION MODAL */}
      {selectedRequest && (
        <Modal
          isOpen={true}
          title={`${decisionAction === 'approved' ? 'Approve' : 'Reject'} Request #${selectedRequest.id}`}
          onClose={() => setSelectedRequest(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Request Summary */}
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.02)',
                padding: '1rem',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '0.75rem',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Target Entity: </span>
                <span style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize' }}>
                  {selectedRequest.entity_type.replace('_', ' ')} #{selectedRequest.entity_id}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Rule Triggered: </span>
                <span style={{ fontWeight: 600, color: 'var(--primary)' }}>
                  {selectedRequest.rule_code}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Submitted By: </span>
                <span style={{ color: 'var(--text-main)' }}>{selectedRequest.requester_name}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Submission Date: </span>
                <span style={{ color: 'var(--text-main)' }}>
                  {new Date(selectedRequest.requested_at).toLocaleDateString()}
                </span>
              </div>
            </div>

            {decisionAction === 'rejected' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--rose-bg)',
                  border: '1px solid var(--rose-border)',
                  color: 'var(--rose)',
                  fontSize: '0.825rem',
                }}
              >
                <AlertTriangle size={16} />
                <span>
                  Rejecting this request will automatically return the document to <strong>draft</strong> status for revisions.
                </span>
              </div>
            )}

            {decisionAction === 'approved' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--emerald-bg)',
                  border: '1px solid var(--emerald-border)',
                  color: 'var(--emerald)',
                  fontSize: '0.825rem',
                }}
              >
                <CheckCircle2 size={16} />
                <span>
                  Approving this request will advance the document workflow (confirming order or dispatching PO).
                </span>
              </div>
            )}

            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.4rem',
                }}
              >
                Decision Notes / Justification:
              </label>
              <textarea
                value={decisionComment}
                onChange={(e) => setDecisionComment(e.target.value)}
                placeholder="Enter justification, notes, or rejection reason..."
                rows={3}
                style={{
                  width: '100%',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.6rem 0.8rem',
                  fontSize: '0.85rem',
                  resize: 'vertical',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSelectedRequest(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'transparent',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitDecision}
                disabled={isDeciding}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.5rem 1.25rem',
                  backgroundColor: decisionAction === 'approved' ? 'var(--emerald)' : 'var(--rose)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: isDeciding ? 'not-allowed' : 'pointer',
                }}
              >
                {decisionAction === 'approved' ? <Check size={16} /> : <X size={16} />}
                {isDeciding ? 'Processing...' : `Confirm ${decisionAction === 'approved' ? 'Approval' : 'Rejection'}`}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* EDIT RULE MODAL */}
      {selectedRule && (
        <Modal
          isOpen={true}
          title={`Edit Threshold Rule: ${selectedRule.code}`}
          onClose={() => setSelectedRule(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.35rem',
                }}
              >
                Description
              </label>
              <input
                type="text"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                style={{
                  width: '100%',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.5rem 0.75rem',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '0.85rem',
                    color: 'var(--text-muted)',
                    marginBottom: '0.35rem',
                  }}
                >
                  Threshold Amount (₱)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={editAmount}
                  onChange={(e) => setEditAmount(e.target.value)}
                  placeholder="e.g. 100000.00"
                  style={{
                    width: '100%',
                    backgroundColor: 'var(--bg-input)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '0.85rem',
                    color: 'var(--text-muted)',
                    marginBottom: '0.35rem',
                  }}
                >
                  Threshold Percentage (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={editPct}
                  onChange={(e) => setEditPct(e.target.value)}
                  placeholder="e.g. 15 for 15%"
                  style={{
                    width: '100%',
                    backgroundColor: 'var(--bg-input)',
                    color: 'var(--text-main)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.85rem',
                  }}
                />
              </div>
            </div>

            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.35rem',
                }}
              >
                Required Approver Permission Code
              </label>
              <input
                type="text"
                value={editPerm}
                onChange={(e) => setEditPerm(e.target.value)}
                style={{
                  width: '100%',
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '0.5rem 0.75rem',
                  fontSize: '0.85rem',
                  fontFamily: 'monospace',
                }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
              <input
                type="checkbox"
                id="rule-active"
                checked={editActive}
                onChange={(e) => setEditActive(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <label
                htmlFor="rule-active"
                style={{ fontSize: '0.85rem', color: 'var(--text-main)', cursor: 'pointer' }}
              >
                Rule is Active and Enforced
              </label>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button
                type="button"
                onClick={() => setSelectedRule(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'transparent',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveRule}
                disabled={isSavingRule}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.5rem 1.25rem',
                  backgroundColor: 'var(--primary)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: isSavingRule ? 'not-allowed' : 'pointer',
                }}
              >
                <ArrowRight size={16} />
                {isSavingRule ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
