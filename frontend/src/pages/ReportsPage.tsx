import React, { useEffect, useState, useMemo } from 'react'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Coins,
  DollarSign,
  Layers,
  PieChart,
  RefreshCw,
  ShieldAlert,
  ShoppingCart,
  TrendingUp,
  Truck,
  Warehouse,
} from 'lucide-react'
import {
  fetchARAgingReport,
  fetchExecutiveSummary,
  fetchInventoryReport,
  fetchPipelineReport,
  fetchProcurementReport,
  fetchRevenueReport,
  type ARAgingResponse,
  type ExecutiveSummaryResponse,
  type InventoryReportResponse,
  type PipelineReportResponse,
  type ProcurementReportResponse,
  type RevenueReportResponse,
} from '../api/reporting'

type ReportSection =
  | 'overview'
  | 'revenue'
  | 'ar_aging'
  | 'pipeline'
  | 'inventory'
  | 'procurement'

export const ReportsPage: React.FC = () => {
  const [activeSection, setActiveSection] = useState<ReportSection>('overview')
  const [timeRange, setTimeRange] = useState<'month' | 'quarter' | 'ytd' | 'custom'>('month')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Report States
  const [summaryData, setSummaryData] = useState<ExecutiveSummaryResponse | null>(null)
  const [revenueData, setRevenueData] = useState<RevenueReportResponse | null>(null)
  const [arAgingData, setArAgingData] = useState<ARAgingResponse | null>(null)
  const [pipelineData, setPipelineData] = useState<PipelineReportResponse | null>(null)
  const [inventoryData, setInventoryData] = useState<InventoryReportResponse | null>(null)
  const [procurementData, setProcurementData] = useState<ProcurementReportResponse | null>(null)

  // Date Range Calculation
  const dateParams = useMemo(() => {
    const today = new Date()
    const todayStr = today.toISOString().split('T')[0]

    if (timeRange === 'month') {
      const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)
      return {
        period_start: startOfMonth.toISOString().split('T')[0],
        period_end: todayStr,
      }
    } else if (timeRange === 'quarter') {
      const startOfQuarter = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000)
      return {
        period_start: startOfQuarter.toISOString().split('T')[0],
        period_end: todayStr,
      }
    } else if (timeRange === 'ytd') {
      const startOfYear = new Date(today.getFullYear(), 0, 1)
      return {
        period_start: startOfYear.toISOString().split('T')[0],
        period_end: todayStr,
      }
    }
    return {}
  }, [timeRange])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [sumRes, revRes, arRes, pipeRes, invRes, procRes] = await Promise.all([
        fetchExecutiveSummary(dateParams).catch(() => null),
        fetchRevenueReport(dateParams).catch(() => null),
        fetchARAgingReport().catch(() => null),
        fetchPipelineReport(dateParams).catch(() => null),
        fetchInventoryReport().catch(() => null),
        fetchProcurementReport(dateParams).catch(() => null),
      ])

      setSummaryData(sumRes)
      setRevenueData(revRes)
      setArAgingData(arRes)
      setPipelineData(pipeRes)
      setInventoryData(invRes)
      setProcurementData(procRes)
    } catch (err: any) {
      setError(err?.message || 'Failed to load reporting data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [dateParams])

  const getKPISymbol = (kpiId: string) => {
    switch (kpiId) {
      case 'KPI-001':
      case 'KPI-002':
        return <Coins size={18} />
      case 'KPI-003':
        return <TrendingUp size={18} />
      case 'KPI-004':
        return <ShoppingCart size={18} />
      case 'KPI-005':
      case 'KPI-018':
        return <DollarSign size={18} />
      case 'KPI-007':
      case 'KPI-008':
        return <PieChart size={18} />
      case 'KPI-013':
        return <Warehouse size={18} />
      case 'KPI-015':
        return <AlertTriangle size={18} />
      case 'KPI-016':
      case 'KPI-017':
        return <Truck size={18} />
      default:
        return <BarChart3 size={18} />
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', paddingBottom: '3rem' }}>
      {/* Page Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                backgroundColor: 'rgba(99, 102, 241, 0.15)',
                color: '#818cf8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <BarChart3 size={20} />
            </div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-main)' }}>
              Operational Analytics & KPIs
            </h1>
          </div>
          <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Live Operational Monolith Metrics · Authority: KPI Dictionary (KPI-001 to KPI-018)
          </p>
        </div>

        {/* Global Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div
            style={{
              display: 'flex',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '2px',
            }}
          >
            {(
              [
                { id: 'month', label: 'This Month' },
                { id: 'quarter', label: 'Trailing 90D' },
                { id: 'ytd', label: 'YTD' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                onClick={() => setTimeRange(opt.id)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  border: 'none',
                  backgroundColor: timeRange === opt.id ? 'var(--primary-color)' : 'transparent',
                  color: timeRange === opt.id ? '#ffffff' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            onClick={loadData}
            disabled={isLoading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-card)',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            color: '#f87171',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <ShieldAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Navigation Sub-Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '0.5rem',
          overflowX: 'auto',
        }}
      >
        {(
          [
            { id: 'overview', label: 'Executive Scorecard', icon: <Layers size={16} /> },
            { id: 'revenue', label: 'Revenue & Gross Margin', icon: <TrendingUp size={16} /> },
            { id: 'ar_aging', label: 'AR Aging Matrix', icon: <DollarSign size={16} /> },
            { id: 'pipeline', label: 'Sales Funnel & Velocity', icon: <PieChart size={16} /> },
            { id: 'inventory', label: 'Inventory Valuation', icon: <Warehouse size={16} /> },
            { id: 'procurement', label: 'Procurement & Spend', icon: <Truck size={16} /> },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveSection(tab.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: activeSection === tab.id ? 'rgba(99, 102, 241, 0.12)' : 'transparent',
              color: activeSection === tab.id ? '#818cf8' : 'var(--text-muted)',
              fontWeight: activeSection === tab.id ? 600 : 500,
              fontSize: '0.88rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s ease',
            }}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 1: Executive Overview Scorecard */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: '1rem',
            }}
          >
            {summaryData?.scorecards.map((card) => (
              <div
                key={card.kpi_id}
                style={{
                  backgroundColor: 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '12px',
                  padding: '1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                  position: 'relative',
                  overflow: 'hidden',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: 'var(--primary-color)',
                      backgroundColor: 'rgba(99, 102, 241, 0.1)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                    }}
                  >
                    <span>{card.kpi_id}</span>
                  </div>
                  <div style={{ color: 'var(--text-muted)' }}>{getKPISymbol(card.kpi_id)}</div>
                </div>

                <div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                    {card.kpi_name}
                  </div>
                  <div style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    {card.formatted_value}
                  </div>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    borderTop: '1px solid var(--border-color)',
                    paddingTop: '6px',
                  }}
                >
                  <span>{card.domain}</span>
                  {card.trend === 'up' && (
                    <span style={{ color: '#34d399', display: 'flex', alignItems: 'center', gap: '2px' }}>
                      <ArrowUpRight size={14} /> Positive
                    </span>
                  )}
                  {card.trend === 'down' && (
                    <span style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: '2px' }}>
                      <ArrowDownRight size={14} /> Alert
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 2: Revenue & Gross Margin */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'revenue' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Key Totals */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-001: Net Revenue (Accrual)
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399' }}>
                ₱{Number(revenueData?.net_revenue || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Total Invoices: {revenueData?.total_invoices || 0} · Credit Notes: {revenueData?.total_credit_notes || 0}
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-002: Gross Margin (Net Rev - COGS)
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#60a5fa' }}>
                ₱{Number(revenueData?.gross_margin || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Evaluated from posted fulfillment dispatches
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-003: Gross Margin %
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#c084fc' }}>
                {Number(revenueData?.gross_margin_pct || 0).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Target: &ge; 25.0%
              </div>
            </div>
          </div>

          {/* Monthly Trend Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', fontWeight: 600 }}>
              Monthly Accrual Performance Trend
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>Month</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Gross Invoiced</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Credit Notes</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Net Revenue</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>COGS</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Gross Margin</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Margin %</th>
                  </tr>
                </thead>
                <tbody>
                  {revenueData?.trend && revenueData.trend.length > 0 ? (
                    revenueData.trend.map((pt) => (
                      <tr key={pt.month} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '12px', fontWeight: 600 }}>{pt.month}</td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          ₱{Number(pt.gross_invoiced).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#f87171' }}>
                          ₱{Number(pt.credit_notes).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600, color: '#34d399' }}>
                          ₱{Number(pt.net_revenue).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          ₱{Number(pt.cogs).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>
                          ₱{Number(pt.gross_margin).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#818cf8' }}>
                          {Number(pt.gross_margin_pct).toFixed(1)}%
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No invoices or shipments posted in this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 3: AR Aging Matrix */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'ar_aging' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* AR Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-005: Total AR Outstanding
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>
                ₱{Number(arAgingData?.total_outstanding || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Open balance across all customers
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-018: Days Sales Outstanding (DSO)
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f59e0b' }}>
                {arAgingData?.dso_days ? `${Number(arAgingData.dso_days).toFixed(1)} Days` : 'N/A'}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Based on trailing 90 days net revenue
              </div>
            </div>
          </div>

          {/* 5-Bucket Visual Bar */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>
              KPI-006: Accounts Receivable Aging Buckets
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem' }}>
              {arAgingData?.buckets.map((b) => (
                <div
                  key={b.bucket}
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1rem',
                  }}
                >
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                    {b.label}
                  </div>
                  <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    ₱{Number(b.amount).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    {b.count} invoices · {Number(b.percentage).toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Customer Aging Breakdown Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>
              Customer Receivables Matrix
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>Customer</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Total Balance</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Current</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>1–30 Days</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>31–60 Days</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>61–90 Days</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>90+ Days</th>
                  </tr>
                </thead>
                <tbody>
                  {arAgingData?.customers && arAgingData.customers.length > 0 ? (
                    arAgingData.customers.map((c) => (
                      <tr key={c.customer_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '12px' }}>
                          <div style={{ fontWeight: 600 }}>{c.customer_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{c.customer_no}</div>
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                          ₱{Number(c.total_balance).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#34d399' }}>
                          ₱{Number(c.current).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#fbbf24' }}>
                          ₱{Number(c.days_1_30).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#f97316' }}>
                          ₱{Number(c.days_31_60).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#ef4444' }}>
                          ₱{Number(c.days_61_90).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#dc2626', fontWeight: 700 }}>
                          ₱{Number(c.days_90_plus).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        All issued invoices are fully paid.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 4: Sales Funnel & Pipeline Velocity */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'pipeline' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Pipeline Velocity KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-007: Weighted Pipeline
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--primary-color)' }}>
                ₱{Number(pipelineData?.weighted_pipeline || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Nominal: ₱{Number(pipelineData?.total_open_amount || 0).toLocaleString('en-PH')}
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-008: Win Rate
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#34d399' }}>
                {Number(pipelineData?.win_rate_pct || 0).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Closed deals cohort
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-009: Lead Conversion Rate
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#60a5fa' }}>
                {Number(pipelineData?.lead_conversion_pct || 0).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Inbound leads converted
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-010: Avg Sales Cycle
              </div>
              <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#c084fc' }}>
                {Number(pipelineData?.avg_sales_cycle_days || 0).toFixed(1)} Days
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Opportunity creation to Won
              </div>
            </div>
          </div>

          {/* Stage Funnel Distribution */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>
              Active Pipeline Stage Funnel
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
              {pipelineData?.stages.map((st) => (
                <div
                  key={st.stage}
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{st.label}</span>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        color: '#818cf8',
                        fontWeight: 600,
                      }}
                    >
                      {st.count} Deals
                    </span>
                  </div>
                  <div style={{ marginTop: '0.75rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Nominal Amount</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>
                      ₱{Number(st.nominal_amount).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div style={{ marginTop: '0.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Weighted Forecast</div>
                    <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--primary-color)' }}>
                      ₱{Number(st.weighted_amount).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 5: Inventory Valuation & Alerts */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'inventory' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Inventory Valuation Header */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-013: Total Inventory Value (WAC)
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399' }}>
                ₱{Number(inventoryData?.total_inventory_value || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Valued across all warehouses at weighted-average cost
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-015: Low-Stock SKU Count
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: inventoryData?.low_stock_count ? '#f87171' : '#34d399' }}>
                {inventoryData?.low_stock_count || 0} Items
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Available quantity below defined reorder point
              </div>
            </div>
          </div>

          {/* Warehouse Breakdown */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>
              Warehouse Stock Capitalization
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '1rem' }}>
              {inventoryData?.warehouses.map((wh) => (
                <div
                  key={wh.warehouse_id}
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1rem',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{wh.warehouse_name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Code: {wh.warehouse_code}</div>
                  <div style={{ marginTop: '0.75rem', fontSize: '1.2rem', fontWeight: 700, color: '#34d399' }}>
                    ₱{Number(wh.total_value).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{wh.sku_count} distinct SKUs</div>
                </div>
              ))}
            </div>
          </div>

          {/* Low Stock Alerts Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertTriangle size={18} color="#f87171" />
              <span>Low-Stock Reorder Triggers</span>
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>SKU</th>
                    <th style={{ padding: '10px 12px' }}>Product Name</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>On Hand</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Reserved</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Available</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Reorder Point</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right', color: '#f87171' }}>Deficit</th>
                  </tr>
                </thead>
                <tbody>
                  {inventoryData?.low_stock_items && inventoryData.low_stock_items.length > 0 ? (
                    inventoryData.low_stock_items.map((item) => (
                      <tr key={item.product_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '12px', fontWeight: 600 }}>{item.sku}</td>
                        <td style={{ padding: '12px' }}>{item.name}</td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          {Number(item.qty_on_hand).toFixed(2)} {item.uom}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          {Number(item.qty_reserved).toFixed(2)} {item.uom}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>
                          {Number(item.qty_available).toFixed(2)} {item.uom}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)' }}>
                          {Number(item.reorder_point).toFixed(2)} {item.uom}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#f87171' }}>
                          -{Number(item.deficit).toFixed(2)} {item.uom}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: '#34d399' }}>
                        All stock items are currently above their reorder thresholds.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* Section 6: Procurement & Vendor Spend */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {activeSection === 'procurement' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-016: Total Purchase Spend (VAT Exclusive)
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#f59e0b' }}>
                ₱{Number(procurementData?.total_purchase_spend || 0).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Approved supplier invoices and AP commitments
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '1.25rem',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                KPI-017: Supplier On-Time Delivery Rate
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399' }}>
                {Number(procurementData?.overall_on_time_rate_pct || 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Receipt dates on or before PO expected delivery date
              </div>
            </div>
          </div>

          {/* Supplier Spend Ranking Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>
              Top Supplier Spend Ranking
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>Supplier</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Bills Approved</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Total Spend</th>
                  </tr>
                </thead>
                <tbody>
                  {procurementData?.suppliers && procurementData.suppliers.length > 0 ? (
                    procurementData.suppliers.map((s) => (
                      <tr key={s.supplier_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '12px' }}>
                          <div style={{ fontWeight: 600 }}>{s.supplier_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{s.supplier_no}</div>
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>{s.bill_count}</td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#f59e0b' }}>
                          ₱{Number(s.spend).toLocaleString('en-PH', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={3} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No supplier invoices recorded in this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
