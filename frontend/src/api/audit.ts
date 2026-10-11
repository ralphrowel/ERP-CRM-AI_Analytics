import { api } from './client';

export interface AuditLogItem {
  id: number;
  occurred_at: string;
  actor_user_id: number | null;
  actor_name?: string | null;
  actor_email?: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  entity_label?: string | null;
  changes: Record<string, [any, any]>;
  context?: Record<string, any> | null;
  ip_address?: string | null;
  request_id?: string | null;
}

export interface PaginatedAuditLogs {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ActivityFeedItem {
  id: string;
  source: 'audit_log' | 'status_history' | 'activity';
  timestamp: string;
  actor_id: number | null;
  actor_name?: string | null;
  actor_email?: string | null;
  title: string;
  summary: string;
  details?: Record<string, any> | null;
  changes?: Record<string, [any, any]> | null;
  badge_color?: string;
}

export interface PaginatedActivityFeed {
  items: ActivityFeedItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogFilterParams {
  entity_type?: string;
  entity_id?: number;
  actor_user_id?: number;
  action?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const auditApi = {
  listLogs: async (params?: AuditLogFilterParams): Promise<PaginatedAuditLogs> => {
    const searchParams = new URLSearchParams();
    if (params) {
      if (params.entity_type) searchParams.append('entity_type', params.entity_type);
      if (params.entity_id !== undefined) searchParams.append('entity_id', String(params.entity_id));
      if (params.actor_user_id !== undefined) searchParams.append('actor_user_id', String(params.actor_user_id));
      if (params.action) searchParams.append('action', params.action);
      if (params.date_from) searchParams.append('date_from', params.date_from);
      if (params.date_to) searchParams.append('date_to', params.date_to);
      if (params.page !== undefined) searchParams.append('page', String(params.page));
      if (params.page_size !== undefined) searchParams.append('page_size', String(params.page_size));
    }
    const query = searchParams.toString();
    const url = `/api/v1/audit/logs${query ? `?${query}` : ''}`;
    return api.get<PaginatedAuditLogs>(url);
  },

  getEntityFeed: async (
    entityType: string,
    entityId: number,
    limit: number = 50,
    offset: number = 0
  ): Promise<PaginatedActivityFeed> => {
    return api.get<PaginatedActivityFeed>(
      `/api/v1/audit/feed/${encodeURIComponent(entityType)}/${entityId}?limit=${limit}&offset=${offset}`
    );
  },
};
