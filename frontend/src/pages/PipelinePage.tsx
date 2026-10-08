import React, { useEffect, useState } from 'react'
import {
  Award,
  Calendar,
  CheckCircle2,
  ChevronRight,
  DollarSign,
  History,
  RefreshCw,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  crmApi,
  type LostReason,
  type Opportunity,
  type OpportunityStage,
  type PipelineResponse,
} from '../api/crm'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

const STAGES: Array<{ id: OpportunityStage; label: string; color: string; defaultProb: number }> = [
  { id: 'discovery', label: 'Discovery', color: '#38bdf8', defaultProb: 10 },
  { id: 'proposal', label: 'Proposal', color: '#818cf8', defaultProb: 30 },
  { id: 'negotiation', label: 'Negotiation', color: '#fbbf24', defaultProb: 70 },
  { id: 'won', label: 'Won', color: '#34d399', defaultProb: 100 },
  { id: 'lost', label: 'Lost', color: '#f43f5e', defaultProb: 0 },
]

export const PipelinePage: React.FC = () => {
  const [pipeline, setPipeline] = useState<PipelineResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isLostModalOpen, setIsLostModalOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [activeOpportunity, setActiveOpportunity] = useState<Opportunity | null>(null)

  // Lost Form State
  const [lostReason, setLostReason] = useState<LostReason>('price')
  const [lostNotes, setLostNotes] = useState('')

  const loadPipeline = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const data = await crmApi.getPipeline()
      setPipeline(data)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load sales pipeline'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadPipeline()
  }, [])

  const handleTransition = async (
    opp: Opportunity,
    toStage: OpportunityStage,
    lost_reason?: LostReason,
    notes?: string,
  ) => {
    setGeneralError(null)
    try {
      await crmApi.transitionOpportunity(opp.id, toStage, lost_reason, notes)
      setSuccessMessage(`Opportunity ${opp.opportunity_no} moved to ${toStage}`)
      setTimeout(() => setSuccessMessage(null), 3500)
      loadPipeline()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Conflict: This opportunity was updated concurrently by another user.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to update deal stage'))
      }
    }
  }

  const promptLost = (opp: Opportunity) => {
    setActiveOpportunity(opp)
    setLostReason('price')
    setLostNotes('')
    setIsLostModalOpen(true)
  }

  const confirmLost = async () => {
    if (!activeOpportunity) return
    await handleTransition(activeOpportunity, 'lost', lostReason, lostNotes)
    setIsLostModalOpen(false)
    setActiveOpportunity(null)
  }

  const getNextStage = (stage: OpportunityStage): OpportunityStage | null => {
    if (stage === 'discovery') return 'proposal'
    if (stage === 'proposal') return 'negotiation'
    if (stage === 'negotiation') return 'won'
    return null
  }

  const formatCurrency = (val: string | number) => {
    const num = Number(val || 0)
    return new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(num)
  }

  // Calculate active deals count
  const activeCount =
    pipeline?.stages
      .filter((s) => s.stage !== 'won' && s.stage !== 'lost')
      .reduce((sum, s) => sum + s.count, 0) || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Title & Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f8fafc' }}>
            CRM Sales Pipeline & Deals
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Interactive stage progression, probabilistic forecasting, and automated customer status promotion.
          </p>
        </div>

        <button
          onClick={() => loadPipeline()}
          className="btn btn-secondary"
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <RefreshCw size={14} /> Refresh Pipeline
        </button>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="badge badge-emerald" style={{ padding: '0.75rem 1rem', fontSize: '0.875rem' }}>
          <CheckCircle2 size={16} /> {successMessage}
        </div>
      )}

      {conflictError && (
        <ConflictAlert message={conflictError} onReload={() => loadPipeline()} />
      )}

      {generalError && (
        <ProblemAlert
          error={generalError}
          onDismiss={() => setGeneralError(null)}
        />
      )}

      {/* KPI Metrics Banner */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div className="card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              backgroundColor: 'rgba(99, 102, 241, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#818cf8',
            }}
          >
            <DollarSign size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
              Total Pipeline Value
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.2rem' }}>
              {formatCurrency(pipeline?.total_pipeline_value || '0')}
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8',
            }}
          >
            <TrendingUp size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
              Weighted Forecast
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#38bdf8', marginTop: '0.2rem' }}>
              {formatCurrency(pipeline?.total_weighted_value || '0')}
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              backgroundColor: 'rgba(52, 211, 153, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#34d399',
            }}
          >
            <Award size={22} />
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
              Active In-Flight Deals
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.2rem' }}>
              {activeCount} Active Deals
            </div>
          </div>
        </div>
      </div>

      {/* Kanban Board Layout */}
      {isLoading ? (
        <div className="card" style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-dim)' }}>
          <RefreshCw className="animate-spin" size={24} style={{ margin: '0 auto 0.75rem' }} />
          <div>Loading sales pipeline board...</div>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, minmax(260px, 1fr))',
            gap: '1rem',
            overflowX: 'auto',
            paddingBottom: '1rem',
            alignItems: 'start',
          }}
        >
          {STAGES.map((colDef) => {
            const stageData = pipeline?.stages.find((s) => s.stage === colDef.id)
            const opps = stageData?.opportunities || []
            const totalStageAmt = stageData?.total_amount || '0'
            const weightedStageAmt = stageData?.weighted_amount || '0'

            return (
              <div
                key={colDef.id}
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  borderRadius: '12px',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  maxHeight: 'calc(100vh - 280px)',
                }}
              >
                {/* Column Header */}
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    borderBottom: '1px solid var(--border-subtle)',
                    borderTop: `3px solid ${colDef.color}`,
                    borderTopLeftRadius: '12px',
                    borderTopRightRadius: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#f8fafc' }}>
                      {colDef.label}
                    </div>
                    <span
                      style={{
                        padding: '0.15rem 0.5rem',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        backgroundColor: 'rgba(255, 255, 255, 0.08)',
                        color: colDef.color,
                      }}
                    >
                      {opps.length}
                    </span>
                  </div>

                  <div style={{ marginTop: '0.35rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                    <span>{formatCurrency(totalStageAmt)}</span>
                    {colDef.id !== 'won' && colDef.id !== 'lost' && (
                      <span title="Weighted value">W: {formatCurrency(weightedStageAmt)}</span>
                    )}
                  </div>
                </div>

                {/* Column Cards List */}
                <div
                  style={{
                    padding: '0.75rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.75rem',
                    overflowY: 'auto',
                    flex: 1,
                  }}
                >
                  {opps.length === 0 ? (
                    <div
                      style={{
                        textAlign: 'center',
                        padding: '2rem 1rem',
                        color: 'var(--text-dim)',
                        fontSize: '0.8rem',
                        fontStyle: 'italic',
                      }}
                    >
                      No deals in {colDef.label}
                    </div>
                  ) : (
                    opps.map((opp) => {
                      const nextStage = getNextStage(opp.stage)
                      return (
                        <div
                          key={opp.id}
                          className="card"
                          style={{
                            padding: '0.85rem',
                            backgroundColor: 'rgba(255, 255, 255, 0.02)',
                            borderColor: 'var(--border-subtle)',
                            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                            <span style={{ fontSize: '0.725rem', fontFamily: 'monospace', color: 'var(--text-dim)' }}>
                              {opp.opportunity_no}
                            </span>
                            <span
                              style={{
                                fontSize: '0.7rem',
                                padding: '0.1rem 0.4rem',
                                borderRadius: '4px',
                                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                                color: '#a5b4fc',
                              }}
                            >
                              {opp.probability}%
                            </span>
                          </div>

                          <div style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f8fafc', marginBottom: '0.35rem' }}>
                            {opp.name}
                          </div>

                          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#38bdf8', marginBottom: '0.5rem' }}>
                            {formatCurrency(opp.estimated_amount)}
                          </div>

                          {opp.expected_close_date && (
                            <div style={{ fontSize: '0.725rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.25rem', marginBottom: '0.65rem' }}>
                              <Calendar size={12} /> Target: {opp.expected_close_date}
                            </div>
                          )}

                          {opp.lost_reason && (
                            <div style={{ fontSize: '0.725rem', color: 'var(--rose-400)', backgroundColor: 'rgba(244, 63, 94, 0.1)', padding: '0.25rem 0.4rem', borderRadius: '4px', marginBottom: '0.5rem' }}>
                              Lost: {opp.lost_reason.replace('_', ' ')}
                            </div>
                          )}

                          {/* Action footer */}
                          <div
                            style={{
                              borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                              paddingTop: '0.5rem',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.25rem 0.4rem', fontSize: '0.7rem' }}
                              title="Audit Trail"
                              onClick={() => {
                                setActiveOpportunity(opp)
                                setIsHistoryOpen(true)
                              }}
                            >
                              <History size={12} />
                            </button>

                            <div style={{ display: 'flex', gap: '0.3rem' }}>
                              {opp.stage !== 'won' && opp.stage !== 'lost' && (
                                <>
                                  <button
                                    className="btn btn-secondary"
                                    style={{ padding: '0.25rem 0.4rem', fontSize: '0.7rem', color: 'var(--rose-400)' }}
                                    title="Mark Lost"
                                    onClick={() => promptLost(opp)}
                                  >
                                    <XCircle size={12} />
                                  </button>

                                  {opp.stage === 'negotiation' && (
                                    <button
                                      className="btn btn-primary"
                                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem', backgroundColor: 'var(--emerald-600)', borderColor: 'var(--emerald-600)' }}
                                      onClick={() => handleTransition(opp, 'won')}
                                      title="Mark Won & Promote Customer"
                                    >
                                      Win Deal
                                    </button>
                                  )}

                                  {nextStage && nextStage !== 'won' && (
                                    <button
                                      className="btn btn-secondary"
                                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                                      onClick={() => handleTransition(opp, nextStage)}
                                    >
                                      Advance <ChevronRight size={11} />
                                    </button>
                                  )}
                                </>
                              )}

                              {opp.stage === 'won' && (
                                <span style={{ fontSize: '0.7rem', color: 'var(--emerald-400)', display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                                  <Award size={12} /> Closed Won
                                </span>
                              )}

                              {opp.stage === 'lost' && (
                                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                                  Closed Lost
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal: Mark Opportunity Lost */}
      <Modal isOpen={isLostModalOpen} onClose={() => setIsLostModalOpen(false)} title="Mark Opportunity as Lost">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ padding: '0.75rem', borderRadius: '8px', backgroundColor: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.2)' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--rose-400)' }}>
              Closing Deal: {activeOpportunity?.name} ({activeOpportunity?.opportunity_no})
            </div>
            <div style={{ fontSize: '0.775rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Roadmap Rule 4 mandates capturing the precise loss reason for CRM pipeline analytics.
            </div>
          </div>

          <div>
            <label className="form-label">Loss Category *</label>
            <select
              required
              className="input-field"
              value={lostReason}
              onChange={(e) => setLostReason(e.target.value as LostReason)}
            >
              <option value="price">Price / Too Expensive</option>
              <option value="competitor">Lost to Competitor</option>
              <option value="no_budget">No Budget / Budget Cut</option>
              <option value="no_decision">Client Made No Decision / Inaction</option>
              <option value="timing">Bad Timing / Postponed to Next Year</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <label className="form-label">Detailed Notes</label>
            <textarea
              rows={3}
              className="input-field"
              placeholder="Competitor pricing details, client feedback..."
              value={lostNotes}
              onChange={(e) => setLostNotes(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setIsLostModalOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              style={{ backgroundColor: 'var(--rose-500)', borderColor: 'var(--rose-500)' }}
              onClick={confirmLost}
            >
              Confirm Loss
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal: Status Audit Trail */}
      <Modal
        isOpen={isHistoryOpen}
        onClose={() => {
          setIsHistoryOpen(false)
          setActiveOpportunity(null)
        }}
        title={`Status History Audit Trail: ${activeOpportunity?.opportunity_no}`}
      >
        {activeOpportunity && (
          <StatusHistoryTimeline entityType="opportunity" entityId={activeOpportunity.id} />
        )}
      </Modal>
    </div>
  )
}
