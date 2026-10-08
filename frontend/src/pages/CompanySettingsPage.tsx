import React, { useEffect, useState } from 'react'
import { Building2, Check, Landmark, Save } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { ProblemAlert } from '../components/ProblemAlert'

interface CompanySettings {
  id: number
  legal_name: string
  trade_name?: string | null
  tin?: string | null
  address?: string | null
  currency_code: string
  timezone: string
  updated_at: string
}

export const CompanySettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<CompanySettings | null>(null)
  const [legalName, setLegalName] = useState('')
  const [tradeName, setTradeName] = useState('')
  const [tin, setTin] = useState('')
  const [address, setAddress] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)

  const loadSettings = async () => {
    try {
      const data = await api.get<CompanySettings>('/api/v1/company-settings')
      setSettings(data)
      setLegalName(data.legal_name)
      setTradeName(data.trade_name || '')
      setTin(data.tin || '')
      setAddress(data.address || '')
    } catch (err: unknown) {
      if (err instanceof ApiError) setError(err)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSaveSuccess(false)
    setIsSaving(true)
    try {
      const updated = await api.put<CompanySettings>('/api/v1/company-settings', {
        legal_name: legalName,
        trade_name: tradeName || null,
        tin: tin || null,
        address: address || null,
      })
      setSettings(updated)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err: unknown) {
      if (err instanceof ApiError) setError(err)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div style={{ maxWidth: '800px' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
          Company & Legal Profile
        </h1>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Enterprise profile and accounting baseline configuration (Roadmap D1, D3, D5).
        </p>
      </div>

      {error && <ProblemAlert error={error} onDismiss={() => setError(null)} />}

      {saveSuccess && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.75rem 1rem',
            borderRadius: '8px',
            backgroundColor: 'var(--emerald-bg)',
            border: '1px solid var(--emerald-border)',
            color: 'var(--emerald)',
            fontSize: '0.875rem',
            fontWeight: 600,
            marginBottom: '1.25rem',
          }}
        >
          <Check size={16} /> Company settings updated successfully.
        </div>
      )}

      <div className="glass-panel" style={{ padding: '2rem' }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Section 1: Legal */}
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Building2 size={18} style={{ color: 'var(--primary)' }} /> Legal Identity
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                  Registered Legal Name *
                </label>
                <input
                  type="text"
                  required
                  value={legalName}
                  onChange={(e) => setLegalName(e.target.value)}
                  className="input-field"
                  placeholder="e.g. Apex Industrial Solutions Corporation"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    Trade / Doing Business As Name
                  </label>
                  <input
                    type="text"
                    value={tradeName}
                    onChange={(e) => setTradeName(e.target.value)}
                    className="input-field"
                    placeholder="Apex Solutions"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    Philippine TIN
                  </label>
                  <input
                    type="text"
                    value={tin}
                    onChange={(e) => setTin(e.target.value)}
                    className="input-field"
                    placeholder="000-123-456-000"
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                  Principal Business Address
                </label>
                <textarea
                  rows={2}
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="input-field"
                  placeholder="Unit 1204, Tower 1, Ayala Triangle, Makati City, Metro Manila"
                />
              </div>
            </div>
          </div>

          {/* Section 2: Fixed Baseline Constants */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Landmark size={18} style={{ color: '#06b6d4' }} /> Operational Baseline (Locked Scope Decisions)
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div
                style={{
                  padding: '1rem',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(0,0,0,0.25)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 700 }}>
                  Standard Currency (D3)
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.25rem' }}>
                  PHP (Philippine Peso ₱)
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.35rem' }}>
                  Locked decision D3: Single currency operation. All line items, payments, and receivables are in PHP.
                </p>
              </div>

              <div
                style={{
                  padding: '1rem',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(0,0,0,0.25)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 700 }}>
                  Business Timezone (D5)
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.25rem' }}>
                  Asia/Manila (UTC+8)
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.35rem' }}>
                  Locked decision D5: All business dates and calendar analytics observe Philippine standard time.
                </p>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              {settings ? `Last updated: ${new Date(settings.updated_at).toLocaleString('en-US', { timeZone: 'Asia/Manila' })} (Manila)` : ''}
            </span>
            <button id="save-settings-btn" type="submit" disabled={isSaving} className="btn btn-primary" style={{ padding: '0.65rem 1.5rem' }}>
              <Save size={16} /> {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
