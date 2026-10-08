import React from 'react'
import {
  Building2,
  CreditCard,
  FileText,
  Kanban,
  LogOut,
  Package,
  Receipt,
  ShieldCheck,
  ShoppingCart,
  UserCheck,
  UserPlus,
  Users,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export type NavTab =
  | 'leads'
  | 'pipeline'
  | 'quotes'
  | 'orders'
  | 'invoices'
  | 'payments'
  | 'customers'
  | 'products'
  | 'employees'
  | 'settings'

interface AppLayoutProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  children: React.ReactNode
}

export const AppLayout: React.FC<AppLayoutProps> = ({ activeTab, onTabChange, children }) => {
  const { user, logout } = useAuth()

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

  const masterDataItems: Array<{ id: NavTab; label: string; icon: React.ReactNode }> = [
    { id: 'customers', label: 'Customers', icon: <Users size={18} /> },
    { id: 'products', label: 'Product Catalog', icon: <Package size={18} /> },
    { id: 'employees', label: 'Employees & Org', icon: <UserCheck size={18} /> },
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
        <nav style={{ padding: '1.25rem 0.85rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
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

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span className="badge badge-subtle">
              PHP (₱) · VAT 12%
            </span>
            <span className="badge badge-cyan">
              Asia/Manila (UTC+8)
            </span>
          </div>
        </header>

        {/* Page Container */}
        <div style={{ padding: '2rem', flex: 1 }}>{children}</div>
      </main>
    </div>
  )
}
