import { api } from './client'

export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
  is_superuser: boolean
  last_login_at: string | null
  version: number
  created_at: string
  updated_at: string
}

export type ScopeType = 'own' | 'department' | 'all'

export interface LoginResponse {
  user: User
  csrf_token: string
  message: string
}

export interface AuthMeResponse {
  user: User
  roles: string[]
  permissions: Record<string, ScopeType>
  department_id: number | null
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>('/api/v1/auth/login', { email, password }),
  logout: () => api.post<{ message: string }>('/api/v1/auth/logout'),
  getMe: () => api.get<AuthMeResponse>('/api/v1/auth/me'),
}
