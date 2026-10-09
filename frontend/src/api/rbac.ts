import { api } from './client'
import type { ScopeType, User } from './auth'

export interface Permission {
  id: number
  code: string
  description: string | null
  module: string
}

export interface RolePermission {
  permission_id: number
  code: string
  module: string
  description: string | null
  scope: ScopeType
}

export interface Role {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  version: number
  created_at: string
  updated_at: string
  permissions: RolePermission[]
}

export interface RolePermissionInput {
  permission_id: number
  scope: ScopeType
}

export interface RoleCreatePayload {
  code: string
  name: string
  description?: string | null
  permissions: RolePermissionInput[]
}

export interface RoleUpdatePayload {
  name?: string | null
  description?: string | null
  permissions?: RolePermissionInput[] | null
  version: number
}

export interface PaginatedRoles {
  items: Role[]
  total: number
  page: number
  page_size: number
}

export interface PaginatedUsers {
  items: User[]
  total: number
  page: number
  page_size: number
}

export interface UserRoleAssignment {
  role_id: number
  role_code: string
  role_name: string
  assigned_at: string
}

export const rbacApi = {
  // Permissions
  listPermissions: (module?: string) => {
    const qs = module ? `?module=${encodeURIComponent(module)}` : ''
    return api.get<Permission[]>(`/api/v1/permissions${qs}`)
  },

  // Roles
  listRoles: (page = 1, pageSize = 50) =>
    api.get<PaginatedRoles>(`/api/v1/roles?page=${page}&page_size=${pageSize}`),

  getRole: (roleId: number) =>
    api.get<Role>(`/api/v1/roles/${roleId}`),

  createRole: (payload: RoleCreatePayload) =>
    api.post<Role>('/api/v1/roles', payload),

  updateRole: (roleId: number, payload: RoleUpdatePayload) =>
    api.put<Role>(`/api/v1/roles/${roleId}`, payload),

  deleteRole: (roleId: number) =>
    api.delete<void>(`/api/v1/roles/${roleId}`),

  // Users & Role Assignments
  listUsers: (page = 1, pageSize = 50) =>
    api.get<PaginatedUsers>(`/api/v1/users?page=${page}&page_size=${pageSize}`),

  getUserRoles: (userId: number) =>
    api.get<UserRoleAssignment[]>(`/api/v1/users/${userId}/roles`),

  assignUserRoles: (userId: number, roleIds: number[]) =>
    api.put<UserRoleAssignment[]>(`/api/v1/users/${userId}/roles`, {
      role_ids: roleIds,
    }),
}
