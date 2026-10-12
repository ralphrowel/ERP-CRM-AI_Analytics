import React, { useCallback, useEffect, useState } from 'react'
import {
  BarChart3,
  Bell,
  Boxes,
  Building2,
  CheckCircle2,
  CheckCheck,
  CreditCard,
  ExternalLink,
  FileCheck,
  FileText,
  History,
  Kanban,
  LogOut,
  Package,
  Receipt,
  Scale,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UploadCloud,
  UserCheck,
  UserPlus,
  Users,
  Wallet,
  Warehouse,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import {
  fetchNotifications,
  fetchUnreadCount,
  type InAppNotification,
  markAllNotificationsAsRead,
  markNotificationAsRead,
} from '../api/notifications'

export type NavTab =
  | 'reports'
  | 'leads'
  | 'pipeline'
  | 'quotes'
  | 'orders'
  | 'invoices'
  | 'payments'
  | 'suppliers'
  | 'purchase_orders'
  | 'goods_receipts'
  | 'supplier_invoices'
  | 'supplier_payments'
  | 'inventory'
  | 'approvals'
  | 'audit_logs'
  | 'customers'
  | 'products'
  | 'imports'
  | 'employees'
  | 'roles'
  | 'settings'
  | 'notifications'

interface AppLayoutProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  children: React.ReactNode
}

export const AppLayout: React.FC<AppLayoutProps> = ({ activeTab, onTabChange, children }) => {
  const { user, logout, hasPermission, isSuperuser } = useAuth()

  const [unreadCount, setUnreadCount] = useState<number>(0)
  const [showBellDropdown, setShowBellDropdown] = useState<boolean>(false)
  const [recentNotifs, setRecentNotifs] = useState<InAppNotification[]>([])
  const [loadingRecent, setLoadingRecent] = useState<boolean>(false)

  const refreshUnread = useCallback(async () => {
    try {
      const res = await fetchUnreadCount()
      setUnreadCount(res.unread_count)
    } catch {
      // background polling
    }
  }, [])

  useEffect(() => {
    refreshUnread()
    const timer = setInterval(refreshUnread, 30000)
    return () => clearInterval(timer)
  }, [refreshUnread])

  const toggleBellDropdown = async () => {
    const next = !showBellDropdown
    setShowBellDropdown(next)
    if (next) {
      setLoadingRecent(true)
      try {
        const resp = await fetchNotifications({ unread_only: true, page: 1, page_size: 5 })
        setRecentNotifs(resp.items)
        setUnreadCount(resp.unread_count)
      } catch (err) {
        console.error('Failed to load recent notifications', err)
      } finally {
        setLoadingRecent(false)
      }
    }
  }

  const handleDropdownMarkAllRead = async () => {
    try {
      await markAllNotificationsAsRead()
      setRecentNotifs([])
      setUnreadCount(0)
    } catch (err) {
      console.error(err)
    }
  }

  const handleDropdownMarkOneRead = async (id: number) => {
    try {
      await markNotificationAsRead(id)
      setRecentNotifs((prev) => prev.filter((n) => n.id !== id))
      setUnreadCount((c) => Math.max(0, c - 1))
    } catch (err) {
      console.error(err)
    }
  }

  const analyticsItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'reports', label: 'Analytics & KPIs', icon: <BarChart3 size={18} /> },
  ]

  const crmItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'leads', label: 'Leads & Inbound', icon: <UserPlus size={18} /> },
    { id: 'pipeline', label: 'Deals & Pipeline', icon: <Kanban size={18} /> },
  ]

  const salesItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'quotes', label: 'Quotes & Proposals', icon: <FileText size={18} /> },
    { id: 'orders', label: 'Sales Orders', icon: <ShoppingCart size={18} /> },
    { id: 'invoices', label: 'Invoices & AR', icon: <Receipt size={18} /> },
    { id: 'payments', label: 'Payments & Credit', icon: <CreditCard size={18} /> },
  ]

  const procurementItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'suppliers', label: 'Suppliers & Vendors', icon: <Truck size={18} /> },
    { id: 'purchase_orders', label: 'Purchase Orders', icon: <FileCheck size={18} /> },
    { id: 'goods_receipts', label: 'Goods Receipts', icon: <Boxes size={18} /> },
    { id: 'supplier_invoices', label: 'Supplier Bills (3-Way)', icon: <Scale size={18} /> },
    { id: 'supplier_payments', label: 'AP Payments', icon: <Wallet size={18} /> },
  ]

  const inventoryItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'inventory', label: 'Inventory & Stock', icon: <Warehouse size={18} /> },
  ]

  const workflowItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'approvals', label: 'Approvals & Governance', icon: <CheckCircle2 size={18} /> },
    {
      id: 'notifications',
      label: unreadCount > 0 ? `Notifications (${unreadCount})` : 'Notifications',
      icon: <Bell size={18} />,
    },
    ...(isSuperuser || hasPermission('audit:read')
      ? [{ id: 'audit_logs' as NavTab, label: 'Audit Trail', icon: <History size={18} /> }]
      : []),
  ]

  const masterDataItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'customers', label: 'Customers', icon: <Users size={18} /> },
    { id: 'products', label: 'Product Catalog', icon: <Package size={18} /> },
    { id: 'imports', label: 'Legacy & CSV Imports', icon: <UploadCloud size={18} /> },
    { id: 'employees', label: 'Employees & Org', icon: <UserCheck size={18} /> },
    ...(isSuperuser || hasPermission('role:read')
      ? [{ id: 'roles' as NavTab, label: 'Roles & Security', icon: <ShieldCheck size={18} /> }]
      : []),
    { id: 'settings', label: 'Company Settings', icon: <Building2 size={18} /> },
  ]

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-app)' }}>
      {/* Sidebar */}
      <aside
        style={{
          width: '260px',
          backgroundColor: 'var(--bg-sidebar)',
          borderRight: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          position: 'fixed',
          top: 0,
          bottom: 0,
          left: 0,
          zIndex: 100,
        }}
      >
        {/* Brand */}
        <div
          style={{
            padding: '1.5rem',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(99, 102, 241, 0.4)',
              color: '#ffffff',
              fontWeight: 800,
              fontSize: '1.1rem',
            }}
          >
            E
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '1rem', letterSpacing: '-0.02em', color: '#f8fafc' }}>
              ERP / CRM Core
            </div>
            <div style={{ fontSize: '0.725rem', color: 'var(--text-dim)', fontWeight: 500 }}>
              Operational Monolith v0.1
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav
          style={{
            padding: '1.25rem 0.85rem',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
            overflowY: 'auto',
          }}
        >
          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '0 0.75rem 0.5rem',
            }}
          >
            Analytics & KPIs
          </div>

          {analyticsItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            CRM Operations
          </div>

          {crmItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            Commercial Sales
          </div>

          {salesItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            Procurement & Purchasing
          </div>

          {procurementItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            Inventory & Logistics
          </div>

          {inventoryItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            Workflow & Governance
          </div>

          {workflowItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}

          <div
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--text-dim)',
              letterSpacing: '0.08em',
              padding: '1rem 0.75rem 0.5rem',
            }}
          >
            Master Data
          </div>

          {masterDataItems.map((item) => {
            const isActive = activeTab === item.id
            return (
              <button
                key={item.id}
                id={`nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 600 : 500,
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                  backgroundColor: isActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                  borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        {/* User Card & Logout */}
        <div
          style={{
            padding: '1rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'rgba(0, 0, 0, 0.2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.full_name}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                {user?.is_superuser ? 'Super Administrator' : 'Staff User'}
              </div>
            </div>
            {user?.is_superuser && (
              <span className="badge badge-emerald" title="Superuser Privileges">
                <ShieldCheck size={12} /> Root
              </span>
            )}
          </div>

          <button
            id="logout-btn"
            onClick={logout}
            className="btn btn-secondary"
            style={{ width: '100%', fontSize: '0.8rem', padding: '0.45rem' }}
          >
            <LogOut size={14} /> Log Out
          </button>
        </div>
      </aside>

      {/* Main Content Viewport */}
      <main
        style={{
          marginLeft: '260px',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
        }}
      >
        {/* Top Header */}
        <header
          style={{
            height: '64px',
            backgroundColor: 'rgba(13, 18, 31, 0.8)',
            backdropFilter: 'blur(12px)',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 2rem',
            position: 'sticky',
            top: 0,
            zIndex: 90,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>Enterprise Core</span>
            <span style={{ color: 'var(--text-dim)' }}>/</span>
            <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize' }}>
              {activeTab}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', position: 'relative' }}>
            <span className="badge badge-subtle">
              PHP (₱) · VAT 12%
            </span>
            <span className="badge badge-cyan">
              Asia/Manila (UTC+8)
            </span>

            {/* Notification Bell Button */}
            <div style={{ position: 'relative' }}>
              <button
                id="notification-bell-btn"
                onClick={toggleBellDropdown}
                title="Notifications"
                style={{
                  background: showBellDropdown ? 'rgba(99, 102, 241, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid',
                  borderColor: showBellDropdown ? '#6366f1' : 'var(--border-subtle)',
                  borderRadius: '8px',
                  width: '38px',
                  height: '38px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: showBellDropdown ? '#a5b4fc' : 'var(--text-main)',
                  position: 'relative',
                  transition: 'all 0.15s ease',
                }}
              >
                <Bell size={18} />
                {unreadCount > 0 && (
                  <span
                    id="bell-unread-badge"
                    style={{
                      position: 'absolute',
                      top: '-4px',
                      right: '-4px',
                      backgroundColor: '#ef4444',
                      color: '#ffffff',
                      borderRadius: '999px',
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      minWidth: '18px',
                      height: '18px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: '0 4px',
                      boxShadow: '0 0 8px rgba(239, 68, 68, 0.8)',
                    }}
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Dropdown Menu */}
              {showBellDropdown && (
                <div
                  id="notifications-dropdown-menu"
                  style={{
                    position: 'absolute',
                    top: '46px',
                    right: 0,
                    width: '360px',
                    backgroundColor: 'rgba(15, 23, 42, 0.96)',
                    backdropFilter: 'blur(16px)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '12px',
                    boxShadow: '0 12px 40px rgba(0, 0, 0, 0.6)',
                    zIndex: 1000,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  {/* Dropdown Header */}
                  <div
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--border-subtle)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      backgroundColor: 'rgba(0, 0, 0, 0.2)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#f8fafc' }}>
                        Notifications
                      </span>
                      {unreadCount > 0 && (
                        <span className="badge badge-rose" style={{ fontSize: '0.7rem' }}>
                          {unreadCount} unread
                        </span>
                      )}
                    </div>
                    {unreadCount > 0 && (
                      <button
                        onClick={handleDropdownMarkAllRead}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#38bdf8',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <CheckCheck size={13} /> Mark all read
                      </button>
                    )}
                  </div>

                  {/* Dropdown List */}
                  <div style={{ maxHeight: '320px', overflowY: 'auto' }}>
                    {loadingRecent ? (
                      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
                        Loading...
                      </div>
                    ) : recentNotifs.length === 0 ? (
                      <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--text-dim)' }}>
                        <Bell size={24} style={{ opacity: 0.3, marginBottom: '6px' }} />
                        <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>No unread notifications</div>
                      </div>
                    ) : (
                      recentNotifs.map((notif) => (
                        <div
                          key={notif.id}
                          style={{
                            padding: '12px 16px',
                            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px',
                            backgroundColor: 'rgba(30, 41, 59, 0.4)',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 600, fontSize: '0.825rem', color: '#f8fafc' }}>
                              {notif.title}
                            </span>
                            <button
                              onClick={() => handleDropdownMarkOneRead(notif.id)}
                              title="Mark as read"
                              style={{
                                background: 'none',
                                border: 'none',
                                color: 'var(--text-dim)',
                                cursor: 'pointer',
                                padding: '2px',
                              }}
                            >
                              <CheckCheck size={14} />
                            </button>
                          </div>
                          <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                            {notif.message}
                          </p>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '2px' }}>
                            {new Date(notif.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Dropdown Footer */}
                  <div
                    style={{
                      padding: '10px 16px',
                      borderTop: '1px solid var(--border-subtle)',
                      backgroundColor: 'rgba(0, 0, 0, 0.25)',
                      textAlign: 'center',
                    }}
                  >
                    <button
                      id="view-all-notifications-btn"
                      onClick={() => {
                        setShowBellDropdown(false)
                        onTabChange('notifications')
                      }}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#818cf8',
                        fontWeight: 600,
                        fontSize: '0.825rem',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      View all notifications <ExternalLink size={13} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Page Container */}
        <div style={{ padding: '2rem', flex: 1 }}>{children}</div>
      </main>
    </div>
  )
}
