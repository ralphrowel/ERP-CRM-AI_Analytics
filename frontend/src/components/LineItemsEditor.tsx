import React from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { Product } from '../api/products'
import type { LineItemPayload, TaxRate } from '../api/sales'

interface LineItemsEditorProps {
  items: LineItemPayload[]
  onChange: (items: LineItemPayload[]) => void
  products: Product[]
  taxRates: TaxRate[]
}

export const LineItemsEditor: React.FC<LineItemsEditorProps> = ({
  items,
  onChange,
  products,
  taxRates,
}) => {
  const defaultTaxRate = taxRates.find((t) => t.is_default) || taxRates[0]

  const handleAddLine = () => {
    onChange([
      ...items,
      {
        product_id: null,
        description: '',
        uom: 'pc',
        quantity: '1.000',
        unit_price: '0.0000',
        discount_amount: '0.00',
        tax_rate_id: defaultTaxRate?.id,
      },
    ])
  }

  const handleRemoveLine = (index: number) => {
    onChange(items.filter((_, idx) => idx !== index))
  }

  const handleLineChange = (index: number, field: keyof LineItemPayload, value: unknown) => {
    const updated = [...items]
    const current = { ...updated[index] }

    if (field === 'product_id') {
      const prodId = value ? Number(value) : null
      current.product_id = prodId
      if (prodId) {
        const prod = products.find((p) => p.id === prodId)
        if (prod) {
          current.description = prod.name
          current.uom = prod.uom
          current.unit_price = prod.list_price
        }
      }
    } else {
      // @ts-expect-error dynamic assign
      current[field] = value
    }

    updated[index] = current
    onChange(updated)
  }

  // Live computed preview per Roadmap §4.3
  const computeTotals = () => {
    let subtotal = 0
    let discountTotal = 0
    let taxTotal = 0

    items.forEach((item) => {
      const qty = parseFloat(item.quantity) || 0
      const price = parseFloat(item.unit_price) || 0
      const discount = parseFloat(item.discount_amount || '0') || 0
      const trObj = taxRates.find((t) => t.id === item.tax_rate_id) || defaultTaxRate
      const rate = trObj ? parseFloat(trObj.rate) : 0.12

      const gross = Math.round(qty * price * 100) / 100
      const net = Math.max(0, Math.round((gross - discount) * 100) / 100)
      const tax = Math.round(net * rate * 100) / 100

      subtotal += net
      discountTotal += discount
      taxTotal += tax
    })

    return {
      subtotal: subtotal.toFixed(2),
      discountTotal: discountTotal.toFixed(2),
      taxTotal: taxTotal.toFixed(2),
      grandTotal: (subtotal + taxTotal).toFixed(2),
    }
  }

  const totals = computeTotals()
  const formatCurrency = (val: string) =>
    new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(parseFloat(val))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ overflowX: 'auto', border: '1px solid var(--border-subtle)', borderRadius: '8px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '750px' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '35px' }}>#</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '220px' }}>Product & Description</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '80px' }}>UoM</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '90px' }}>Qty</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '110px' }}>Unit Price (₱)</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '100px' }}>Discount (₱)</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', width: '110px' }}>Tax Rate</th>
              <th style={{ padding: '0.65rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-dim)', textAlign: 'right', width: '110px' }}>Total</th>
              <th style={{ padding: '0.65rem 0.75rem', width: '40px' }}></th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
                  No items added yet. Click &quot;Add Line Item&quot; below.
                </td>
              </tr>
            ) : (
              items.map((item, idx) => {
                const qty = parseFloat(item.quantity) || 0
                const price = parseFloat(item.unit_price) || 0
                const disc = parseFloat(item.discount_amount || '0') || 0
                const trObj = taxRates.find((t) => t.id === item.tax_rate_id) || defaultTaxRate
                const rate = trObj ? parseFloat(trObj.rate) : 0.12
                const gross = Math.round(qty * price * 100) / 100
                const net = Math.max(0, Math.round((gross - disc) * 100) / 100)
                const lineTotal = Math.round((net + net * rate) * 100) / 100

                return (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem', color: 'var(--text-dim)' }}>{idx + 1}</td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <select
                        className="input-field"
                        style={{ marginBottom: '0.25rem', fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.product_id || ''}
                        onChange={(e) => handleLineChange(idx, 'product_id', e.target.value)}
                      >
                        <option value="">-- Custom / Ad-hoc Item --</option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku} · {p.name}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        required
                        className="input-field"
                        placeholder="Line description..."
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.description || ''}
                        onChange={(e) => handleLineChange(idx, 'description', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <input
                        type="text"
                        className="input-field"
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.uom || 'pc'}
                        onChange={(e) => handleLineChange(idx, 'uom', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <input
                        type="number"
                        step="0.001"
                        min="0.001"
                        required
                        className="input-field"
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.quantity}
                        onChange={(e) => handleLineChange(idx, 'quantity', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <input
                        type="number"
                        step="0.0001"
                        min="0"
                        required
                        className="input-field"
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.unit_price}
                        onChange={(e) => handleLineChange(idx, 'unit_price', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        className="input-field"
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.discount_amount || '0'}
                        onChange={(e) => handleLineChange(idx, 'discount_amount', e.target.value)}
                      />
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <select
                        className="input-field"
                        style={{ fontSize: '0.8rem', padding: '0.3rem' }}
                        value={item.tax_rate_id || defaultTaxRate?.id || ''}
                        onChange={(e) => handleLineChange(idx, 'tax_rate_id', Number(e.target.value))}
                      >
                        {taxRates.map((tr) => (
                          <option key={tr.id} value={tr.id}>
                            {tr.code} ({(parseFloat(tr.rate) * 100).toFixed(0)}%)
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontWeight: 600, fontSize: '0.85rem', color: '#f8fafc' }}>
                      {formatCurrency(lineTotal.toString())}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                      <button
                        type="button"
                        onClick={() => handleRemoveLine(idx)}
                        style={{ background: 'none', border: 'none', color: 'var(--rose-400)', cursor: 'pointer', padding: '4px' }}
                        title="Remove Line"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <button
          type="button"
          onClick={handleAddLine}
          className="btn btn-secondary"
          style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem' }}
        >
          <Plus size={14} /> Add Line Item
        </button>

        {/* Live Totals Card */}
        <div
          style={{
            backgroundColor: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            padding: '0.85rem 1.25rem',
            minWidth: '240px',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.35rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span>Subtotal:</span>
            <span>{formatCurrency(totals.subtotal)}</span>
          </div>
          {parseFloat(totals.discountTotal) > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--rose-400)' }}>
              <span>Discounts:</span>
              <span>-{formatCurrency(totals.discountTotal)}</span>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span>12% VAT:</span>
            <span>{formatCurrency(totals.taxTotal)}</span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '0.95rem',
              fontWeight: 700,
              color: '#38bdf8',
              borderTop: '1px solid var(--border-subtle)',
              paddingTop: '0.4rem',
              marginTop: '0.2rem',
            }}
          >
            <span>Grand Total:</span>
            <span>{formatCurrency(totals.grandTotal)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
