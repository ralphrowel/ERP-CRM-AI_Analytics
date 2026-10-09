import React, { createContext, useContext, useEffect, useState } from 'react'
import { authApi, type ScopeType, type User } from '../api/auth'

interface AuthContextType {
  user: User | null
  roles: string[]
  permissions: Record<string, ScopeType>
  departmentId: number | null
  isAuthenticated: boolean
  isLoading: boolean
  isSuperuser: boolean
  hasPermission: (permissionCode: string, minScope?: ScopeType) => boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const SCOPE_RANKS: Record<ScopeType, number> = {
  own: 1,
  department: 2,
  all: 3,
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [permissions, setPermissions] = useState<Record<string, ScopeType>>({})
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refreshUser = async () => {
    try {
      const res = await authApi.getMe()
      setUser(res.user)
      setRoles(res.roles || [])
      setPermissions(res.permissions || {})
      setDepartmentId(res.department_id ?? null)
    } catch {
      setUser(null)
      setRoles([])
      setPermissions({})
      setDepartmentId(null)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  const login = async (email: string, password: string) => {
    await authApi.login(email, password)
    await refreshUser()
  }

  const logout = async () => {
    try {
      await authApi.logout()
    } finally {
      setUser(null)
      setRoles([])
      setPermissions({})
      setDepartmentId(null)
    }
  }

  const hasPermission = (permissionCode: string, minScope?: ScopeType): boolean => {
    if (!user) return false
    if (user.is_superuser) return true

    const currentScope = permissions[permissionCode]
    if (!currentScope) return false
    if (!minScope) return true

    return SCOPE_RANKS[currentScope] >= SCOPE_RANKS[minScope]
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        roles,
        permissions,
        departmentId,
        isAuthenticated: !!user,
        isLoading,
        isSuperuser: !!user?.is_superuser,
        hasPermission,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
