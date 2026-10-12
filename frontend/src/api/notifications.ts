import { apiRequest } from './client'

export interface InAppNotification {
  id: number
  user_id: number
  title: string
  message: string
  link?: string | null
  category: string
  is_read: boolean
  read_at?: string | null
  dedup_key?: string | null
  created_at: string
}

export interface NotificationListResponse {
  items: InAppNotification[]
  total: number
  page: number
  page_size: number
  unread_count: number
}

export interface UnreadCountResponse {
  unread_count: number
}

export interface DeadLetterEvent {
  id: number
  event_type: string
  aggregate_type: string
  aggregate_id: number
  payload: Record<string, unknown>
  attempts: number
  last_error: string | null
  created_at: string
}

export interface DeadLetterListResponse {
  items: DeadLetterEvent[]
  total: number
}

export async function fetchNotifications(params?: {
  unread_only?: boolean
  page?: number
  page_size?: number
}): Promise<NotificationListResponse> {
  const query = new URLSearchParams()
  if (params?.unread_only) query.set('unread_only', 'true')
  if (params?.page) query.set('page', params.page.toString())
  if (params?.page_size) query.set('page_size', params.page_size.toString())

  const qs = query.toString() ? `?${query.toString()}` : ''
  return apiRequest<NotificationListResponse>(`/api/v1/notifications${qs}`)
}

export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  return apiRequest<UnreadCountResponse>('/api/v1/notifications/unread-count')
}

export async function markNotificationAsRead(id: number): Promise<InAppNotification> {
  return apiRequest<InAppNotification>(`/api/v1/notifications/${id}/read`, {
    method: 'PATCH',
  })
}

export async function markAllNotificationsAsRead(): Promise<{ marked_read: number }> {
  return apiRequest<{ marked_read: number }>('/api/v1/notifications/read-all', {
    method: 'POST',
  })
}

export async function fetchDeadLetters(params?: {
  limit?: number
  offset?: number
}): Promise<DeadLetterListResponse> {
  const query = new URLSearchParams()
  if (params?.limit) query.set('limit', params.limit.toString())
  if (params?.offset) query.set('offset', params.offset.toString())

  const qs = query.toString() ? `?${query.toString()}` : ''
  return apiRequest<DeadLetterListResponse>(`/api/v1/events/dead-letters${qs}`)
}

export async function retryDeadLetterEvent(id: number): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/api/v1/events/dead-letters/${id}/retry`, {
    method: 'POST',
  })
}
