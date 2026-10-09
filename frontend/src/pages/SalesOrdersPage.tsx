import React, { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle,
  FileCheck,
  FileText,
  History,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Truck,
  XCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { type Customer, customersApi } from '../api/customers'
import { type Warehouse, shipmentsApi, warehousesApi } from '../api/inventory'
import { type Product, productsApi } from '../api/products'
import {
  type SalesOrder,
  salesApi,
  type SalesOrderCreatePayload,
  type SalesOrderStatus,
  type TaxRate,
} from '../api/sales'
import { ConflictAlert } from '../components/ConflictAlert'
import { LineItemsEditor } from '../components/LineItemsEditor'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'
import { StatusHistoryTimeline } from '../components/StatusHistoryTimeline'

export const SalesOrdersPage: React.FC = () => {
  const [orders, setOrders] = useState<SalesOrder[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  // Master data
  const [customers, setCustomers] = useState<Customer[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [taxRates, setTaxRates] = useState<TaxRate[]>([])
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])

  // Notifications
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isCancelOpen, setIsCancelOpen] = useState(false)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isFulfillOpen, setIsFulfillOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<SalesOrder | null>(null)
  const [cancelReason, setCancelReason] = useState('')

  // Fulfillment form state
  const [fulfillCarrier, setFulfillCarrier] = useState('')
  const [fulfillTracking, setFulfillTracking] = useState('')
  const [fulfillNotes, setFulfillNotes] = useState('')
  const [fulfillQuantities, setFulfillQuantities] = useState<Record<number, string>>({})
  const [isFulfilling, setIsFulfilling] = useState(false)

  // Create form state
  const [formData, setFormData] = useState<SalesOrderCreatePayload>({
    customer_id: 0,
    warehouse_id: undefined,
    order_date: new Date().toISOString().split('T')[0],
    requested_delivery_date: '',
    notes: '',
    items: [],
  })

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [ordersRes, custRes, prodRes, trRes, whRes] = await Promise.all([
        salesApi.listSalesOrders({ page, page_size: pageSize, status: statusFilter || undefined }),
        customersApi.list({ page: 1, page_size: 100 }),
        productsApi.list({ page: 1, page_size: 100 }),
        salesApi.listTaxRates(),
        warehousesApi.list(true),
      ])
      setOrders(ordersRes.items)
      setTotal(ordersRes.total)
      setCustomers(custRes.items)
      setProducts(prodRes.items)
      setTaxRates(trRes)
      setWarehouses(whRes)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to load sales orders data'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, statusFilter])

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.customer_id) {
      setGeneralError(new Error('Please select a customer.'))
      return
    }
    if (formData.items.length === 0) {
      setGeneralError(new Error('Sales order must contain at least one line item.'))
      return
    }

    try {
      const created = await salesApi.createSalesOrder(formData)
      setIsCreateOpen(false)
      setFormData({
        customer_id: 0,
        order_date: new Date().toISOString().split('T')[0],
        requested_delivery_date: '',
        notes: '',
        items: [],
      })
      setSuccessMessage(`Sales Order ${created.order_no} created successfully`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create sales order'))
      }
    }
  }

  const handleConfirm = async (so: SalesOrder) => {
    setGeneralError(null)
    try {
      await salesApi.confirmSalesOrder(so.id)
      setSuccessMessage(`Order ${so.order_no} confirmed! Customer address & payment snapshots locked.`)
      setTimeout(() => setSuccessMessage(null), 4500)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) setConflictError('Conflict: Order was modified concurrently.')
        else setGeneralError(err)
      }
    }
  }

  const handleHold = async (so: SalesOrder) => {
    try {
      await salesApi.holdSalesOrder(so.id, 'Commercial hold')
      setSuccessMessage(`Order ${so.order_no} put on hold`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleRelease = async (so: SalesOrder) => {
    try {
      await salesApi.releaseSalesOrder(so.id)
      setSuccessMessage(`Order ${so.order_no} released back to confirmed`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleCancelConfirm = async () => {
    if (!selectedOrder) return
    try {
      await salesApi.cancelSalesOrder(selectedOrder.id, cancelReason)
      setIsCancelOpen(false)
      setSelectedOrder(null)
      setSuccessMessage(`Order cancelled`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleCreateInvoice = async (so: SalesOrder) => {
    try {
      await salesApi.createInvoiceFromOrder(so.id)
      setSuccessMessage(`Draft invoice created for Sales Order ${so.order_no}! You can review and issue it in Invoices.`)
      setTimeout(() => setSuccessMessage(null), 5000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to create invoice from sales order'))
      }
    }
  }

  const openFulfillModal = (so: SalesOrder) => {
    setSelectedOrder(so)
    setFulfillCarrier('')
    setFulfillTracking('')
    setFulfillNotes('')
    const initialQty: Record<number, string> = {}
    so.items.forEach((item) => {
      const remaining = Math.max(0, parseFloat(item.quantity) - parseFloat(item.quantity_shipped || '0'))
      initialQty[item.id!] = remaining.toString()
    })
    setFulfillQuantities(initialQty)
    setIsFulfillOpen(true)
  }

  const handleFulfillSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrder) return
    setIsFulfilling(true)
    setGeneralError(null)

    const itemsToShip = selectedOrder.items
      .map((item) => {
        const qty = parseFloat(fulfillQuantities[item.id!] || '0')
        return {
          sales_order_item_id: item.id!,
          product_id: item.product_id!,
          quantity: qty.toString(),
        }
      })
      .filter((item) => parseFloat(item.quantity) > 0)

    if (itemsToShip.length === 0) {
      setGeneralError(new Error('Please specify a quantity greater than 0 for at least one item.'))
      setIsFulfilling(false)
      return
    }

    try {
      const shipment = await shipmentsApi.create({
        sales_order_id: selectedOrder.id,
        carrier: fulfillCarrier || undefined,
        tracking_no: fulfillTracking || undefined,
        notes: fulfillNotes || undefined,
        items: itemsToShip.map((item) => ({
          sales_order_item_id: item.sales_order_item_id,
          quantity: item.quantity,
        })),
      })

      await shipmentsApi.post(shipment.id)
      setIsFulfillOpen(false)
      setSelectedOrder(null)
      setSuccessMessage(`Shipment ${shipment.shipment_no} created and posted! Inventory issued & COGS recorded.`)
      setTimeout(() => setSuccessMessage(null), 5000)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err)
      } else {
        setGeneralError(new Error('Failed to fulfill order'))
      }
    } finally {
      setIsFulfilling(false)
    }
  }

  const formatCurrency = (val: string) =>
    new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(parseFloat(val || '0'))

  const getStatusBadge = (status: SalesOrderStatus) => {
    switch (status) {
      case 'draft':
        return <span className="badge badge-subtle">Draft</span>
      case 'pending_approval':
        return <span className="badge badge-amber">Pending Approval</span>
      case 'confirmed':
        return <span className="badge badge-indigo">Confirmed</span>
      case 'partially_shipped':
        return <span className="badge badge-amber">Partially Shipped</span>
      case 'shipped':
        return <span className="badge badge-emerald">Shipped</span>
      case 'on_hold':
        return <span className="badge badge-amber">On Hold</span>
      case 'completed':
        return <span className="badge badge-emerald">Completed</span>
      case 'cancelled':
        return <span className="badge badge-rose">Cancelled</span>
      default:
        return <span className="badge badge-cyan">{status}</span>
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f8fafc' }}>
            Sales Orders (Commercial Commitment)
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Legally binding purchase contracts, credit limit protection, address snapshot immutability, and fulfillment readiness.
          </p>
        </div>

        <button
          className="btn btn-primary"
          onClick={() => {
            setFormData({
              customer_id: customers[0]?.id || 0,
              order_date: new Date().toISOString().split('T')[0],
              requested_delivery_date: '',
              notes: '',
              items: [],
            })
            setIsCreateOpen(true)
          }}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <Plus size={16} /> New Sales Order
        </button>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="badge badge-emerald" style={{ padding: '0.75rem 1rem', fontSize: '0.875rem' }}>
          <CheckCircle size={16} /> {successMessage}
        </div>
      )}

      {conflictError && <ConflictAlert message={conflictError} onReload={() => loadData()} />}
      {generalError && <ProblemAlert error={generalError} onDismiss={() => setGeneralError(null)} />}

      {/* Filter Bar */}
      <div
        className="card"
        style={{
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          backgroundColor: 'var(--bg-surface)',
        }}
      >
        <select
          className="input-field"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
          style={{ minWidth: '150px' }}
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="confirmed">Confirmed</option>
          <option value="on_hold">On Hold</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <button onClick={() => loadData()} className="btn btn-secondary" title="Refresh">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Orders Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Order #
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Customer Account
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Order Date
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Warehouse
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Status
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', textAlign: 'right' }}>
                Grand Total (₱)
              </th>
              <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', textAlign: 'right' }}>
                Lifecycle Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  <RefreshCw className="animate-spin" size={20} style={{ margin: '0 auto 0.5rem' }} />
                  <div>Loading sales orders...</div>
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
                  No sales orders found.
                </td>
              </tr>
            ) : (
              orders.map((so) => {
                const customer = customers.find((c) => c.id === so.customer_id)
                return (
                  <tr key={so.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontSize: '0.85rem', color: '#a5b4fc', fontWeight: 600 }}>
                      <span
                        onClick={() => {
                          setSelectedOrder(so)
                          setIsDetailsOpen(true)
                        }}
                        style={{ cursor: 'pointer', textDecoration: 'underline' }}
                        title="Click to view snapshots & details"
                      >
                        {so.order_no}
                      </span>
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: '#f8fafc' }}>
                        {customer ? customer.name : `Customer #${so.customer_id}`}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                        {so.items.length} line item{so.items.length > 1 ? 's' : ''}
                      </div>
                    </td>
                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                      {so.order_date}
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span
                        style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(99, 102, 241, 0.1)',
                          color: '#a5b4fc',
                          fontSize: '0.75rem',
                          fontFamily: 'monospace',
                        }}
                      >
                        {so.warehouse?.code || 'DEFAULT'}
                      </span>
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>{getStatusBadge(so.status)}</td>
                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: '0.9rem', color: '#38bdf8' }}>
                      {formatCurrency(so.grand_total)}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.35rem' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem' }}
                          title="Audit Trail"
                          onClick={() => {
                            setSelectedOrder(so)
                            setIsHistoryOpen(true)
                          }}
                        >
                          <History size={13} />
                        </button>

                        {so.status === 'draft' && (
                          <>
                            <button
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem', backgroundColor: 'var(--emerald-600)', borderColor: 'var(--emerald-600)' }}
                              onClick={() => handleConfirm(so)}
                              title="Confirm order & verify credit limit"
                            >
                              Confirm
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                              onClick={() => {
                                setSelectedOrder(so)
                                setCancelReason('')
                                setIsCancelOpen(true)
                              }}
                              title="Cancel Order"
                            >
                              <XCircle size={13} />
                            </button>
                          </>
                        )}

                        {(so.status === 'confirmed' || so.status === 'partially_shipped') && (
                          <>
                            <button
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem', backgroundColor: '#0284c7', borderColor: '#0284c7' }}
                              onClick={() => openFulfillModal(so)}
                              title="Create and Post Shipment"
                            >
                              <Truck size={12} /> Ship
                            </button>
                            <button
                              className="btn btn-primary"
                              style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem' }}
                              onClick={() => handleCreateInvoice(so)}
                              title="Create Invoice from this Order"
                            >
                              <FileText size={12} /> Invoice
                            </button>
                            {so.status === 'confirmed' && (
                              <>
                                <button
                                  className="btn btn-secondary"
                                  style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem', color: 'var(--amber-400)' }}
                                  onClick={() => handleHold(so)}
                                  title="Put on hold"
                                >
                                  <Pause size={12} /> Hold
                                </button>
                                <button
                                  className="btn btn-secondary"
                                  style={{ padding: '0.35rem 0.5rem', fontSize: '0.75rem', color: 'var(--rose-400)' }}
                                  onClick={() => {
                                    setSelectedOrder(so)
                                    setCancelReason('')
                                    setIsCancelOpen(true)
                                  }}
                                  title="Cancel Order"
                                >
                                  <XCircle size={13} />
                                </button>
                              </>
                            )}
                          </>
                        )}

                        {so.status === 'shipped' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.55rem', fontSize: '0.75rem' }}
                            onClick={() => handleCreateInvoice(so)}
                            title="Create Invoice from this Order"
                          >
                            <FileText size={12} /> Invoice
                          </button>
                        )}

                        {so.status === 'on_hold' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
                            onClick={() => handleRelease(so)}
                            title="Release hold"
                          >
                            <Play size={12} /> Release
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>

        {/* Pagination footer */}
        <div
          style={{
            padding: '0.75rem 1rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.85rem',
            color: 'var(--text-dim)',
          }}
        >
          <div>
            Showing {orders.length > 0 ? (page - 1) * pageSize + 1 : 0} to {Math.min(page * pageSize, total)} of {total} orders
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
            >
              Previous
            </button>
            <button
              className="btn btn-secondary"
              disabled={page * pageSize >= total}
              onClick={() => setPage(page + 1)}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Modal: Create Sales Order */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Sales Order">
        <form onSubmit={handleCreateOrder} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '1rem' }}>
            <div>
              <label className="form-label">Customer Account *</label>
              <select
                required
                className="input-field"
                value={formData.customer_id}
                onChange={(e) => setFormData({ ...formData, customer_id: Number(e.target.value) })}
              >
                <option value="">-- Select Customer --</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.customer_no}) - {c.status}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Fulfillment Warehouse</label>
              <select
                className="input-field"
                value={formData.warehouse_id || ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    warehouse_id: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              >
                <option value="">Default Warehouse</option>
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.code} - {w.name} {w.is_default ? '(Default)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Order Date *</label>
              <input
                type="date"
                required
                className="input-field"
                value={formData.order_date || ''}
                onChange={(e) => setFormData({ ...formData, order_date: e.target.value })}
              />
            </div>
            <div>
              <label className="form-label">Requested Delivery Date</label>
              <input
                type="date"
                className="input-field"
                value={formData.requested_delivery_date || ''}
                onChange={(e) => setFormData({ ...formData, requested_delivery_date: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="form-label">Order Line Items</label>
            <LineItemsEditor
              items={formData.items}
              onChange={(newItems) => setFormData({ ...formData, items: newItems })}
              products={products}
              taxRates={taxRates}
            />
          </div>

          <div>
            <label className="form-label">Delivery Notes & Instructions</label>
            <textarea
              rows={2}
              className="input-field"
              placeholder="Delivery instructions, gate pass requirements..."
              value={formData.notes || ''}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <FileCheck size={16} /> Save Sales Order
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Order Details & Address Snapshots */}
      <Modal isOpen={isDetailsOpen} onClose={() => setIsDetailsOpen(false)} title={`Order Snapshots: ${selectedOrder?.order_no}`}>
        {selectedOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div style={{ padding: '0.85rem', borderRadius: '8px', backgroundColor: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#a5b4fc', marginBottom: '0.35rem' }}>
                  Billing Address Snapshot
                </strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {selectedOrder.billing_address_snapshot || 'Pending confirmation'}
                </span>
              </div>
              <div style={{ padding: '0.85rem', borderRadius: '8px', backgroundColor: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#38bdf8', marginBottom: '0.35rem' }}>
                  Shipping Address Snapshot
                </strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {selectedOrder.shipping_address_snapshot || 'Pending confirmation'}
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div style={{ padding: '0.85rem', borderRadius: '8px', backgroundColor: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#f8fafc', marginBottom: '0.35rem' }}>
                  Payment Terms Snapshot
                </strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {selectedOrder.payment_terms_days_snapshot} days (Cash / Prepaid if 0)
                </span>
              </div>
              <div style={{ padding: '0.85rem', borderRadius: '8px', backgroundColor: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#34d399', marginBottom: '0.35rem' }}>
                  Fulfillment Warehouse
                </strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {selectedOrder.warehouse ? `${selectedOrder.warehouse.code} - ${selectedOrder.warehouse.name}` : 'Default Warehouse'}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setIsDetailsOpen(false)}>
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal: Cancel Order */}
      <Modal isOpen={isCancelOpen} onClose={() => setIsCancelOpen(false)} title="Cancel Sales Order">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--rose-400)' }}>
            <AlertTriangle size={18} />
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
              Cancel confirmation for {selectedOrder?.order_no}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Per Roadmap rules, confirmed orders can only be cancelled if zero items have been invoiced.
          </p>
          <textarea
            rows={3}
            className="input-field"
            placeholder="Reason for cancellation..."
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setIsCancelOpen(false)}>
              Back
            </button>
            <button
              className="btn btn-primary"
              style={{ backgroundColor: 'var(--rose-500)', borderColor: 'var(--rose-500)' }}
              onClick={handleCancelConfirm}
            >
              Confirm Cancellation
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal: Fulfill / Create Shipment */}
      <Modal
        isOpen={isFulfillOpen}
        onClose={() => {
          setIsFulfillOpen(false)
          setSelectedOrder(null)
        }}
        title={`Ship & Fulfill: ${selectedOrder?.order_no}`}
      >
        {selectedOrder && (
          <form onSubmit={handleFulfillSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div
              style={{
                padding: '0.75rem',
                backgroundColor: 'rgba(56, 189, 248, 0.08)',
                borderRadius: '6px',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                fontSize: '0.85rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Warehouse:</span>
                <span style={{ fontWeight: 600, color: '#f8fafc' }}>
                  {selectedOrder.warehouse ? `${selectedOrder.warehouse.code} - ${selectedOrder.warehouse.name}` : 'Default Warehouse'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.25rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Payment Terms:</span>
                <span
                  style={{
                    fontWeight: 600,
                    color: selectedOrder.payment_terms_days_snapshot === 0 ? 'var(--amber-400)' : 'var(--emerald-400)',
                  }}
                >
                  {selectedOrder.payment_terms_days_snapshot === 0
                    ? 'Prepaid (Requires full payment of issued invoices before shipping)'
                    : `${selectedOrder.payment_terms_days_snapshot} Days Credit`}
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label className="form-label">Carrier / Courier</label>
                <input
                  type="text"
                  className="input-field"
                  placeholder="e.g. LBC, NinjaVan, DHL, Internal Fleet"
                  value={fulfillCarrier}
                  onChange={(e) => setFulfillCarrier(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Tracking Number</label>
                <input
                  type="text"
                  className="input-field"
                  placeholder="e.g. TRK-98234710"
                  value={fulfillTracking}
                  onChange={(e) => setFulfillTracking(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="form-label">Fulfillment / Dispatch Notes</label>
              <input
                type="text"
                className="input-field"
                placeholder="Optional notes or dispatch details..."
                value={fulfillNotes}
                onChange={(e) => setFulfillNotes(e.target.value)}
              />
            </div>

            <div>
              <label className="form-label" style={{ marginBottom: '0.5rem', display: 'block' }}>
                Items to Ship
              </label>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '0.5rem' }}>Item</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Ordered</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Shipped</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Remaining</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', width: '120px' }}>Ship Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedOrder.items.map((item) => {
                    const ordered = parseFloat(item.quantity)
                    const shipped = parseFloat(item.quantity_shipped || '0')
                    const remaining = Math.max(0, ordered - shipped)
                    return (
                      <tr key={item.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ fontWeight: 600, color: '#f8fafc' }}>{item.description}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>UOM: {item.uom}</div>
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-dim)' }}>{ordered}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', color: 'var(--text-dim)' }}>{shipped}</td>
                        <td
                          style={{
                            padding: '0.5rem',
                            textAlign: 'right',
                            fontWeight: 600,
                            color: remaining > 0 ? '#38bdf8' : 'var(--text-dim)',
                          }}
                        >
                          {remaining}
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                          <input
                            type="number"
                            min="0"
                            max={remaining}
                            step="any"
                            className="input-field"
                            style={{ textAlign: 'right', padding: '0.25rem 0.5rem' }}
                            value={fulfillQuantities[item.id!] ?? ''}
                            onChange={(e) =>
                              setFulfillQuantities({
                                ...fulfillQuantities,
                                [item.id!]: e.target.value,
                              })
                            }
                            disabled={remaining <= 0}
                          />
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
                className="btn btn-secondary"
                onClick={() => {
                  setIsFulfillOpen(false)
                  setSelectedOrder(null)
                }}
                disabled={isFulfilling}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isFulfilling}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  backgroundColor: '#0284c7',
                  borderColor: '#0284c7',
                }}
              >
                <Truck size={14} />
                {isFulfilling ? 'Posting Shipment...' : 'Post & Dispatch Shipment'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      {/* Modal: Status History */}
      <Modal
        isOpen={isHistoryOpen}
        onClose={() => {
          setIsHistoryOpen(false)
          setSelectedOrder(null)
        }}
        title={`Audit Trail: ${selectedOrder?.order_no}`}
      >
        {selectedOrder && <StatusHistoryTimeline entityType="sales_order" entityId={selectedOrder.id} />}
      </Modal>
    </div>
  )
}
