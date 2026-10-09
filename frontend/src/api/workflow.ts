import { api } from './client'

export interface ApprovalRule {
  id: number
  code: string
  entity_type: string
  description: string | null
  threshold_amount: string | null
  threshold_pct: string | null
  approver_permission: string
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface ApprovalRuleUpdatePayload {
  description?: string | null
  threshold_amount?: string | number | null
  threshold_pct?: string | number | null
  approver_permission?: string | null
  is_active?: boolean
  version: number
}

export type ApprovalRequestStatus = 'pending' | 'approved' | 'rejected'

export interface ApprovalRequest {
  id: number
  rule_id: number
  rule_code: string
  entity_type: string
  entity_id: number
  status: ApprovalRequestStatus
  requested_by: number
  requester_name: string
  requested_at: string
  decided_by: number | null
  decider_name: string | null
  decided_at: string | null
  comment: string | null
}

export interface PaginatedApprovalRequests {
  items: ApprovalRequest[]
  total: number
  page: number
  page_size: number
}

export interface ApprovalDecisionPayload {
  decision: 'approved' | 'rejected'
  comment?: string | null
}

export const workflowApi = {
  // Rules
  listRules: (entityType?: string) => {
    const qs = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : ''
    return api.get<ApprovalRule[]>(`/api/v1/workflow/rules${qs}`)
  },

  updateRule: (ruleId: number, payload: ApprovalRuleUpdatePayload) => {
    return api.patch<ApprovalRule>(`/api/v1/workflow/rules/${ruleId}`, payload)
  },

  // Requests Queue
  listRequests: (params?: {
    status?: ApprovalRequestStatus
    entity_type?: string
    page?: number
    page_size?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.entity_type) query.set('entity_type', params.entity_type)
    if (params?.page) query.set('page', String(params.page))
    if (params?.page_size) query.set('page_size', String(params.page_size))
    const qs = query.toString() ? `?${query.toString()}` : ''
    return api.get<PaginatedApprovalRequests>(`/api/v1/workflow/requests${qs}`)
  },

  getRequest: (requestId: number) => {
    return api.get<ApprovalRequest>(`/api/v1/workflow/requests/${requestId}`)
  },

  decideRequest: (requestId: number, payload: ApprovalDecisionPayload) => {
    return api.post<ApprovalRequest>(`/api/v1/workflow/requests/${requestId}/decide`, payload)
  },
}
