import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle,
  Edit2,
  KeyRound,
  Lock,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
  UserCheck,
  Users,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type ScopeType, type User } from '../api/auth'
import {
  type Permission,
  type Role,
  type RolePermissionInput,
  type UserRoleAssignment,
  rbacApi,
} from '../api/rbac'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { useAuth } from '../context/AuthContext'

export const RolesPage: React.FC = () => {
  const { hasPermission, isSuperuser } = useAuth()

  // Tab: 'roles' | 'users'
  const [activeTab, setActiveTab] = useState<'roles' | 'users'>('roles')

  // Data states
  const [roles, setRoles] = useState<Role[]>([])
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Feedback states
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Create Role Modal
  const [isCreateRoleOpen, setIsCreateRoleOpen] = useState(false)
  const [newRoleCode, setNewRoleCode] = useState('')
  const [newRoleName, setNewRoleName] = useState('')
  const [newRoleDesc, setNewRoleDesc] = useState('')
  const [newRolePerms, setNewRolePerms] = useState<Record<number, ScopeType>>({})

  // Edit Role Modal
  const [isEditRoleOpen, setIsEditRoleOpen] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [editRoleName, setEditRoleName] = useState('')
  const [editRoleDesc, setEditRoleDesc] = useState('')
  const [editRolePerms, setEditRolePerms] = useState<Record<number, ScopeType>>({})

  // User Role Assignment Modal
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [userAssignedRoleIds, setUserAssignedRoleIds] = useState<number[]>([])
  const [isAssignLoading, setIsAssignLoading] = useState(false)

  // Delete Confirmation
  const [deletingRoleId, setDeletingRoleId] = useState<number | null>(null)

  // Permissions checking
  const canCreateRoles = isSuperuser || hasPermission('role:create')
  const canUpdateRoles = isSuperuser || hasPermission('role:update')
  const canDeleteRoles = isSuperuser || hasPermission('role:delete')
  const canAssignRoles = isSuperuser || hasPermission('role:assign')

  const fetchData = async () => {
    setIsLoading(true)
    setGeneralError(null)
    setConflictError(null)
    try {
      const [rolesRes, permsRes, usersRes] = await Promise.all([
        rbacApi.listRoles(1, 100),
        rbacApi.listPermissions(),
        rbacApi.listUsers(1, 100),
      ])
      setRoles(rolesRes.items)
      setPermissions(permsRes)
      setUsers(usersRes.items)
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
  }, [])

  // Group permissions by module
  const permissionsByModule = permissions.reduce<Record<string, Permission[]>>((acc, perm) => {
    const mod = perm.module || 'other'
    if (!acc[mod]) acc[mod] = []
    acc[mod].push(perm)
    return acc
  }, {})

  // Handle open create modal
  const handleOpenCreateModal = () => {
    setNewRoleCode('')
    setNewRoleName('')
    setNewRoleDesc('')
    setNewRolePerms({})
    setConflictError(null)
    setGeneralError(null)
    setIsCreateRoleOpen(true)
  }

  // Handle submit create role
  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault()
    setConflictError(null)
    setGeneralError(null)

    const permInputs: RolePermissionInput[] = Object.entries(newRolePerms).map(
      ([permId, scope]) => ({
        permission_id: Number(permId),
        scope,
      })
    )

    try {
      await rbacApi.createRole({
        code: newRoleCode.trim().toLowerCase(),
        name: newRoleName.trim(),
        description: newRoleDesc.trim() || null,
        permissions: permInputs,
      })
      setSuccessMessage(`Role "${newRoleName}" created successfully.`)
      setIsCreateRoleOpen(false)
      fetchData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError(err.problem?.detail || 'A role with this code already exists.')
      } else if (err instanceof Error) {
        setGeneralError(err)
      }
    }
  }

  // Handle open edit modal
  const handleOpenEditModal = (role: Role) => {
    setEditingRole(role)
    setEditRoleName(role.name)
    setEditRoleDesc(role.description || '')
    const permMap: Record<number, ScopeType> = {}
    role.permissions.forEach((p) => {
      permMap[p.permission_id] = p.scope
    })
    setEditRolePerms(permMap)
    setConflictError(null)
    setGeneralError(null)
    setIsEditRoleOpen(true)
  }

  // Handle submit edit role
  const handleUpdateRole = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingRole) return
    setConflictError(null)
    setGeneralError(null)

    const permInputs: RolePermissionInput[] = Object.entries(editRolePerms).map(
      ([permId, scope]) => ({
        permission_id: Number(permId),
        scope,
      })
    )

    try {
      await rbacApi.updateRole(editingRole.id, {
        name: editRoleName.trim(),
        description: editRoleDesc.trim() || null,
        permissions: permInputs,
        version: editingRole.version,
      })
      setSuccessMessage(`Role "${editRoleName}" updated successfully. Sessions re-synchronized.`)
      setIsEditRoleOpen(false)
      fetchData()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.isConflict) {
        setConflictError('Concurrency conflict: this role was modified by another user. Please refresh.')
      } else if (err instanceof Error) {
        setGeneralError(err)
      }
    }
  }

  // Handle delete role
  const handleDeleteRole = async (roleId: number) => {
    if (!window.confirm('Are you sure you want to delete this custom role? This cannot be undone.')) {
      return
    }
    setDeletingRoleId(roleId)
    try {
      await rbacApi.deleteRole(roleId)
      setSuccessMessage('Role deleted successfully.')
      fetchData()
    } catch (err: unknown) {
      if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setDeletingRoleId(null)
    }
  }

  // Handle open user role assignment
  const handleOpenAssignModal = async (u: User) => {
    setSelectedUser(u)
    setIsAssignLoading(true)
    setIsAssignModalOpen(true)
    try {
      const assignments: UserRoleAssignment[] = await rbacApi.getUserRoles(u.id)
      setUserAssignedRoleIds(assignments.map((a) => a.role_id))
    } catch (err: unknown) {
      if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setIsAssignLoading(false)
    }
  }

  // Handle submit user role assignment
  const handleSaveUserRoles = async () => {
    if (!selectedUser) return
    setIsAssignLoading(true)
    try {
      await rbacApi.assignUserRoles(selectedUser.id, userAssignedRoleIds)
      setSuccessMessage(`Assigned roles updated for user ${selectedUser.full_name}. Active sessions revoked for security.`)
      setIsAssignModalOpen(false)
      fetchData()
    } catch (err: unknown) {
      if (err instanceof Error) {
        setGeneralError(err)
      }
    } finally {
      setIsAssignLoading(false)
    }
  }

  const toggleUserRoleId = (roleId: number) => {
    setUserAssignedRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((id) => id !== roleId) : [...prev, roleId]
    )
  }

  // Scope badge rendering
  const renderScopeBadge = (scope: ScopeType) => {
    switch (scope) {
      case 'all':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '0.7rem',
              fontWeight: 700,
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            All Org
          </span>
        )
      case 'department':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '0.7rem',
              fontWeight: 700,
              backgroundColor: 'rgba(6, 182, 212, 0.15)',
              color: '#22d3ee',
              border: '1px solid rgba(6, 182, 212, 0.3)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Dept
          </span>
        )
      case 'own':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '0.7rem',
              fontWeight: 700,
              backgroundColor: 'rgba(245, 158, 11, 0.15)',
              color: '#fbbf24',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Own Only
          </span>
        )
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Title & Top Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.6rem',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: '#f8fafc',
              display: 'flex',
              alignItems: 'center',
              gap: '0.6rem',
            }}
          >
            <Shield size={28} style={{ color: '#818cf8' }} />
            Roles & Permissions Matrix
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '0.2rem' }}>
            Enterprise Role-Based Access Control (RBAC) with granular multi-level scoping (Own, Department, All).
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            onClick={fetchData}
            disabled={isLoading}
            className="btn btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
          >
            <RefreshCw size={15} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>

          {activeTab === 'roles' && canCreateRoles && (
            <button
              id="create-role-btn"
              onClick={handleOpenCreateModal}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
            >
              <Plus size={16} />
              New Role
            </button>
          )}
        </div>
      </div>

      {/* Alerts */}
      {successMessage && (
        <div
          style={{
            padding: '0.85rem 1rem',
            borderRadius: '8px',
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            color: '#34d399',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <CheckCircle size={18} />
            <span>{successMessage}</span>
          </div>
          <button
            onClick={() => setSuccessMessage(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1rem' }}
          >
            ✕
          </button>
        </div>
      )}

      {conflictError && <ConflictAlert message={conflictError} onReload={fetchData} />}
      {generalError && <ProblemAlert error={generalError} />}

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '0.5rem',
        }}
      >
        <button
          id="tab-roles-matrix"
          onClick={() => setActiveTab('roles')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.6rem 1.2rem',
            borderRadius: '8px',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 600,
            transition: 'all 0.15s ease',
            backgroundColor: activeTab === 'roles' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            color: activeTab === 'roles' ? '#a5b4fc' : 'var(--text-muted)',
            borderBottom: activeTab === 'roles' ? '2px solid #6366f1' : '2px solid transparent',
          }}
        >
          <KeyRound size={16} />
          Roles & Permissions ({roles.length})
        </button>

        <button
          id="tab-user-assignments"
          onClick={() => setActiveTab('users')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.6rem 1.2rem',
            borderRadius: '8px',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 600,
            transition: 'all 0.15s ease',
            backgroundColor: activeTab === 'users' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            color: activeTab === 'users' ? '#a5b4fc' : 'var(--text-muted)',
            borderBottom: activeTab === 'users' ? '2px solid #6366f1' : '2px solid transparent',
          }}
        >
          <Users size={16} />
          User Role Assignments ({users.length})
        </button>
      </div>

      {/* TAB 1: ROLES & MATRIX */}
      {activeTab === 'roles' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '1.25rem 1.5rem',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc' }}>
                  Defined Enterprise Roles
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                  System roles are protected, while custom roles can be defined with customized permissions and data scoping.
                </p>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Code</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Role Name</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Type</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Description</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Permissions</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((r) => (
                    <tr
                      key={r.id}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        transition: 'background-color 0.1s',
                      }}
                    >
                      <td style={{ padding: '1rem 1.25rem', fontFamily: 'monospace', fontWeight: 600, color: '#cbd5e1' }}>
                        {r.code}
                      </td>
                      <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: '#f8fafc' }}>
                        {r.name}
                      </td>
                      <td style={{ padding: '1rem 1.25rem' }}>
                        {r.is_system ? (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '0.725rem',
                              fontWeight: 600,
                              backgroundColor: 'rgba(99, 102, 241, 0.15)',
                              color: '#a5b4fc',
                              border: '1px solid rgba(99, 102, 241, 0.3)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Lock size={11} /> System
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '0.725rem',
                              fontWeight: 600,
                              backgroundColor: 'rgba(148, 163, 184, 0.1)',
                              color: '#94a3b8',
                              border: '1px solid rgba(148, 163, 184, 0.2)',
                            }}
                          >
                            Custom
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '1rem 1.25rem', color: 'var(--text-muted)', maxWidth: '300px' }}>
                        {r.description || '—'}
                      </td>
                      <td style={{ padding: '1rem 1.25rem' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', maxWidth: '420px' }}>
                          {r.permissions.length === 0 ? (
                            <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>No permissions</span>
                          ) : (
                            r.permissions.slice(0, 5).map((p) => (
                              <span
                                key={p.permission_id}
                                title={`${p.code} (${p.scope})`}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                                  border: '1px solid var(--border-subtle)',
                                  fontSize: '0.725rem',
                                }}
                              >
                                <span>{p.code}</span>
                                {renderScopeBadge(p.scope)}
                              </span>
                            ))
                          )}
                          {r.permissions.length > 5 && (
                            <span
                              style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                                fontSize: '0.725rem',
                                color: 'var(--text-muted)',
                              }}
                            >
                              +{r.permissions.length - 5} more
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                          {canUpdateRoles && (
                            <button
                              id={`edit-role-${r.id}`}
                              onClick={() => handleOpenEditModal(r)}
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                              title="Edit Role & Permissions"
                            >
                              <Edit2 size={13} /> Edit
                            </button>
                          )}
                          {!r.is_system && canDeleteRoles && (
                            <button
                              id={`delete-role-${r.id}`}
                              onClick={() => handleDeleteRole(r.id)}
                              disabled={deletingRoleId === r.id}
                              className="btn btn-secondary"
                              style={{
                                padding: '0.35rem 0.65rem',
                                fontSize: '0.75rem',
                                color: '#f87171',
                                borderColor: 'rgba(248, 113, 113, 0.3)',
                              }}
                              title="Delete Custom Role"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: USER ROLE ASSIGNMENTS */}
      {activeTab === 'users' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '1.25rem 1.5rem',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc' }}>
                  User Role Assignments
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                  Modifying user roles immediately revokes active user sessions to guarantee instant permission enforcement.
                </p>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>User</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Email</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Privilege Level</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600 }}>Status</th>
                    <th style={{ padding: '0.85rem 1.25rem', color: 'var(--text-muted)', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        transition: 'background-color 0.1s',
                      }}
                    >
                      <td style={{ padding: '1rem 1.25rem', fontWeight: 600, color: '#f8fafc' }}>
                        {u.full_name}
                      </td>
                      <td style={{ padding: '1rem 1.25rem', color: 'var(--text-muted)' }}>
                        {u.email}
                      </td>
                      <td style={{ padding: '1rem 1.25rem' }}>
                        {u.is_superuser ? (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '0.725rem',
                              fontWeight: 700,
                              backgroundColor: 'rgba(16, 185, 129, 0.15)',
                              color: '#34d399',
                              border: '1px solid rgba(16, 185, 129, 0.3)',
                            }}
                          >
                            Super Administrator
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '0.725rem',
                              fontWeight: 500,
                              backgroundColor: 'rgba(255, 255, 255, 0.05)',
                              color: '#cbd5e1',
                            }}
                          >
                            Standard User
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '1rem 1.25rem' }}>
                        {u.is_active ? (
                          <span style={{ color: '#34d399', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <CheckCircle size={13} /> Active
                          </span>
                        ) : (
                          <span style={{ color: '#f87171', fontSize: '0.8rem' }}>Deactivated</span>
                        )}
                      </td>
                      <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                        {canAssignRoles && (
                          <button
                            id={`assign-roles-user-${u.id}`}
                            onClick={() => handleOpenAssignModal(u)}
                            className="btn btn-secondary"
                            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                          >
                            <UserCheck size={13} /> Manage Roles
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: CREATE ROLE */}
      <Modal
        isOpen={isCreateRoleOpen}
        onClose={() => setIsCreateRoleOpen(false)}
        title="Create New Operational Role"
      >
        <form onSubmit={handleCreateRole} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem', color: '#cbd5e1' }}>
                Role Code <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                id="role-code-input"
                type="text"
                placeholder="e.g. sales_supervisor"
                value={newRoleCode}
                onChange={(e) => setNewRoleCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                required
                className="input-field"
                style={{ width: '100%' }}
              />
              <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)', marginTop: '0.2rem', display: 'block' }}>
                Lowercase alphanumeric and underscores only.
              </span>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem', color: '#cbd5e1' }}>
                Role Name <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                id="role-name-input"
                type="text"
                placeholder="e.g. Sales Supervisor"
                value={newRoleName}
                onChange={(e) => setNewRoleName(e.target.value)}
                required
                className="input-field"
                style={{ width: '100%' }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem', color: '#cbd5e1' }}>
              Description
            </label>
            <input
              id="role-desc-input"
              type="text"
              placeholder="e.g. Can manage quotes, leads, and orders in department"
              value={newRoleDesc}
              onChange={(e) => setNewRoleDesc(e.target.value)}
              className="input-field"
              style={{ width: '100%' }}
            />
          </div>

          {/* Permissions Matrix Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.5rem', color: '#cbd5e1' }}>
              Permissions & Scope Assignment
            </label>
            <div
              style={{
                maxHeight: '340px',
                overflowY: 'auto',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '0.75rem',
                backgroundColor: 'rgba(0, 0, 0, 0.2)',
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem',
              }}
            >
              {Object.entries(permissionsByModule).map(([mod, perms]) => (
                <div key={mod} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <div
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      color: '#818cf8',
                      letterSpacing: '0.06em',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      paddingBottom: '0.25rem',
                    }}
                  >
                    Module: {mod}
                  </div>
                  {perms.map((p) => {
                    const isChecked = !!newRolePerms[p.id]
                    const currentScope = newRolePerms[p.id] || 'all'
                    return (
                      <div
                        key={p.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.35rem 0.5rem',
                          borderRadius: '6px',
                          backgroundColor: isChecked ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                        }}
                      >
                        <label
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            cursor: 'pointer',
                            fontSize: '0.8rem',
                            color: isChecked ? '#f8fafc' : 'var(--text-muted)',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              const checked = e.target.checked
                              setNewRolePerms((prev) => {
                                const next = { ...prev }
                                if (checked) {
                                  next[p.id] = 'all'
                                } else {
                                  delete next[p.id]
                                }
                                return next
                              })
                            }}
                          />
                          <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{p.code}</span>
                          {p.description && (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                              - {p.description}
                            </span>
                          )}
                        </label>

                        {isChecked && (
                          <select
                            value={currentScope}
                            onChange={(e) => {
                              const val = e.target.value as ScopeType
                              setNewRolePerms((prev) => ({ ...prev, [p.id]: val }))
                            }}
                            className="input-field"
                            style={{
                              padding: '0.2rem 0.5rem',
                              fontSize: '0.75rem',
                              backgroundColor: 'rgba(15, 23, 42, 0.9)',
                              width: '130px',
                            }}
                          >
                            <option value="all">All (Global)</option>
                            <option value="department">Department</option>
                            <option value="own">Own Records</option>
                          </select>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setIsCreateRoleOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-create-role" type="submit" className="btn btn-primary">
              Create Role
            </button>
          </div>
        </form>
      </Modal>

      {/* MODAL: EDIT ROLE */}
      <Modal
        isOpen={isEditRoleOpen}
        onClose={() => setIsEditRoleOpen(false)}
        title={`Edit Role: ${editingRole?.name || ''}`}
      >
        <form onSubmit={handleUpdateRole} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem', color: '#cbd5e1' }}>
              Role Name <span style={{ color: '#f87171' }}>*</span>
            </label>
            <input
              id="edit-role-name-input"
              type="text"
              value={editRoleName}
              onChange={(e) => setEditRoleName(e.target.value)}
              required
              className="input-field"
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem', color: '#cbd5e1' }}>
              Description
            </label>
            <input
              id="edit-role-desc-input"
              type="text"
              value={editRoleDesc}
              onChange={(e) => setEditRoleDesc(e.target.value)}
              className="input-field"
              style={{ width: '100%' }}
            />
          </div>

          {/* Permissions Matrix Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.5rem', color: '#cbd5e1' }}>
              Permissions & Scopes
            </label>
            <div
              style={{
                maxHeight: '340px',
                overflowY: 'auto',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '0.75rem',
                backgroundColor: 'rgba(0, 0, 0, 0.2)',
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem',
              }}
            >
              {Object.entries(permissionsByModule).map(([mod, perms]) => (
                <div key={mod} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <div
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      color: '#818cf8',
                      letterSpacing: '0.06em',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      paddingBottom: '0.25rem',
                    }}
                  >
                    Module: {mod}
                  </div>
                  {perms.map((p) => {
                    const isChecked = !!editRolePerms[p.id]
                    const currentScope = editRolePerms[p.id] || 'all'
                    return (
                      <div
                        key={p.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.35rem 0.5rem',
                          borderRadius: '6px',
                          backgroundColor: isChecked ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                        }}
                      >
                        <label
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            cursor: 'pointer',
                            fontSize: '0.8rem',
                            color: isChecked ? '#f8fafc' : 'var(--text-muted)',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              const checked = e.target.checked
                              setEditRolePerms((prev) => {
                                const next = { ...prev }
                                if (checked) {
                                  next[p.id] = 'all'
                                } else {
                                  delete next[p.id]
                                }
                                return next
                              })
                            }}
                          />
                          <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{p.code}</span>
                          {p.description && (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                              - {p.description}
                            </span>
                          )}
                        </label>

                        {isChecked && (
                          <select
                            value={currentScope}
                            onChange={(e) => {
                              const val = e.target.value as ScopeType
                              setEditRolePerms((prev) => ({ ...prev, [p.id]: val }))
                            }}
                            className="input-field"
                            style={{
                              padding: '0.2rem 0.5rem',
                              fontSize: '0.75rem',
                              backgroundColor: 'rgba(15, 23, 42, 0.9)',
                              width: '130px',
                            }}
                          >
                            <option value="all">All (Global)</option>
                            <option value="department">Department</option>
                            <option value="own">Own Records</option>
                          </select>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setIsEditRoleOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button id="submit-update-role" type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </Modal>

      {/* MODAL: ASSIGN USER ROLES */}
      <Modal
        isOpen={isAssignModalOpen}
        onClose={() => setIsAssignModalOpen(false)}
        title={`Assign Roles: ${selectedUser?.full_name || ''}`}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(99, 102, 241, 0.1)',
              border: '1px solid rgba(99, 102, 241, 0.25)',
              fontSize: '0.8rem',
              color: '#a5b4fc',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <AlertTriangle size={16} />
            <span>
              Saving role changes immediately terminates existing sessions for this user to enforce revised access.
            </span>
          </div>

          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: '#f8fafc' }}>
              Select Operational Roles
            </div>

            {isAssignLoading ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                Loading user assignments...
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '300px', overflowY: 'auto' }}>
                {roles.map((r) => {
                  const isAssigned = userAssignedRoleIds.includes(r.id)
                  return (
                    <div
                      key={r.id}
                      onClick={() => toggleUserRoleId(r.id)}
                      style={{
                        padding: '0.75rem 1rem',
                        borderRadius: '8px',
                        border: isAssigned
                          ? '1px solid rgba(99, 102, 241, 0.5)'
                          : '1px solid var(--border-subtle)',
                        backgroundColor: isAssigned
                          ? 'rgba(99, 102, 241, 0.12)'
                          : 'rgba(255, 255, 255, 0.02)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.875rem' }}>
                          {r.name}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                          <span style={{ fontFamily: 'monospace' }}>{r.code}</span>
                          {r.description ? ` · ${r.description}` : ''}
                        </div>
                      </div>

                      <div
                        style={{
                          width: '20px',
                          height: '20px',
                          borderRadius: '4px',
                          border: isAssigned ? '1px solid #6366f1' : '1px solid var(--border-subtle)',
                          backgroundColor: isAssigned ? '#6366f1' : 'transparent',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#fff',
                        }}
                      >
                        {isAssigned && <Check size={14} />}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setIsAssignModalOpen(false)}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button
              id="submit-assign-roles"
              type="button"
              onClick={handleSaveUserRoles}
              disabled={isAssignLoading}
              className="btn btn-primary"
            >
              Save Assignments
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
export default RolesPage
