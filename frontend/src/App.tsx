import React, { useState } from 'react'
import { AppLayout, type NavTab } from './components/AppLayout'
import { AuthProvider, useAuth } from './context/AuthContext'
import { CompanySettingsPage } from './pages/CompanySettingsPage'
import { CustomersPage } from './pages/CustomersPage'
import { EmployeesPage } from './pages/EmployeesPage'
import { InvoicesPage } from './pages/InvoicesPage'
import { InventoryPage } from './pages/InventoryPage'
import { LeadsPage } from './pages/LeadsPage'
import { LoginPage } from './pages/LoginPage'
import { PaymentsPage } from './pages/PaymentsPage'
import { PipelinePage } from './pages/PipelinePage'
import { ProductsPage } from './pages/ProductsPage'
import { QuotesPage } from './pages/QuotesPage'
import { SalesOrdersPage } from './pages/SalesOrdersPage'
import { SuppliersPage } from './pages/SuppliersPage'
import { PurchaseOrdersPage } from './pages/PurchaseOrdersPage'

const MainRouter: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth()
  const [activeTab, setActiveTab] = useState<NavTab>('leads')

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#080c14',
          color: '#f8fafc',
          gap: '1rem',
        }}
      >
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            border: '3px solid rgba(99, 102, 241, 0.2)',
            borderTopColor: '#6366f1',
            animation: 'spin 0.8s linear infinite',
          }}
        />
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
        <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
          Loading ERP Operational Session...
        </span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <LoginPage />
  }

  return (
    <AppLayout activeTab={activeTab} onTabChange={setActiveTab}>
      {activeTab === 'leads' && <LeadsPage />}
      {activeTab === 'pipeline' && <PipelinePage />}
      {activeTab === 'quotes' && <QuotesPage />}
      {activeTab === 'orders' && <SalesOrdersPage />}
      {activeTab === 'invoices' && <InvoicesPage />}
      {activeTab === 'payments' && <PaymentsPage />}
      {activeTab === 'suppliers' && <SuppliersPage />}
      {activeTab === 'purchase_orders' && <PurchaseOrdersPage />}
      {activeTab === 'inventory' && <InventoryPage />}
      {activeTab === 'customers' && <CustomersPage />}
      {activeTab === 'products' && <ProductsPage />}
      {activeTab === 'employees' && <EmployeesPage />}
      {activeTab === 'settings' && <CompanySettingsPage />}
    </AppLayout>
  )
}

export function App() {
  return (
    <AuthProvider>
      <MainRouter />
    </AuthProvider>
  )
}

export default App
