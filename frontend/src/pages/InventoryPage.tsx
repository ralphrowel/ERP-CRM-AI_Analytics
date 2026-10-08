import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Layers,
  Package,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingDown,
  Warehouse as WarehouseIcon,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type InventoryBalance,
  type InventoryReconciliationOut,
  type InventoryTransaction,
  type OpeningBalanceItemPayload,
  type Warehouse,
  inventoryApi,
  warehousesApi,
} from '../api/inventory'
import { type Product, productsApi } from '../api/products'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

type InventoryTab = 'balances' | 'ledger' | 'warehouses' | 'reconciliation'

export const InventoryPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<InventoryTab>('balances')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Data states
  const [balances, setBalances] = useState<InventoryBalance[]>([])
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [reconciliation, setReconciliation] = useState<InventoryReconciliationOut | null>(null)

  // Filters
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number | undefined>(undefined)
  const [selectedProductId, setSelectedProductId] = useState<number | undefined>(undefined)
  const [belowReorderFilter, setBelowReorderFilter] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Modals
  const [isOpeningStockOpen, setIsOpeningStockOpen] = useState(false)
  const [isWarehouseModalOpen, setIsWarehouseModalOpen] = useState(false)
  const [editingWarehouse, setEditingWarehouse] = useState<Warehouse | null>(null)

  // Opening stock form
  const [openingWarehouseId, setOpeningWarehouseId] = useState<number>(0)
  const [openingItems, setOpeningItems] = useState<OpeningBalanceItemPayload[]>([
    { product_id: 0, quantity: '10.000', unit_cost: '100.0000' },
  ])

  // Warehouse form
  const [whCode, setWhCode] = useState('')
  const [whName, setWhName] = useState('')
  const [whAddress, setWhAddress] = useState('')
  const [whIsDefault, setWhIsDefault] = useState(false)
  const [whIsActive, setWhIsActive] = useState(true)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [whRes, prodRes] = await Promise.all([
        warehousesApi.list(),
        productsApi.list({ page_size: 100 }),
      ])
      setWarehouses(whRes)
      setProducts(prodRes.items.filter((p) => p.product_type === 'stock'))

      if (whRes.length > 0 && !openingWarehouseId) {
        const defaultWh = whRes.find((w) => w.is_default) || whRes[0]
        setOpeningWarehouseId(defaultWh.id)
      }

      if (activeTab === 'balances') {
        const balRes = await inventoryApi.listBalances({
          warehouse_id: selectedWarehouseId,
          product_id: selectedProductId,
          below_reorder: belowReorderFilter || undefined,
        })
        setBalances(balRes)
      } else if (activeTab === 'ledger') {
        const txnRes = await inventoryApi.listTransactions({
          warehouse_id: selectedWarehouseId,
          product_id: selectedProductId,
          limit: 150,
        })
        setTransactions(txnRes)
      } else if (activeTab === 'reconciliation') {
        const reconRes = await inventoryApi.getReconciliation()
        setReconciliation(reconRes)
      }
    } catch (err) {
      setError(err as ApiError | Error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [activeTab, selectedWarehouseId, selectedProductId, belowReorderFilter])

  // Calculations for KPI
  const totalValuation = balances.reduce(
    (sum, b) => sum + (parseFloat(b.total_stock_value) || 0),
    0
  )
  const lowStockCount = balances.filter(
    (b) => parseFloat(b.qty_available) <= parseFloat(b.reorder_point)
  ).length
  const totalTrackedItems = balances.length

  const handlePostOpeningBalances = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const validItems = openingItems.filter(
      (item) => item.product_id > 0 && parseFloat(item.quantity) > 0
    )
    if (validItems.length === 0) {
      alert('Please add at least one valid product and quantity.')
      return
    }

    try {
      await inventoryApi.postOpeningBalances({
        warehouse_id: openingWarehouseId,
        items: validItems,
      })
      setSuccessMessage('Opening inventory balances posted to ledger successfully.')
      setIsOpeningStockOpen(false)
      loadData()
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleSaveWarehouse = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingWarehouse) {
        await warehousesApi.update(editingWarehouse.id, {
          name: whName,
          address: whAddress,
          is_default: whIsDefault,
          is_active: whIsActive,
        })
        setSuccessMessage(`Warehouse ${whName} updated.`)
      } else {
        await warehousesApi.create({
          code: whCode,
          name: whName,
          address: whAddress,
          is_default: whIsDefault,
          is_active: whIsActive,
        })
        setSuccessMessage(`Warehouse ${whCode} created.`)
      }
      setIsWarehouseModalOpen(false)
      setEditingWarehouse(null)
      loadData()
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const filteredBalances = balances.filter((b) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      b.product_name.toLowerCase().includes(q) ||
      b.product_sku.toLowerCase().includes(q) ||
      b.warehouse_name.toLowerCase().includes(q)
    )
  })

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
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
          <h1
            style={{
              fontSize: '1.65rem',
              fontWeight: 800,
              letterSpacing: '-0.025em',
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
            }}
          >
            <WarehouseIcon size={26} color="#6366f1" />
            Inventory & Warehouses
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Dual-layer stock architecture: Append-only Truth Ledger and Live Balances Cache with strict reservation locks.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => loadData()}
            className="btn-secondary"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 0.85rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>

          <button
            id="btn-post-opening-stock"
            onClick={() => {
              setIsOpeningStockOpen(true)
              setOpeningItems([{ product_id: products[0]?.id || 0, quantity: '10.000', unit_cost: '100.0000' }])
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.55rem 1rem',
              borderRadius: '8px',
              backgroundColor: '#6366f1',
              color: '#ffffff',
              border: 'none',
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
            }}
          >
            <Package size={16} /> Post Opening Stock
          </button>

          <button
            id="btn-new-warehouse"
            onClick={() => {
              setEditingWarehouse(null)
              setWhCode('')
              setWhName('')
              setWhAddress('')
              setWhIsDefault(false)
              setWhIsActive(true)
              setIsWarehouseModalOpen(true)
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.55rem 1rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(99, 102, 241, 0.15)',
              color: '#a5b4fc',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            <Plus size={16} /> New Warehouse
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && <ProblemAlert error={error} onDismiss={() => setError(null)} />}
      {successMessage && (
        <div
          style={{
            padding: '0.75rem 1rem',
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            borderRadius: '8px',
            color: '#34d399',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{successMessage}</span>
          <button
            onClick={() => setSuccessMessage(null)}
            style={{ background: 'none', border: 'none', color: '#34d399', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Top Metric Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
        }}
      >
        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Total Stock Valuation
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10b981' }}>
            ₱{totalValuation.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Valued at weighted average cost
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Monitored SKUs
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
            {totalTrackedItems}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Stock items across warehouses
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Low Stock Alerts
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: lowStockCount > 0 ? '#ef4444' : '#10b981' }}>
            {lowStockCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Available &le; Reorder Point
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Warehouses Active
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#6366f1' }}>
            {warehouses.filter((w) => w.is_active).length}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            {warehouses.length} total facilities
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid var(--border-subtle)',
          gap: '1.5rem',
          fontSize: '0.9rem',
          fontWeight: 600,
        }}
      >
        <button
          onClick={() => setActiveTab('balances')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'balances' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'balances' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Package size={17} /> Stock Balances & Availability
        </button>

        <button
          onClick={() => setActiveTab('ledger')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'ledger' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'ledger' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Layers size={17} /> Stock Movement Ledger
        </button>

        <button
          onClick={() => setActiveTab('warehouses')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'warehouses' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'warehouses' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Building2 size={17} /> Warehouses ({warehouses.length})
        </button>

        <button
          onClick={() => setActiveTab('reconciliation')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'reconciliation' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'reconciliation' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <ShieldCheck size={17} /> Ledger Reconciliation
        </button>
      </div>

      {/* Tab: Balances */}
      {activeTab === 'balances' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Filters Bar */}
          <div
            style={{
              display: 'flex',
              gap: '1rem',
              alignItems: 'center',
              flexWrap: 'wrap',
              backgroundColor: 'var(--bg-card)',
              padding: '1rem',
              borderRadius: '10px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '220px' }}>
              <Search size={16} color="var(--text-dim)" />
              <input
                type="text"
                placeholder="Search SKU or product name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-main)',
                  fontSize: '0.875rem',
                  outline: 'none',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <select
                value={selectedWarehouseId || ''}
                onChange={(e) =>
                  setSelectedWarehouseId(e.target.value ? parseInt(e.target.value, 10) : undefined)
                }
                style={{
                  padding: '0.45rem 0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                  fontSize: '0.85rem',
                }}
              >
                <option value="">All Warehouses</option>
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.code} - {w.name} {w.is_default ? '(Default)' : ''}
                  </option>
                ))}
              </select>

              <select
                value={selectedProductId || ''}
                onChange={(e) =>
                  setSelectedProductId(e.target.value ? parseInt(e.target.value, 10) : undefined)
                }
                style={{
                  padding: '0.45rem 0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                  fontSize: '0.85rem',
                  maxWidth: '180px',
                }}
              >
                <option value="">All Products</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku} - {p.name}
                  </option>
                ))}
              </select>

              <button
                onClick={() => setBelowReorderFilter(!belowReorderFilter)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: '6px',
                  backgroundColor: belowReorderFilter ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                  border: belowReorderFilter ? '1px solid #ef4444' : '1px solid var(--border-subtle)',
                  color: belowReorderFilter ? '#ef4444' : 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                }}
              >
                <AlertTriangle size={14} /> Below Reorder Only
              </button>
            </div>
          </div>

          {/* Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderBottom: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  <th style={{ padding: '0.85rem 1rem' }}>Product / SKU</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Warehouse</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>On Hand</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Reserved</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Available</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Avg Unit Cost</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Stock Valuation</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'center' }}>Reorder Status</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      Loading inventory records...
                    </td>
                  </tr>
                ) : filteredBalances.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No inventory balances found. Click "Post Opening Stock" to initialize stock.
                    </td>
                  </tr>
                ) : (
                  filteredBalances.map((b) => {
                    const isLow = parseFloat(b.qty_available) <= parseFloat(b.reorder_point)
                    const isZero = parseFloat(b.qty_available) <= 0
                    return (
                      <tr
                        key={`${b.product_id}-${b.warehouse_id}`}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          transition: 'background-color 0.15s ease',
                        }}
                      >
                        <td style={{ padding: '0.85rem 1rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{b.product_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                            {b.product_sku} &bull; {b.uom}
                          </div>
                        </td>
                        <td style={{ padding: '0.85rem 1rem' }}>
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(99, 102, 241, 0.1)',
                              color: '#a5b4fc',
                              fontSize: '0.8rem',
                              fontWeight: 500,
                            }}
                          >
                            {b.warehouse_code}
                          </span>
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                          {parseFloat(b.qty_on_hand).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                          {parseFloat(b.qty_reserved) > 0 ? (
                            <span
                              style={{
                                color: '#f59e0b',
                                backgroundColor: 'rgba(245, 158, 11, 0.12)',
                                padding: '0.2rem 0.45rem',
                                borderRadius: '4px',
                                fontWeight: 600,
                              }}
                            >
                              {parseFloat(b.qty_reserved).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-dim)' }}>0.00</span>
                          )}
                        </td>
                        <td
                          style={{
                            padding: '0.85rem 1rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: isZero ? '#ef4444' : isLow ? '#f59e0b' : '#10b981',
                          }}
                        >
                          {parseFloat(b.qty_available).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          ₱{parseFloat(b.avg_unit_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 700, color: '#f8fafc' }}>
                          ₱{parseFloat(b.total_stock_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'center' }}>
                          {isLow ? (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.3rem',
                                padding: '0.2rem 0.5rem',
                                borderRadius: '999px',
                                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                                color: '#ef4444',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                              }}
                            >
                              <TrendingDown size={12} /> Low Stock (Min {parseFloat(b.reorder_point)})
                            </span>
                          ) : (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.3rem',
                                padding: '0.2rem 0.5rem',
                                borderRadius: '999px',
                                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                color: '#10b981',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                              }}
                            >
                              <CheckCircle2 size={12} /> Normal
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Movement Ledger */}
      {activeTab === 'ledger' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderBottom: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  <th style={{ padding: '0.85rem 1rem' }}>Timestamp</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Product</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Warehouse</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Txn Type</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Quantity</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Unit Cost</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Total Cost</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>On-Hand After</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Source / Notes</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={9} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      Loading ledger transactions...
                    </td>
                  </tr>
                ) : transactions.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No ledger transactions found yet.
                    </td>
                  </tr>
                ) : (
                  transactions.map((t) => {
                    const isPositive = parseFloat(t.quantity) >= 0
                    const isReservation = t.txn_type.startsWith('reservation')
                    return (
                      <tr
                        key={t.id}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                      >
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--text-dim)', fontSize: '0.8rem' }}>
                          {new Date(t.created_at).toLocaleString()}
                        </td>
                        <td style={{ padding: '0.85rem 1rem' }}>
                          <div style={{ fontWeight: 600 }}>{t.product_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                            {t.product_sku}
                          </div>
                        </td>
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--text-muted)' }}>
                          {t.warehouse_name}
                        </td>
                        <td style={{ padding: '0.85rem 1rem' }}>
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              backgroundColor: isReservation
                                ? 'rgba(245, 158, 11, 0.15)'
                                : t.txn_type === 'opening_balance'
                                ? 'rgba(99, 102, 241, 0.15)'
                                : 'rgba(16, 185, 129, 0.15)',
                              color: isReservation ? '#f59e0b' : t.txn_type === 'opening_balance' ? '#a5b4fc' : '#34d399',
                            }}
                          >
                            {t.txn_type.replace('_', ' ')}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: '0.85rem 1rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: isPositive ? '#10b981' : '#ef4444',
                          }}
                        >
                          {isPositive ? `+${t.quantity}` : t.quantity}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          ₱{parseFloat(t.unit_cost).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          ₱{parseFloat(t.total_cost).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                          {parseFloat(t.qty_on_hand_after).toFixed(2)}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--text-dim)', fontSize: '0.8rem' }}>
                          {t.source_type} {t.source_id ? `#${t.source_id}` : ''} {t.notes ? `(${t.notes})` : ''}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Warehouses */}
      {activeTab === 'warehouses' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {warehouses.map((wh) => (
            <div
              key={wh.id}
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '12px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontWeight: 800,
                      backgroundColor: 'rgba(99, 102, 241, 0.15)',
                      color: '#a5b4fc',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '6px',
                    }}
                  >
                    {wh.code}
                  </span>
                  <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-main)' }}>
                    {wh.name}
                  </div>
                </div>
                {wh.is_default && (
                  <span
                    style={{
                      padding: '0.2rem 0.5rem',
                      borderRadius: '999px',
                      backgroundColor: 'rgba(16, 185, 129, 0.15)',
                      color: '#10b981',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                    }}
                  >
                    Default
                  </span>
                )}
              </div>

              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                {wh.address || 'No physical address specified'}
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingTop: '0.75rem',
                  borderTop: '1px solid var(--border-subtle)',
                }}
              >
                <span
                  style={{
                    fontSize: '0.8rem',
                    color: wh.is_active ? '#10b981' : '#ef4444',
                    fontWeight: 600,
                  }}
                >
                  &bull; {wh.is_active ? 'Active' : 'Inactive'}
                </span>

                <button
                  onClick={() => {
                    setEditingWarehouse(wh)
                    setWhCode(wh.code)
                    setWhName(wh.name)
                    setWhAddress(wh.address || '')
                    setWhIsDefault(wh.is_default)
                    setWhIsActive(wh.is_active)
                    setIsWarehouseModalOpen(true)
                  }}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-main)',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  Edit
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab: Reconciliation */}
      {activeTab === 'reconciliation' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              padding: '1.25rem',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <ShieldCheck size={28} color="#10b981" />
              <div>
                <div style={{ fontWeight: 800, color: '#34d399', fontSize: '1.1rem' }}>
                  Truth Ledger Integrity Check
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Compares sum(&Delta; quantity) in append-only transactions against cached inventory balances.
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '1.5rem' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                  Total Checked
                </div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#f8fafc' }}>
                  {reconciliation?.total_checked || 0}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                  Reconciled
                </div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#10b981' }}>
                  {reconciliation?.total_reconciled || 0}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                  Discrepancies
                </div>
                <div
                  style={{
                    fontSize: '1.25rem',
                    fontWeight: 800,
                    color: (reconciliation?.total_discrepancies || 0) > 0 ? '#ef4444' : '#10b981',
                  }}
                >
                  {reconciliation?.total_discrepancies || 0}
                </div>
              </div>
            </div>
          </div>

          <div
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderBottom: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  <th style={{ padding: '0.85rem 1rem' }}>Product / SKU</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Warehouse</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Balance On Hand</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Ledger &Sigma; Quantity</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Variance</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'center' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {!reconciliation || reconciliation.items.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No inventory balances to reconcile.
                    </td>
                  </tr>
                ) : (
                  reconciliation.items.map((item) => (
                    <tr
                      key={`${item.product_id}-${item.warehouse_id}`}
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                    >
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <div style={{ fontWeight: 600 }}>{item.product_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                          {item.product_sku}
                        </div>
                      </td>
                      <td style={{ padding: '0.85rem 1rem', color: 'var(--text-muted)' }}>
                        {item.warehouse_name}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                        {item.balance_on_hand}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                        {item.ledger_sum_quantity}
                      </td>
                      <td
                        style={{
                          padding: '0.85rem 1rem',
                          textAlign: 'right',
                          fontWeight: 700,
                          color: parseFloat(item.quantity_variance) === 0 ? '#10b981' : '#ef4444',
                        }}
                      >
                        {item.quantity_variance}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'center' }}>
                        {item.is_reconciled ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '999px',
                              backgroundColor: 'rgba(16, 185, 129, 0.15)',
                              color: '#10b981',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}
                          >
                            MATCHED 100%
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '999px',
                              backgroundColor: 'rgba(239, 68, 68, 0.15)',
                              color: '#ef4444',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}
                          >
                            DISCREPANCY
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Post Opening Stock */}
      {isOpeningStockOpen && (
        <Modal
          title="Post Opening Inventory Stock"
          isOpen={isOpeningStockOpen}
          onClose={() => setIsOpeningStockOpen(false)}
        >
          <form onSubmit={handlePostOpeningBalances} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Target Warehouse *
              </label>
              <select
                value={openingWarehouseId}
                onChange={(e) => setOpeningWarehouseId(parseInt(e.target.value, 10))}
                required
                style={{
                  width: '100%',
                  padding: '0.6rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                }}
              >
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.code} - {w.name} {w.is_default ? '(Default)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '0.5rem',
                }}
              >
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Stock Items *</label>
                <button
                  type="button"
                  onClick={() =>
                    setOpeningItems([
                      ...openingItems,
                      { product_id: products[0]?.id || 0, quantity: '10.000', unit_cost: '100.0000' },
                    ])
                  }
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#6366f1',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  + Add Row
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {openingItems.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '2fr 1fr 1fr auto',
                      gap: '0.5rem',
                      alignItems: 'center',
                    }}
                  >
                    <select
                      value={item.product_id}
                      onChange={(e) => {
                        const updated = [...openingItems]
                        updated[idx].product_id = parseInt(e.target.value, 10)
                        setOpeningItems(updated)
                      }}
                      required
                      style={{
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-app)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-main)',
                        fontSize: '0.85rem',
                      }}
                    >
                      <option value={0} disabled>Select Product</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.sku} - {p.name}
                        </option>
                      ))}
                    </select>

                    <input
                      type="number"
                      step="0.001"
                      min="0.001"
                      placeholder="Qty"
                      value={item.quantity}
                      onChange={(e) => {
                        const updated = [...openingItems]
                        updated[idx].quantity = e.target.value
                        setOpeningItems(updated)
                      }}
                      required
                      style={{
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-app)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-main)',
                        fontSize: '0.85rem',
                      }}
                    />

                    <input
                      type="number"
                      step="0.0001"
                      min="0.0001"
                      placeholder="Unit Cost ₱"
                      value={item.unit_cost}
                      onChange={(e) => {
                        const updated = [...openingItems]
                        updated[idx].unit_cost = e.target.value
                        setOpeningItems(updated)
                      }}
                      required
                      style={{
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-app)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-main)',
                        fontSize: '0.85rem',
                      }}
                    />

                    {openingItems.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setOpeningItems(openingItems.filter((_, i) => i !== idx))}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#ef4444',
                          cursor: 'pointer',
                          padding: '0.25rem',
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button
                type="button"
                onClick={() => setIsOpeningStockOpen(false)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                style={{
                  padding: '0.5rem 1.25rem',
                  borderRadius: '6px',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  border: 'none',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Post to Ledger
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Modal: Add/Edit Warehouse */}
      {isWarehouseModalOpen && (
        <Modal
          title={editingWarehouse ? `Edit Warehouse ${editingWarehouse.code}` : 'Create New Warehouse'}
          isOpen={isWarehouseModalOpen}
          onClose={() => setIsWarehouseModalOpen(false)}
        >
          <form onSubmit={handleSaveWarehouse} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Warehouse Code *
              </label>
              <input
                type="text"
                value={whCode}
                onChange={(e) => setWhCode(e.target.value.toUpperCase())}
                placeholder="e.g. WH-CEBU-01"
                disabled={!!editingWarehouse}
                required
                style={{
                  width: '100%',
                  padding: '0.6rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Warehouse Name *
              </label>
              <input
                type="text"
                value={whName}
                onChange={(e) => setWhName(e.target.value)}
                placeholder="e.g. Cebu Central Distribution Center"
                required
                style={{
                  width: '100%',
                  padding: '0.6rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Address / Location
              </label>
              <textarea
                value={whAddress}
                onChange={(e) => setWhAddress(e.target.value)}
                placeholder="e.g. Mandaue City, Cebu"
                rows={3}
                style={{
                  width: '100%',
                  padding: '0.6rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-main)',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.25rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={whIsDefault}
                  onChange={(e) => setWhIsDefault(e.target.checked)}
                />
                Default Fulfillment Warehouse
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={whIsActive}
                  onChange={(e) => setWhIsActive(e.target.checked)}
                />
                Facility Active
              </label>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button
                type="button"
                onClick={() => setIsWarehouseModalOpen(false)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                style={{
                  padding: '0.5rem 1.25rem',
                  borderRadius: '6px',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  border: 'none',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Save Warehouse
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
export default InventoryPage
