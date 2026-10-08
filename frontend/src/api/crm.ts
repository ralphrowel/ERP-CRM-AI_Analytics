import { api } from './client'
import type { Customer } from './customers'

export type LeadSource = 'website' | 'referral' | 'event' | 'cold_call' | 'social' | 'import' | 'other'
export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'disqualified' | 'converted'
export type OpportunityStage = 'discovery' | 'proposal' | 'negotiation' | 'won' | 'lost'
export type LostReason = 'price' | 'competitor' | 'no_budget' | 'no_decision' | 'timing' | 'other'
export type ActivityType = 'call' | 'email' | 'meeting' | 'task' | 'note'

export interface Lead {
  id: number
  lead_no: string
  first_name: string
  last_name?: string | null
  company_name?: string | null
  job_title?: string | null
  email?: string | null
  phone?: string | null
  source: LeadSource
  status: LeadStatus
  disqualified_reason?: string | null
  owner_user_id?: number | null
  converted_at?: string | null
  converted_customer_id?: number | null
  converted_contact_id?: number | null
  converted_opportunity_id?: number | null
  notes?: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface PaginatedLeads {
  items: Lead[]
  total: number
  page: number
  page_size: number
}

export interface LeadCreatePayload {
  first_name: string
  last_name?: string
  company_name?: string
  job_title?: string
  email?: string
  phone?: string
  source?: LeadSource
  notes?: string
}

export interface LeadConvertPayload {
  link_existing_customer_id?: number | null
  new_customer_name?: string | null
  create_opportunity?: boolean
  opportunity_name?: string | null
  opportunity_estimated_amount?: string
  expected_close_date?: string | null
}

export interface Opportunity {
  id: number
  opportunity_no: string
  name: string
  customer_id: number
  primary_contact_id?: number | null
  stage: OpportunityStage
  estimated_amount: string
  probability: string
  expected_close_date?: string | null
  closed_at?: string | null
  lost_reason?: string | null
  source_lead_id?: number | null
  owner_user_id?: number | null
  version: number
  created_at: string
  updated_at: string
}

export interface PaginatedOpportunities {
  items: Opportunity[]
  total: number
  page: number
  page_size: number
}

export interface PipelineStageItem {
  stage: OpportunityStage
  count: number
  total_amount: string
  weighted_amount: string
  opportunities: Opportunity[]
}

export interface PipelineResponse {
  stages: PipelineStageItem[]
  total_pipeline_value: string
  total_weighted_value: string
}

export interface Activity {
  id: number
  activity_type: ActivityType
  subject: string
  body?: string | null
  due_at?: string | null
  completed_at?: string | null
  owner_user_id?: number | null
  lead_id?: number | null
  customer_id?: number | null
  contact_id?: number | null
  opportunity_id?: number | null
  created_at: string
  updated_at: string
}

export interface StatusHistoryItem {
  id: number
  entity_type: string
  entity_id: number
  from_status?: string | null
  to_status: string
  reason?: string | null
  changed_by?: number | null
  changed_at: string
}

export const crmApi = {
  // Leads
  listLeads: (params: { page?: number; page_size?: number; status?: string; source?: string; search?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.page) query.set('page', params.page.toString())
    if (params.page_size) query.set('page_size', params.page_size.toString())
    if (params.status) query.set('status', params.status)
    if (params.source) query.set('source', params.source)
    if (params.search) query.set('search', params.search)
    return api.get<PaginatedLeads>(`/api/v1/leads?${query.toString()}`)
  },
  getLead: (id: number) => api.get<Lead>(`/api/v1/leads/${id}`),
  createLead: (data: LeadCreatePayload) => api.post<Lead>('/api/v1/leads', data),
  transitionLead: (id: number, to_status: LeadStatus, reason?: string) =>
    api.post<Lead>(`/api/v1/leads/${id}/transition`, { to_status, reason }),
  checkLeadDuplicates: (id: number) => api.get<Customer[]>(`/api/v1/leads/${id}/duplicates`),
  convertLead: (id: number, data: LeadConvertPayload) => api.post<Lead>(`/api/v1/leads/${id}/convert`, data),

  // Opportunities
  listOpportunities: (params: { page?: number; page_size?: number; stage?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.page) query.set('page', params.page.toString())
    if (params.page_size) query.set('page_size', params.page_size.toString())
    if (params.stage) query.set('stage', params.stage)
    return api.get<PaginatedOpportunities>(`/api/v1/opportunities?${query.toString()}`)
  },
  getPipeline: () => api.get<PipelineResponse>('/api/v1/opportunities/pipeline'),
  transitionOpportunity: (id: number, to_stage: OpportunityStage, lost_reason?: LostReason, reason?: string) =>
    api.post<Opportunity>(`/api/v1/opportunities/${id}/transition`, { to_stage, lost_reason, reason }),

  // Activities
  listActivities: (params: { lead_id?: number; customer_id?: number; opportunity_id?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.lead_id) query.set('lead_id', params.lead_id.toString())
    if (params.customer_id) query.set('customer_id', params.customer_id.toString())
    if (params.opportunity_id) query.set('opportunity_id', params.opportunity_id.toString())
    return api.get<Activity[]>(`/api/v1/activities?${query.toString()}`)
  },
  createActivity: (data: {
    activity_type: ActivityType
    subject: string
    body?: string
    due_at?: string
    lead_id?: number
    customer_id?: number
    opportunity_id?: number
  }) => api.post<Activity>('/api/v1/activities', data),

  // History
  getStatusHistory: (entityType: string, entityId: number) =>
    api.get<StatusHistoryItem[]>(`/api/v1/history/${entityType}/${entityId}`),
}
