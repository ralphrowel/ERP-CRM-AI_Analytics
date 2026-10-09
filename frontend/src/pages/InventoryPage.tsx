import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeftRight,
  Building2,
  CheckCircle2,
  Eye,
  Layers,
  Package,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  Truck,
  Warehouse as WarehouseIcon,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type InventoryBalance,
  type InventoryReconciliationOut,
  type InventoryTransaction,
  type OpeningBalanceItemPayload,
  type Shipment,
  type StockAdjustment,
  type StockAdjustmentItemCreatePayload,
  type StockTransfer,
  type StockTransferItemCreatePayload,
  type Warehouse,
  inventoryApi,
  shipmentsApi,
  stockAdjustmentsApi,
  stockTransfersApi,
  warehousesApi,
} from '../api/inventory'
import { type Product, productsApi } from '../api/products'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

type InventoryTab = 'balances' | 'ledger' | 'shipments' | 'adjustments' | 'transfers' | 'warehouses' | 'reconciliation'

export const InventoryPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<InventoryTab>('balances')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Data states
  const [balances, setBalances] = useState<InventoryBalance[]>([])
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([])
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [adjustments, setAdjustments] = useState<StockAdjustment[]>([])
  const [transfers, setTransfers] = useState<StockTransfer[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [reconciliation, setReconciliation] = useState<InventoryReconciliationOut | null>(null)

  // Filters
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number | undefined>(undefined)
  const [selectedProductId, setSelectedProductId] = useState<number | undefined>(undefined)
  const [belowReorderFilter, setBelowReorderFilter] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Modals & Details
  const [isOpeningStockOpen, setIsOpeningStockOpen] = useState(false)
  const [isWarehouseModalOpen, setIsWarehouseModalOpen] = useState(false)
  const [editingWarehouse, setEditingWarehouse] = useState<Warehouse | null>(null)
  const [selectedShipment, setSelectedShipment] = useState<Shipment | null>(null)
  const [selectedAdjustment, setSelectedAdjustment] = useState<StockAdjustment | null>(null)
  const [selectedTransfer, setSelectedTransfer] = useState<StockTransfer | null>(null)

  // Create Modals
  const [isAdjustmentModalOpen, setIsAdjustmentModalOpen] = useState(false)
  const [isTransferModalOpen, setIsTransferModalOpen] = useState(false)

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

  // Adjustment form
  const [adjWarehouseId, setAdjWarehouseId] = useState<number>(0)
  const [adjReason, setAdjReason] = useState<string>('count_correction')
  const [adjNotes, setAdjNotes] = useState('')
  const [adjItems, setAdjItems] = useState<StockAdjustmentItemCreatePayload[]>([
    { product_id: 0, quantity_change: '1.000', unit_cost: '' },
  ])

  // Transfer form
  const [transFromWarehouseId, setTransFromWarehouseId] = useState<number>(0)
  const [transToWarehouseId, setTransToWarehouseId] = useState<number>(0)
  const [transNotes, setTransNotes] = useState('')
  const [transItems, setTransItems] = useState<StockTransferItemCreatePayload[]>([
    { product_id: 0, quantity: '1.000' },
  ])

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
      if (whRes.length > 0 && !adjWarehouseId) {
        const defaultWh = whRes.find((w) => w.is_default) || whRes[0]
        setAdjWarehouseId(defaultWh.id)
      }
      if (whRes.length >= 2 && !transFromWarehouseId) {
        setTransFromWarehouseId(whRes[0].id)
        setTransToWarehouseId(whRes[1].id)
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
      } else if (activeTab === 'shipments') {
        const shipRes = await shipmentsApi.list({ warehouse_id: selectedWarehouseId })
        setShipments(shipRes)
      } else if (activeTab === 'adjustments') {
        const adjRes = await stockAdjustmentsApi.list({ warehouse_id: selectedWarehouseId })
        setAdjustments(adjRes)
      } else if (activeTab === 'transfers') {
        const transRes = await stockTransfersApi.list({ warehouse_id: selectedWarehouseId })
        setTransfers(transRes)
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

  const handlePostShipment = async (id: number) => {
    setError(null)
    try {
      await shipmentsApi.post(id)
      setSuccessMessage('Shipment posted successfully! Inventory issued and COGS calculated.')
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
      if (selectedShipment?.id === id) setSelectedShipment(null)
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleCancelShipment = async (id: number) => {
    setError(null)
    try {
      await shipmentsApi.cancel(id)
      setSuccessMessage('Shipment draft cancelled.')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
      if (selectedShipment?.id === id) setSelectedShipment(null)
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleCreateAdjustment = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!adjWarehouseId) {
      alert('Please select a warehouse.')
      return
    }
    const validItems = adjItems.filter(
      (item) => item.product_id > 0 && parseFloat(item.quantity_change.toString()) !== 0
    )
    if (validItems.length === 0) {
      alert('Please specify at least one item with non-zero quantity change.')
      return
    }

    try {
      const created = await stockAdjustmentsApi.create({
        warehouse_id: adjWarehouseId,
        reason: adjReason,
        notes: adjNotes || undefined,
        items: validItems.map((item) => ({
          product_id: item.product_id,
          quantity_change: item.quantity_change,
          unit_cost: item.unit_cost ? parseFloat(item.unit_cost.toString()) : undefined,
        })),
      })
      await stockAdjustmentsApi.post(created.id)
      setSuccessMessage(`Stock Adjustment ${created.adjustment_no || ''} posted successfully! Live balance and ledger updated.`)
      setTimeout(() => setSuccessMessage(null), 4000)
      setIsAdjustmentModalOpen(false)
      loadData()
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handlePostAdjustment = async (id: number) => {
    setError(null)
    try {
      await stockAdjustmentsApi.post(id)
      setSuccessMessage('Adjustment posted to live balances & ledger.')
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
      if (selectedAdjustment?.id === id) setSelectedAdjustment(null)
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleCancelAdjustment = async (id: number) => {
    setError(null)
    try {
      await stockAdjustmentsApi.cancel(id)
      setSuccessMessage('Adjustment draft cancelled.')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
      if (selectedAdjustment?.id === id) setSelectedAdjustment(null)
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleCreateTransfer = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!transFromWarehouseId || !transToWarehouseId) {
      alert('Please select both source and destination warehouses.')
      return
    }
    if (transFromWarehouseId === transToWarehouseId) {
      alert('Source and destination warehouses must be different.')
      return
    }
    const validItems = transItems.filter(
      (item) => item.product_id > 0 && parseFloat(item.quantity.toString()) > 0
    )
    if (validItems.length === 0) {
      alert('Please specify at least one item with quantity greater than 0.')
      return
    }

    try {
      const created = await stockTransfersApi.create({
        from_warehouse_id: transFromWarehouseId,
        to_warehouse_id: transToWarehouseId,
        notes: transNotes || undefined,
        items: validItems,
      })
      await stockTransfersApi.post(created.id)
      setSuccessMessage(`Stock Transfer ${created.transfer_no || ''} posted! Dual-movement transfer complete.`)
      setTimeout(() => setSuccessMessage(null), 4000)
      setIsTransferModalOpen(false)
      loadData()
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handlePostTransfer = async (id: number) => {
    setError(null)
    try {
      await stockTransfersApi.post(id)
      setSuccessMessage('Stock transfer posted successfully!')
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
      if (selectedTransfer?.id === id) setSelectedTransfer(null)
    } catch (err) {
      setError(err as ApiError | Error)
    }
  }

  const handleCancelTransfer = async (id: number) => {
    setError(null)
    try {
      await stockTransfersApi.cancel(id)
      setSuccessMessage('Stock transfer draft cancelled.')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
      if (selectedTransfer?.id === id) setSelectedTransfer(null)
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
          onClick={() => setActiveTab('shipments')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'shipments' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'shipments' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Truck size={17} /> Shipments ({shipments.length})
        </button>

        <button
          onClick={() => setActiveTab('adjustments')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'adjustments' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'adjustments' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <SlidersHorizontal size={17} /> Stock Adjustments
        </button>

        <button
          onClick={() => setActiveTab('transfers')}
          style={{
            background: 'none',
            border: 'none',
            padding: '0.75rem 0.25rem',
            cursor: 'pointer',
            color: activeTab === 'transfers' ? '#6366f1' : 'var(--text-muted)',
            borderBottom: activeTab === 'transfers' ? '2px solid #6366f1' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <ArrowLeftRight size={17} /> Warehouse Transfers
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

      {/* Tab: Shipments */}
      {activeTab === 'shipments' && (
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
                  <th style={{ padding: '0.85rem 1rem' }}>Shipment #</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Sales Order</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Warehouse</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Carrier / Tracking</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Total COGS</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Shipped At</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shipments.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No shipments recorded yet. Dispatch confirmed sales orders from the Sales Orders module.
                    </td>
                  </tr>
                ) : (
                  shipments.map((s) => (
                    <tr key={s.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                        {s.shipment_no || `Draft #${s.id}`}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', color: '#a5b4fc', fontWeight: 600 }}>
                        {s.sales_order_no}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span style={{ fontFamily: 'monospace', color: 'var(--text-dim)' }}>
                          {s.warehouse_code} - {s.warehouse_name}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        {s.status === 'posted' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(16, 185, 129, 0.15)',
                              color: '#34d399',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}
                          >
                            POSTED
                          </span>
                        ) : s.status === 'draft' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              color: 'var(--text-muted)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            DRAFT
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(239, 68, 68, 0.15)',
                              color: '#f87171',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            CANCELLED
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {s.carrier ? `${s.carrier} (${s.tracking_no || 'No track #'})` : '-'}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 700, color: '#34d399' }}>
                        {s.total_cogs
                          ? `₱${parseFloat(s.total_cogs).toLocaleString('en-US', {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}`
                          : '-'}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        {s.shipped_at ? new Date(s.shipped_at).toLocaleString() : new Date(s.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.4rem' }}>
                          <button
                            onClick={() => setSelectedShipment(s)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                              padding: '0.35rem 0.65rem',
                              borderRadius: '6px',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)',
                              border: '1px solid var(--border-subtle)',
                              color: 'var(--text-main)',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                            }}
                            title="View Items & Details"
                          >
                            <Eye size={12} /> View
                          </button>
                          {s.status === 'draft' && (
                            <>
                              <button
                                onClick={() => handlePostShipment(s.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.65rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#0284c7',
                                  border: 'none',
                                  color: '#fff',
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                                title="Post Shipment & Issue Stock"
                              >
                                <CheckCircle2 size={12} /> Post
                              </button>
                              <button
                                onClick={() => handleCancelShipment(s.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                  border: '1px solid rgba(239, 68, 68, 0.3)',
                                  color: '#ef4444',
                                  fontSize: '0.75rem',
                                  cursor: 'pointer',
                                }}
                                title="Cancel Draft Shipment"
                              >
                                <XCircle size={12} /> Cancel
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Stock Adjustments */}
      {activeTab === 'adjustments' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => {
                if (warehouses.length > 0 && !adjWarehouseId) setAdjWarehouseId(warehouses[0].id)
                setAdjReason('count_correction')
                setAdjNotes('')
                setAdjItems([{ product_id: products[0]?.id || 0, quantity_change: '1.000', unit_cost: '' }])
                setIsAdjustmentModalOpen(true)
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
              <Plus size={16} /> New Stock Adjustment
            </button>
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
                  <th style={{ padding: '0.85rem 1rem' }}>Adjustment #</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Warehouse</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Reason</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Items</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Notes</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Date</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {adjustments.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No stock adjustments recorded. Click "New Stock Adjustment" to record count corrections, damages, or losses.
                    </td>
                  </tr>
                ) : (
                  adjustments.map((adj) => (
                    <tr key={adj.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                        {adj.adjustment_no || `Draft #${adj.id}`}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span style={{ fontFamily: 'monospace', color: 'var(--text-dim)' }}>
                          {adj.warehouse_code} - {adj.warehouse_name}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span
                          style={{
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(99, 102, 241, 0.1)',
                            color: '#a5b4fc',
                            fontSize: '0.75rem',
                            textTransform: 'capitalize',
                          }}
                        >
                          {adj.reason.replace('_', ' ')}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        {adj.status === 'posted' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(16, 185, 129, 0.15)',
                              color: '#34d399',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}
                          >
                            POSTED
                          </span>
                        ) : adj.status === 'draft' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              color: 'var(--text-muted)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            DRAFT
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(239, 68, 68, 0.15)',
                              color: '#f87171',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            CANCELLED
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        {adj.items.length} item{adj.items.length > 1 ? 's' : ''}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {adj.notes || '-'}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        {adj.posted_at ? new Date(adj.posted_at).toLocaleString() : new Date(adj.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.4rem' }}>
                          <button
                            onClick={() => setSelectedAdjustment(adj)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                              padding: '0.35rem 0.65rem',
                              borderRadius: '6px',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)',
                              border: '1px solid var(--border-subtle)',
                              color: 'var(--text-main)',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                            }}
                            title="View Items"
                          >
                            <Eye size={12} /> View
                          </button>
                          {adj.status === 'draft' && (
                            <>
                              <button
                                onClick={() => handlePostAdjustment(adj.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.65rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#10b981',
                                  border: 'none',
                                  color: '#fff',
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                <CheckCircle2 size={12} /> Post
                              </button>
                              <button
                                onClick={() => handleCancelAdjustment(adj.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                  border: '1px solid rgba(239, 68, 68, 0.3)',
                                  color: '#ef4444',
                                  fontSize: '0.75rem',
                                  cursor: 'pointer',
                                }}
                              >
                                <XCircle size={12} /> Cancel
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Warehouse Transfers */}
      {activeTab === 'transfers' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => {
                if (warehouses.length >= 2) {
                  setTransFromWarehouseId(warehouses[0].id)
                  setTransToWarehouseId(warehouses[1].id)
                }
                setTransNotes('')
                setTransItems([{ product_id: products[0]?.id || 0, quantity: '1.000' }])
                setIsTransferModalOpen(true)
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
              <Plus size={16} /> New Stock Transfer
            </button>
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
                  <th style={{ padding: '0.85rem 1rem' }}>Transfer #</th>
                  <th style={{ padding: '0.85rem 1rem' }}>From Facility</th>
                  <th style={{ padding: '0.85rem 1rem' }}>To Facility</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Items</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Notes</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Date</th>
                  <th style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {transfers.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No warehouse transfers recorded yet. Click "New Stock Transfer" to transfer inventory between facilities.
                    </td>
                  </tr>
                ) : (
                  transfers.map((t) => (
                    <tr key={t.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>
                        {t.transfer_no || `Draft #${t.id}`}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span style={{ fontFamily: 'monospace', color: 'var(--text-dim)' }}>
                          {t.from_warehouse_code} - {t.from_warehouse_name}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span style={{ fontFamily: 'monospace', color: '#a5b4fc' }}>
                          {t.to_warehouse_code} - {t.to_warehouse_name}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        {t.status === 'posted' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(16, 185, 129, 0.15)',
                              color: '#34d399',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                            }}
                          >
                            POSTED
                          </span>
                        ) : t.status === 'draft' ? (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              color: 'var(--text-muted)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            DRAFT
                          </span>
                        ) : (
                          <span
                            style={{
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(239, 68, 68, 0.15)',
                              color: '#f87171',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            CANCELLED
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        {t.items.length} item{t.items.length > 1 ? 's' : ''}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {t.notes || '-'}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        {t.posted_at ? new Date(t.posted_at).toLocaleString() : new Date(t.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.4rem' }}>
                          <button
                            onClick={() => setSelectedTransfer(t)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                              padding: '0.35rem 0.65rem',
                              borderRadius: '6px',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)',
                              border: '1px solid var(--border-subtle)',
                              color: 'var(--text-main)',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                            }}
                            title="View Items"
                          >
                            <Eye size={12} /> View
                          </button>
                          {t.status === 'draft' && (
                            <>
                              <button
                                onClick={() => handlePostTransfer(t.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.65rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#10b981',
                                  border: 'none',
                                  color: '#fff',
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                <CheckCircle2 size={12} /> Post
                              </button>
                              <button
                                onClick={() => handleCancelTransfer(t.id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  padding: '0.35rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                  border: '1px solid rgba(239, 68, 68, 0.3)',
                                  color: '#ef4444',
                                  fontSize: '0.75rem',
                                  cursor: 'pointer',
                                }}
                              >
                                <XCircle size={12} /> Cancel
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
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

      {/* Modal: View Shipment */}
      {selectedShipment && (
        <Modal
          title={`Shipment Details: ${selectedShipment.shipment_no || `Draft #${selectedShipment.id}`}`}
          isOpen={!!selectedShipment}
          onClose={() => setSelectedShipment(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '0.75rem',
                padding: '0.85rem',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Order Ref</span>
                <strong style={{ color: '#a5b4fc', fontFamily: 'monospace' }}>{selectedShipment.sales_order_no}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Warehouse</span>
                <strong>
                  {selectedShipment.warehouse_code} - {selectedShipment.warehouse_name}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Carrier / Tracking</span>
                <span>{selectedShipment.carrier || '-'} ({selectedShipment.tracking_no || 'None'})</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Total COGS</span>
                <strong style={{ color: '#34d399' }}>
                  {selectedShipment.total_cogs ? `₱${parseFloat(selectedShipment.total_cogs).toFixed(2)}` : 'Pending posting'}
                </strong>
              </div>
            </div>

            <div>
              <strong style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem' }}>Shipped Items & COGS</strong>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '0.5rem' }}>Item</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Qty</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>WAC Unit Cost</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>COGS</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedShipment.items.map((item) => (
                    <tr key={item.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <td style={{ padding: '0.5rem' }}>
                        <div style={{ fontWeight: 600 }}>{item.product_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                          {item.product_sku} &bull; UOM: {item.product_uom}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600 }}>{item.quantity}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                        {item.unit_cost ? `₱${parseFloat(item.unit_cost).toFixed(2)}` : '-'}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 600, color: '#34d399' }}>
                        {item.cogs_amount ? `₱${parseFloat(item.cogs_amount).toFixed(2)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSelectedShipment(null)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
              {selectedShipment.status === 'draft' && (
                <button
                  type="button"
                  onClick={() => handlePostShipment(selectedShipment.id)}
                  style={{
                    padding: '0.5rem 1.25rem',
                    borderRadius: '6px',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    border: 'none',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Post Shipment
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: View Adjustment */}
      {selectedAdjustment && (
        <Modal
          title={`Stock Adjustment: ${selectedAdjustment.adjustment_no || `Draft #${selectedAdjustment.id}`}`}
          isOpen={!!selectedAdjustment}
          onClose={() => setSelectedAdjustment(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '0.75rem',
                padding: '0.85rem',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Warehouse</span>
                <strong>
                  {selectedAdjustment.warehouse_code} - {selectedAdjustment.warehouse_name}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Reason</span>
                <span style={{ textTransform: 'capitalize' }}>{selectedAdjustment.reason.replace('_', ' ')}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Notes</span>
                <span>{selectedAdjustment.notes || 'None'}</span>
              </div>
            </div>

            <div>
              <strong style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem' }}>Adjusted Items</strong>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '0.5rem' }}>Item</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Quantity Change</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Unit Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedAdjustment.items.map((item) => {
                    const isPositive = parseFloat(item.quantity_change) > 0
                    return (
                      <tr key={item.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ fontWeight: 600 }}>{item.product_name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                            {item.product_sku} &bull; UOM: {item.product_uom}
                          </div>
                        </td>
                        <td
                          style={{
                            padding: '0.5rem',
                            textAlign: 'right',
                            fontWeight: 700,
                            color: isPositive ? '#34d399' : '#f87171',
                          }}
                        >
                          {isPositive ? `+${item.quantity_change}` : item.quantity_change}
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                          {item.unit_cost ? `₱${parseFloat(item.unit_cost).toFixed(2)}` : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSelectedAdjustment(null)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: View Transfer */}
      {selectedTransfer && (
        <Modal
          title={`Stock Transfer: ${selectedTransfer.transfer_no || `Draft #${selectedTransfer.id}`}`}
          isOpen={!!selectedTransfer}
          onClose={() => setSelectedTransfer(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '0.75rem',
                padding: '0.85rem',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>From Facility</span>
                <strong>
                  {selectedTransfer.from_warehouse_code} - {selectedTransfer.from_warehouse_name}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>To Facility</span>
                <strong style={{ color: '#a5b4fc' }}>
                  {selectedTransfer.to_warehouse_code} - {selectedTransfer.to_warehouse_name}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Notes</span>
                <span>{selectedTransfer.notes || 'None'}</span>
              </div>
            </div>

            <div>
              <strong style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem' }}>Transferred Items</strong>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '0.5rem' }}>Item</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Transfer Quantity</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Unit Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedTransfer.items.map((item) => (
                    <tr key={item.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <td style={{ padding: '0.5rem' }}>
                        <div style={{ fontWeight: 600 }}>{item.product_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                          {item.product_sku} &bull; UOM: {item.product_uom}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 700, color: '#38bdf8' }}>
                        {item.quantity}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-muted)' }}>
                        {item.unit_cost ? `₱${parseFloat(item.unit_cost).toFixed(2)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSelectedTransfer(null)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: Create Stock Adjustment */}
      {isAdjustmentModalOpen && (
        <Modal
          title="New Stock Adjustment"
          isOpen={isAdjustmentModalOpen}
          onClose={() => setIsAdjustmentModalOpen(false)}
        >
          <form onSubmit={handleCreateAdjustment} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Warehouse *
                </label>
                <select
                  value={adjWarehouseId}
                  onChange={(e) => setAdjWarehouseId(parseInt(e.target.value, 10))}
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
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Adjustment Reason *
                </label>
                <select
                  value={adjReason}
                  onChange={(e) => setAdjReason(e.target.value)}
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
                  <option value="count_correction">Count Correction (Stocktake)</option>
                  <option value="damage">Damage (Loss / Disposal)</option>
                  <option value="loss">Loss / Theft / Shrinkage</option>
                  <option value="found">Found / Discovered Inventory</option>
                  <option value="expired">Expired Stock</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Reason Details / Notes
              </label>
              <input
                type="text"
                value={adjNotes}
                onChange={(e) => setAdjNotes(e.target.value)}
                placeholder="e.g. Monthly physical inventory count audit"
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Items to Adjust *</label>
                <button
                  type="button"
                  onClick={() =>
                    setAdjItems([...adjItems, { product_id: products[0]?.id || 0, quantity_change: '1.000', unit_cost: '' }])
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
                {adjItems.map((item, idx) => (
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
                        const updated = [...adjItems]
                        updated[idx].product_id = parseInt(e.target.value, 10)
                        setAdjItems(updated)
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
                      step="any"
                      placeholder="Qty (+ or -)"
                      value={item.quantity_change}
                      onChange={(e) => {
                        const updated = [...adjItems]
                        updated[idx].quantity_change = e.target.value
                        setAdjItems(updated)
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
                      step="any"
                      placeholder="Cost ₱ (if add)"
                      value={item.unit_cost ?? ''}
                      onChange={(e) => {
                        const updated = [...adjItems]
                        updated[idx].unit_cost = e.target.value
                        setAdjItems(updated)
                      }}
                      style={{
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-app)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-main)',
                        fontSize: '0.85rem',
                      }}
                    />

                    {adjItems.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setAdjItems(adjItems.filter((_, i) => i !== idx))}
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
              <span style={{ display: 'block', marginTop: '0.4rem', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                Tip: Enter negative quantity (e.g. -5) for shrinkage/damage, or positive quantity for found inventory.
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setIsAdjustmentModalOpen(false)}
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
                Post Adjustment
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Modal: Create Stock Transfer */}
      {isTransferModalOpen && (
        <Modal
          title="New Warehouse Stock Transfer"
          isOpen={isTransferModalOpen}
          onClose={() => setIsTransferModalOpen(false)}
        >
          <form onSubmit={handleCreateTransfer} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Source Facility (From) *
                </label>
                <select
                  value={transFromWarehouseId}
                  onChange={(e) => setTransFromWarehouseId(parseInt(e.target.value, 10))}
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
                      {w.code} - {w.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Destination Facility (To) *
                </label>
                <select
                  value={transToWarehouseId}
                  onChange={(e) => setTransToWarehouseId(parseInt(e.target.value, 10))}
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
                      {w.code} - {w.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
                Transfer Notes / Reason
              </label>
              <input
                type="text"
                value={transNotes}
                onChange={(e) => setTransNotes(e.target.value)}
                placeholder="e.g. Inter-branch replenishment"
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Items to Transfer *</label>
                <button
                  type="button"
                  onClick={() =>
                    setTransItems([...transItems, { product_id: products[0]?.id || 0, quantity: '1.000' }])
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
                {transItems.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '3fr 1fr auto',
                      gap: '0.5rem',
                      alignItems: 'center',
                    }}
                  >
                    <select
                      value={item.product_id}
                      onChange={(e) => {
                        const updated = [...transItems]
                        updated[idx].product_id = parseInt(e.target.value, 10)
                        setTransItems(updated)
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
                      step="any"
                      min="0.001"
                      placeholder="Quantity"
                      value={item.quantity}
                      onChange={(e) => {
                        const updated = [...transItems]
                        updated[idx].quantity = e.target.value
                        setTransItems(updated)
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

                    {transItems.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setTransItems(transItems.filter((_, i) => i !== idx))}
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

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setIsTransferModalOpen(false)}
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
                Post Transfer
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
export default InventoryPage
