import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle,
  Filter,
  History,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  UserX,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  crmApi,
  type Lead,
  type LeadCreatePayload,
  type LeadSource,
  type LeadStatus,
} from '../api/crm'
import type { Customer } from '../api/customers'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

export const LeadsPage: React.FC = () => {
  const [leads, setLeads] = useState<Lead[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [sourceFilter, setSourceFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Errors & Alerts
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals & Drawers
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isDisqualifyOpen, setIsDisqualifyOpen] = useState(false)
  const [isConvertOpen, setIsConvertOpen] = useState(false)
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null)

  // Disqualify Form State
  const [disqualifyReason, setDisqualifyReason] = useState('')

  // Convert Wizard State
  const [duplicateCustomers, setDuplicateCustomers] = useState<Customer[]>([])
  const [isCheckingDuplicates, setIsCheckingDuplicates] = useState(false)
  const [convertChoice, setConvertChoice] = useState<'new' | 'link'>('new')
  const [selectedExistingCustomerId, setSelectedExistingCustomerId] = useState<number | null>(null)
  const [newCustomerName, setNewCustomerName] = useState('')
  const [createOpportunity, setCreateOpportunity] = useState(true)
  const [opportunityName, setOpportunityName] = useState('')
  const [opportunityAmount, setOpportunityAmount] = useState('50000.00')
  const [expectedCloseDate, setExpectedCloseDate] = useState('')

  // Create Form State
  const [formData, setFormData] = useState<LeadCreatePayload>({
    first_name: '',
    last_name: '',
    company_name: '',
    job_title: '',
    email: '',
    phone: '',
    source: 'website',
    notes: '',
  })

  const loadLeads = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const res = await crmApi.listLeads({
        page,
        page_size: pageSize,
        search: searchTerm || undefined,
        status: statusFilter || undefined,
        source: sourceFilter || undefined,
      })
      setLeads(res.items)
      setTotal(res.total)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load leads'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadLeads()
  }, [page, statusFilter, sourceFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadLeads()
  }

  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault()
    setGeneralError(null)
    try {
      await crmApi.createLead(formData)
      setIsCreateOpen(false)
      setFormData({
        first_name: '',
        last_name: '',
        company_name: '',
        job_title: '',
        email: '',
        phone: '',
        source: 'website',
        notes: '',
      })
      setSuccessMessage('Lead created successfully')
      setTimeout(() => setSuccessMessage(null), 4000)
      loadLeads()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create lead'))
      }
    }
  }

  const handleTransition = async (leadId: number, targetStatus: LeadStatus, reason?: string) => {
    setGeneralError(null)
    try {
      await crmApi.transitionLead(leadId, targetStatus, reason)
      setSuccessMessage(`Lead moved to ${targetStatus}`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadLeads()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('This lead was modified by another transaction. Please refresh.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to transition lead'))
      }
    }
  }

  const openDisqualifyModal = (lead: Lead) => {
    setSelectedLead(lead)
    setDisqualifyReason('')
    setIsDisqualifyOpen(true)
  }

  const confirmDisqualify = async () => {
    if (!selectedLead) return
    await handleTransition(selectedLead.id, 'disqualified', disqualifyReason)
    setIsDisqualifyOpen(false)
    setSelectedLead(null)
  }

  const openConvertWizard = async (lead: Lead) => {
    setSelectedLead(lead)
    setIsConvertOpen(true)
    setIsCheckingDuplicates(true)
    setConvertChoice('new')
    setSelectedExistingCustomerId(null)
    setNewCustomerName(lead.company_name || `${lead.first_name} ${lead.last_name || ''}`.trim())
    setCreateOpportunity(true)
    setOpportunityName(`${lead.company_name || lead.first_name} Deal`)
    setOpportunityAmount('50000.00')

    const d = new Date()
    d.setDate(d.getDate() + 30)
    setExpectedCloseDate(d.toISOString().split('T')[0])

    try {
      const dupes = await crmApi.checkLeadDuplicates(lead.id)
      setDuplicateCustomers(dupes)
      if (dupes.length > 0) {
        setConvertChoice('link')
        setSelectedExistingCustomerId(dupes[0].id)
      }
    } catch {
      setDuplicateCustomers([])
    } finally {
      setIsCheckingDuplicates(false)
    }
  }

  const handleConvertSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedLead) return
    setGeneralError(null)

    try {
      await crmApi.convertLead(selectedLead.id, {
        link_existing_customer_id: convertChoice === 'link' ? selectedExistingCustomerId : null,
        new_customer_name: convertChoice === 'new' ? newCustomerName : null,
        create_opportunity: createOpportunity,
        opportunity_name: createOpportunity ? opportunityName : undefined,
        opportunity_estimated_amount: createOpportunity ? opportunityAmount : undefined,
        expected_close_date: createOpportunity && expectedCloseDate ? expectedCloseDate : undefined,
      })

      setIsConvertOpen(false)
      setSelectedLead(null)
      setSuccessMessage('Lead converted successfully! Prospect Customer, Contact, and Opportunity created.')
      setTimeout(() => setSuccessMessage(null), 6000)
      loadLeads()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError('Conversion conflict: data changed concurrently.')
        } else {
          setGeneralError(err)
        }
      } else {
        setGeneralError(new Error('Failed to convert lead'))
      }
    }
  }

  const getStatusBadge = (status: LeadStatus) => {
    switch (status) {
      case 'new':
        return <span className="badge badge-cyan">New</span>
      case 'contacted':
        return <span className="badge badge-amber">Contacted</span>
      case 'qualified':
        return <span className="badge badge-indigo">Qualified</span>
      case 'converted':
        return <span className="badge badge-emerald">Converted</span>
      case 'disqualified':
        return <span className="badge badge-rose">Disqualified</span>
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f8fafc' }}>
            CRM Lead Management
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Track top-of-funnel prospects, qualification workflows, and atomic conversion into Customer accounts.
          </p>
        </div>

        <button
          id="btn-create-lead"
          className="btn btn-primary"
          onClick={() => setIsCreateOpen(true)}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <Plus size={16} /> New Inbound Lead
        </button>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="badge badge-emerald" style={{ padding: '0.75rem 1rem', fontSize: '0.875rem' }}>
          <CheckCircle size={16} /> {successMessage}
        </div>
      )}

      {conflictError && (
        <ConflictAlert message={conflictError} onReload={() => loadLeads()} />
      )}

      {generalError && (
        <ProblemAlert
          error={generalError}
          onDismiss={() => setGeneralError(null)}
        />
      )}

      {/* Filter / Search Bar */}
      <div
        className="card"
        style={{
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: 'var(--bg-surface)',
        }}
      >
        <form
          onSubmit={handleSearchSubmit}
          style={{ display: 'flex', gap: '0.5rem', flex: 1, minWidth: '260px' }}
        >
          <div style={{ position: 'relative', flex: 1 }}>
            <Search
              size={16}
              style={{
                position: 'absolute',
                left: '0.75rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-dim)',
              }}
            />
            <input
              id="input-lead-search"
              type="text"
              className="input-field"
              placeholder="Search leads by name, email, company, or lead #..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ paddingLeft: '2.25rem', width: '100%' }}
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Search
          </button>
        </form>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Filter size={14} color="var(--text-dim)" />
            <select
              id="select-lead-status"
              className="input-field"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
              style={{ minWidth: '130px' }}
            >
              <option value="">All Statuses</option>
              <option value="new">New</option>
              <option value="contacted">Contacted</option>
              <option value="qualified">Qualified</option>
              <option value="converted">Converted</option>
              <option value="disqualified">Disqualified</option>
            </select>
          </div>

          <select
            id="select-lead-source"
            className="input-field"
            value={sourceFilter}
            onChange={(e) => {
              setSourceFilter(e.target.value)
              setPage(1)
            }}
            style={{ minWidth: '130px' }}
          >
            <option value="">All Sources</option>
            <option value="website">Website</option>
            <option value="referral">Referral</option>
            <option value="event">Event</option>
            <option value="cold_call">Cold Call</option>
            <option value="social">Social</option>
            <option value="import">Import</option>
            <option value="other">Other</option>
          </select>

          <button
            onClick={() => loadLeads()}
            className="btn btn-secondary"
            title="Refresh"
            style={{ padding: '0.5rem' }}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Leads Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Lead #
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Contact / Company
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Source
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Status
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Created
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', textAlign: 'right' }}>
                Lifecycle Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  <RefreshCw className="animate-spin" size={20} style={{ margin: '0 auto 0.5rem' }} />
                  <div>Loading leads directory...</div>
                </td>
              </tr>
            ) : leads.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  No leads found matching current filters.
                </td>
              </tr>
            ) : (
              leads.map((lead) => {
                const fullName = `${lead.first_name} ${lead.last_name || ''}`.trim()
                return (
                  <tr
                    key={lead.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background-color 0.1s',
                    }}
                  >
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontSize: '0.85rem', color: '#a5b4fc' }}>
                      {lead.lead_no}
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: '#f8fafc' }}>{fullName}</div>
                      <div style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                        {lead.company_name ? lead.company_name : <em>No Company</em>}
                        {lead.job_title && ` · ${lead.job_title}`}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', gap: '0.75rem', marginTop: '0.2rem' }}>
                        {lead.email && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                            <Mail size={11} /> {lead.email}
                          </span>
                        )}
                        {lead.phone && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                            <Phone size={11} /> {lead.phone}
                          </span>
                        )}
                      </div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span className="badge badge-subtle" style={{ textTransform: 'capitalize' }}>
                        {lead.source.replace('_', ' ')}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      {getStatusBadge(lead.status)}
                      {lead.disqualified_reason && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--rose-400)', marginTop: '0.2rem' }}>
                          Reason: {lead.disqualified_reason}
                        </div>
                      )}
                    </td>

                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                      {new Date(lead.created_at).toLocaleDateString()}
                    </td>

                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.4rem' }}>
                        {/* Audit Trail Button */}
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                          title="View Audit Trail"
                          onClick={() => {
                            setSelectedLead(lead)
                            setIsHistoryOpen(true)
                          }}
                        >
                          <History size={13} />
                        </button>

                        {/* Transition Buttons based on state machine */}
                        {lead.status === 'new' && (
                          <>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem' }}
                              onClick={() => handleTransition(lead.id, 'contacted')}
                            >
                              Contact
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => openDisqualifyModal(lead)}
                              title="Disqualify"
                            >
                              <UserX size={13} />
                            </button>
                          </>
                        )}

                        {lead.status === 'contacted' && (
                          <>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', borderColor: '#6366f1', color: '#a5b4fc' }}
                              onClick={() => handleTransition(lead.id, 'qualified')}
                            >
                              Qualify
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => openDisqualifyModal(lead)}
                              title="Disqualify"
                            >
                              <UserX size={13} />
                            </button>
                          </>
                        )}

                        {lead.status === 'qualified' && (
                          <>
                            <button
                              id={`btn-convert-${lead.id}`}
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                              onClick={() => openConvertWizard(lead)}
                            >
                              <Sparkles size={13} /> Convert Lead
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => openDisqualifyModal(lead)}
                              title="Disqualify"
                            >
                              <UserX size={13} />
                            </button>
                          </>
                        )}

                        {lead.status === 'converted' && (
                          <span style={{ fontSize: '0.75rem', color: 'var(--emerald-400)', display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                            <CheckCircle size={13} /> Converted
                          </span>
                        )}

                        {lead.status === 'disqualified' && (
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                            Closed
                          </span>
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
            Showing {leads.length > 0 ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, total)} of {total} leads
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

      {/* Modal: Create Lead */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Inbound Lead">
        <form onSubmit={handleCreateLead} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="form-label">First Name *</label>
              <input
                type="text"
                required
                className="input-field"
                placeholder="e.g. Maria"
                value={formData.first_name}
                onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
              />
            </div>
            <div>
              <label className="form-label">Last Name</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Santos"
                value={formData.last_name || ''}
                onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="form-label">Company Name</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Acme Logistics Corp"
                value={formData.company_name || ''}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
              />
            </div>
            <div>
              <label className="form-label">Job Title</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Procurement Lead"
                value={formData.job_title || ''}
                onChange={(e) => setFormData({ ...formData, job_title: e.target.value })}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="form-label">Email Address</label>
              <input
                type="email"
                className="input-field"
                placeholder="e.g. maria@acme.ph"
                value={formData.email || ''}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            <div>
              <label className="form-label">Phone Number</label>
              <input
                type="tel"
                className="input-field"
                placeholder="e.g. +63 917 123 4567"
                value={formData.phone || ''}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="form-label">Lead Acquisition Source</label>
            <select
              className="input-field"
              value={formData.source}
              onChange={(e) => setFormData({ ...formData, source: e.target.value as LeadSource })}
            >
              <option value="website">Website</option>
              <option value="referral">Referral</option>
              <option value="event">Industry Event / Expo</option>
              <option value="cold_call">Cold Outreach</option>
              <option value="social">Social Media / LinkedIn</option>
              <option value="import">Bulk Import</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <label className="form-label">Internal Qualification Notes</label>
            <textarea
              className="input-field"
              rows={3}
              placeholder="Initial requirements, timeline, budget notes..."
              value={formData.notes || ''}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Register Lead
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Disqualify Lead */}
      <Modal isOpen={isDisqualifyOpen} onClose={() => setIsDisqualifyOpen(false)} title="Disqualify Lead">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Marking lead <strong>{selectedLead?.first_name} {selectedLead?.last_name}</strong> as disqualified. Please provide an audit reason:
          </p>
          <div>
            <label className="form-label">Disqualification Reason *</label>
            <textarea
              required
              rows={3}
              className="input-field"
              placeholder="e.g. Budget out of range, competitor preferred, unresponsive after 5 attempts..."
              value={disqualifyReason}
              onChange={(e) => setDisqualifyReason(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setIsDisqualifyOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              style={{ backgroundColor: 'var(--rose-500)', borderColor: 'var(--rose-500)' }}
              disabled={!disqualifyReason.trim()}
              onClick={confirmDisqualify}
            >
              Confirm Disqualification
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal: Lead Convert Wizard */}
      <Modal isOpen={isConvertOpen} onClose={() => setIsConvertOpen(false)} title="Lead Conversion Wizard">
        <form onSubmit={handleConvertSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ padding: '0.75rem', borderRadius: '8px', backgroundColor: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#a5b4fc', marginBottom: '0.25rem' }}>
              Converting Lead: {selectedLead?.lead_no} ({selectedLead?.first_name} {selectedLead?.last_name})
            </div>
            <div style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
              Atomic conversion guarantees creation of a Contact record, Customer account linking, and Deal creation in a single transaction.
            </div>
          </div>

          {/* Duplicate Detection Alert */}
          {isCheckingDuplicates ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
              <RefreshCw className="animate-spin" size={14} /> Scanning existing accounts for duplicate matches...
            </div>
          ) : duplicateCustomers.length > 0 ? (
            <div
              style={{
                padding: '0.85rem',
                borderRadius: '8px',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f59e0b', fontWeight: 600, fontSize: '0.85rem' }}>
                <AlertTriangle size={16} /> Potential Duplicate Accounts Found ({duplicateCustomers.length})
              </div>
              <div style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                We found existing customers that match this lead’s name or email:
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8rem', color: '#f8fafc' }}>
                {duplicateCustomers.map((c) => (
                  <li key={c.id}>
                    <strong>{c.name}</strong> ({c.customer_no}) · Status: {c.status}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Customer Destination Choice */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label className="form-label">Customer Account Assignment</label>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="convertChoice"
                  value="new"
                  checked={convertChoice === 'new'}
                  onChange={() => setConvertChoice('new')}
                />
                Create New Prospect Customer
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="convertChoice"
                  value="link"
                  checked={convertChoice === 'link'}
                  onChange={() => setConvertChoice('link')}
                />
                Link to Existing Customer Account
              </label>
            </div>
          </div>

          {convertChoice === 'new' ? (
            <div>
              <label className="form-label">New Customer Account Name *</label>
              <input
                type="text"
                required
                className="input-field"
                value={newCustomerName}
                onChange={(e) => setNewCustomerName(e.target.value)}
                placeholder="Company Name or Individual Full Name"
              />
              <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)', marginTop: '0.25rem', display: 'block' }}>
                Account will be created in <strong>prospect</strong> status until first won deal.
              </span>
            </div>
          ) : (
            <div>
              <label className="form-label">Select Existing Customer Account *</label>
              <select
                required
                className="input-field"
                value={selectedExistingCustomerId || ''}
                onChange={(e) => setSelectedExistingCustomerId(Number(e.target.value))}
              >
                <option value="">-- Choose Account --</option>
                {duplicateCustomers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.customer_no}) - {c.status}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Opportunity Section */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', fontWeight: 600, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={createOpportunity}
                onChange={(e) => setCreateOpportunity(e.target.checked)}
              />
              Spawn Pipeline Opportunity (Deal)
            </label>

            {createOpportunity && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', paddingLeft: '1.25rem' }}>
                <div>
                  <label className="form-label">Deal / Opportunity Name *</label>
                  <input
                    type="text"
                    required
                    className="input-field"
                    value={opportunityName}
                    onChange={(e) => setOpportunityName(e.target.value)}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <label className="form-label">Estimated Amount (PHP ₱) *</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      className="input-field"
                      value={opportunityAmount}
                      onChange={(e) => setOpportunityAmount(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="form-label">Expected Close Date</label>
                    <input
                      type="date"
                      className="input-field"
                      value={expectedCloseDate}
                      onChange={(e) => setExpectedCloseDate(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsConvertOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sparkles size={16} /> Execute Atomic Conversion
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Status Audit Trail */}
      <Modal
        isOpen={isHistoryOpen}
        onClose={() => {
          setIsHistoryOpen(false)
          setSelectedLead(null)
        }}
        title={`Status History Audit Trail: ${selectedLead?.lead_no}`}
      >
        {selectedLead && (
          <StatusHistoryTimeline entityType="lead" entityId={selectedLead.id} />
        )}
      </Modal>
    </div>
  )
}
