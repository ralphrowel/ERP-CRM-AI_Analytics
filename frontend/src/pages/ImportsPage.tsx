import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  FileCheck2,
  FileSpreadsheet,
  Filter,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  UploadCloud,
  XCircle,
} from 'lucide-react'
import {
  commitImportBatch,
  getImportBatchDetail,
  type ImportBatch,
  listImportBatches,
  type StagingRow,
  uploadImportCsv,
  uploadRawCsv,
  validateImportBatch,
} from '../api/imports'
import { useAuth } from '../context/AuthContext'

const SAMPLE_DIRTY_CUSTOMERS = `name,email,phone,tin,city,province,customer_type,payment_terms,credit_limit
Ayala Industrial Corp,info@ayala-ind.ph,09171234567,123-456-789-000,Makati,Metro Manila,company,30,₱ 500,000.00
San Miguel Distribution,smb@distribution.ph,+63 917 555 4321,222-333-444-000,Mandaluyong,Metro Manila,company,60,PHP 1,200,000.00
,corrupt-no-name@example.ph,09171112233,333-444-555-000,Quezon City,Metro Manila,company,30,50000.00
Defective Email Corp,invalid-email-address,09182223344,444-555-666-000,Taguig,Metro Manila,company,15,250000.00
Puregold Retail Hub,purchasing@puregold.ph,09173334455,555-666-777-000,Manila,Metro Manila,company,30,₱ 750,000.00
Negative Limit Inc,negative@limit.ph,09174445566,666-777-888-000,Pasig,Metro Manila,company,30,-10000.00
Juan Dela Cruz Enterprise,juan@delacruz.ph,09175556677,777-888-999-000,Cebu City,Cebu,individual,0,100000.00`

const SAMPLE_DIRTY_PRODUCTS = `sku,name,product_type,uom,list_price
SKU-IND-BOLT-01,Heavy Industrial Hex Bolt M12,stock,pc,₱ 120.00
SKU-SERV-ENG-01,Engineering Consultation,service,hr,1500.00
SKU-IND-BOLT-01,Duplicate SKU Item,stock,pc,200.00
SKU-CORRUPT-99,Negative Price Gear,stock,pc,-450.00
SKU-ELEC-WIRE-10,Insulated Copper Wire 10m,stock,box,₱ 2,350.50`

export const ImportsPage: React.FC = () => {
  const { hasPermission, isSuperuser } = useAuth()
  const canUpload = isSuperuser || hasPermission('import:upload')
  const canCommit = isSuperuser || hasPermission('import:commit')

  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [selectedBatch, setSelectedBatch] = useState<ImportBatch | null>(null)
  const [stagingRows, setStagingRows] = useState<StagingRow[]>([])
  const [rowStatusFilter, setRowStatusFilter] = useState<'all' | 'valid' | 'error' | 'committed'>('all')
  const [rowSearchQuery, setRowSearchQuery] = useState('')

  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isCommitting, setIsCommitting] = useState(false)
  const [selectedEntityType, setSelectedEntityType] = useState<'customer' | 'product' | 'contact'>('customer')
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadBatches = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await listImportBatches()
      setBatches(data)
      if (data.length > 0 && !selectedBatch) {
        loadBatchDetail(data[0].id)
      }
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch import batches',
      })
    } finally {
      setIsLoading(false)
    }
  }, [selectedBatch])

  const loadBatchDetail = async (batchId: number) => {
    try {
      const detail = await getImportBatchDetail(batchId, 500)
      setSelectedBatch(detail.batch)
      setStagingRows(detail.staging_rows)
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to load batch inspection rows',
      })
    }
  }

  useEffect(() => {
    loadBatches()
  }, [])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsUploading(true)
    setFeedbackMessage(null)
    try {
      const batch = await uploadImportCsv(file, selectedEntityType, 'browser_upload')
      setFeedbackMessage({
        type: 'success',
        text: `Uploaded "${file.name}". Staged ${batch.row_count} rows (${batch.valid_count} valid, ${batch.error_count} flagged defects).`,
      })
      await loadBatches()
      loadBatchDetail(batch.id)
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'CSV file upload failed',
      })
    } finally {
      setIsUploading(false)
      e.target.value = ''
    }
  }

  const handleLoadSample = async (entity: 'customer' | 'product') => {
    setIsUploading(true)
    setFeedbackMessage(null)
    try {
      const content = entity === 'customer' ? SAMPLE_DIRTY_CUSTOMERS : SAMPLE_DIRTY_PRODUCTS
      const fileName = `sample_dirty_${entity}s.csv`
      const batch = await uploadRawCsv({
        entity_type: entity,
        file_name: fileName,
        csv_content: content,
        source_label: 'sample_demonstrator',
      })
      setFeedbackMessage({
        type: 'success',
        text: `Sample batch staged successfully! Analyzed ${batch.row_count} rows with controlled defects.`,
      })
      await loadBatches()
      loadBatchDetail(batch.id)
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Sample CSV staging failed',
      })
    } finally {
      setIsUploading(false)
    }
  }

  const handleRevalidate = async (batchId: number) => {
    try {
      const updated = await validateImportBatch(batchId)
      setSelectedBatch(updated)
      loadBatchDetail(batchId)
      setFeedbackMessage({
        type: 'success',
        text: `Batch #${batchId} re-validated. ${updated.valid_count} valid, ${updated.error_count} defects.`,
      })
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Re-validation failed',
      })
    }
  }

  const handleCommit = async (batchId: number) => {
    setIsCommitting(true)
    setFeedbackMessage(null)
    try {
      const result = await commitImportBatch(batchId)
      setFeedbackMessage({
        type: 'success',
        text: result.message,
      })
      await loadBatches()
      loadBatchDetail(batchId)
    } catch (err: unknown) {
      setFeedbackMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Batch commit execution failed',
      })
    } finally {
      setIsCommitting(false)
    }
  }

  // Filter staging rows
  const filteredRows = stagingRows.filter((r) => {
    if (rowStatusFilter === 'valid') {
      if (r.validation_errors && r.validation_errors.length > 0) return false
    } else if (rowStatusFilter === 'error') {
      if (!r.validation_errors || r.validation_errors.length === 0) return false
    } else if (rowStatusFilter === 'committed') {
      if (!r.committed_id) return false
    }

    if (rowSearchQuery.trim()) {
      const q = rowSearchQuery.toLowerCase()
      const searchStr = `${r.name || ''} ${r.sku || ''} ${r.first_name || ''} ${r.email || ''} ${r.city || ''}`.toLowerCase()
      if (!searchStr.includes(q)) return false
    }
    return true
  })

  // Aggregated totals
  const totalBatches = batches.length
  const totalRowsStaged = batches.reduce((acc, b) => acc + b.row_count, 0)
  const totalRowsValid = batches.reduce((acc, b) => acc + b.valid_count, 0)
  const totalRowsCommitted = batches.reduce((acc, b) => acc + b.committed_count, 0)

  return (
    <div style={{ padding: '2rem', maxWidth: '1440px', margin: '0 auto', color: '#f8fafc' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '2rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
              }}
            >
              <Database size={22} color="#ffffff" />
            </div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
              Legacy & CSV Data Import Engine
            </h1>
          </div>
          <p style={{ margin: 0, color: 'var(--text-muted, #94a3b8)', fontSize: '0.925rem' }}>
            Operational core dirty-data staging pipeline (V1.0 Path A), row-level defect analysis, and partial commit.
          </p>
        </div>

        {/* Global Controls */}
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button
            onClick={() => loadBatches()}
            disabled={isLoading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.6rem 1rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#e2e8f0',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            <RefreshCw size={15} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Feedback Toast */}
      {feedbackMessage && (
        <div
          style={{
            padding: '1rem 1.25rem',
            borderRadius: '10px',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            backgroundColor: feedbackMessage.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            border: `1px solid ${feedbackMessage.type === 'success' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
            color: feedbackMessage.type === 'success' ? '#34d399' : '#f87171',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {feedbackMessage.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
            <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{feedbackMessage.text}</span>
          </div>
          <button
            onClick={() => setFeedbackMessage(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1.25rem' }}
          >
            ×
          </button>
        </div>
      )}

      {/* KPI Summary Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
            <span>Import Batches</span>
            <FileSpreadsheet size={16} color="#6366f1" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, marginTop: '0.5rem', color: '#f8fafc' }}>
            {totalBatches}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
            Total uploaded files
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
            <span>Staged Rows</span>
            <Database size={16} color="#38bdf8" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, marginTop: '0.5rem', color: '#f8fafc' }}>
            {totalRowsStaged.toLocaleString()}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
            Raw untouched records
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
            <span>Valid Records</span>
            <ShieldCheck size={16} color="#34d399" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, marginTop: '0.5rem', color: '#34d399' }}>
            {totalRowsValid.toLocaleString()}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
            Passed format & integrity rules
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
            <span>Committed to ERP</span>
            <CheckCircle2 size={16} color="#10b981" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, marginTop: '0.5rem', color: '#10b981' }}>
            {totalRowsCommitted.toLocaleString()}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
            Committed into operational core
          </div>
        </div>
      </div>

      {/* Main Grid: Upload Staging & Batches */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Upload Box Card */}
        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.6)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '14px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <UploadCloud size={20} color="#818cf8" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Upload CSV Dataset</h2>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
              Select Entity Type
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              {(['customer', 'product', 'contact'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setSelectedEntityType(t)}
                  style={{
                    padding: '0.5rem 0.25rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    cursor: 'pointer',
                    backgroundColor: selectedEntityType === t ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                    border: selectedEntityType === t ? '1px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.1)',
                    color: selectedEntityType === t ? '#818cf8' : '#94a3b8',
                  }}
                >
                  {t}s
                </button>
              ))}
            </div>
          </div>

          {/* Drag & Drop Area */}
          <label
            style={{
              border: '2px dashed rgba(99, 102, 241, 0.35)',
              borderRadius: '12px',
              padding: '2rem 1rem',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.75rem',
              cursor: canUpload && !isUploading ? 'pointer' : 'not-allowed',
              backgroundColor: 'rgba(15, 23, 42, 0.4)',
              transition: 'border-color 0.2s',
            }}
          >
            <input
              type="file"
              accept=".csv"
              disabled={!canUpload || isUploading}
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
            <div
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                backgroundColor: 'rgba(99, 102, 241, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Upload size={22} color="#818cf8" />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc' }}>
                {isUploading ? 'Staging & Validating CSV...' : 'Click to Upload CSV'}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.2rem' }}>
                Text-based staging; raw JSONB preserved
              </div>
            </div>
          </label>

          {/* Quick Demonstrator Templates */}
          <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Sparkles size={16} color="#fbbf24" />
              <span style={{ fontSize: '0.825rem', fontWeight: 600, color: '#cbd5e1' }}>
                Quick Test Datasets
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => handleLoadSample('customer')}
                disabled={isUploading || !canUpload}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.6rem 0.75rem',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#e2e8f0',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span>Dirty Customers (7 rows, mixed errors)</span>
                <Play size={14} color="#818cf8" />
              </button>

              <button
                type="button"
                onClick={() => handleLoadSample('product')}
                disabled={isUploading || !canUpload}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.6rem 0.75rem',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#e2e8f0',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span>Dirty Products (Duplicate SKU, negative price)</span>
                <Play size={14} color="#818cf8" />
              </button>
            </div>
          </div>
        </div>

        {/* Batch Ledger Table */}
        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.6)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '14px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Import Batches</h2>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{batches.length} Batches Registered</span>
          </div>

          <div style={{ overflowX: 'auto', flex: 1 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: '#94a3b8', textAlign: 'left' }}>
                  <th style={{ padding: '0.75rem 0.5rem' }}>Batch</th>
                  <th style={{ padding: '0.75rem 0.5rem' }}>Entity</th>
                  <th style={{ padding: '0.75rem 0.5rem' }}>File Name</th>
                  <th style={{ padding: '0.75rem 0.5rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Total</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Valid</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Errors</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Committed</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {batches.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
                      No import batches yet. Upload a CSV file or load sample dataset.
                    </td>
                  </tr>
                ) : (
                  batches.map((b) => {
                    const isSelected = selectedBatch?.id === b.id
                    return (
                      <tr
                        key={b.id}
                        onClick={() => loadBatchDetail(b.id)}
                        style={{
                          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                          transition: 'background-color 0.15s',
                        }}
                      >
                        <td style={{ padding: '0.75rem 0.5rem', fontWeight: 600, color: '#818cf8' }}>#{b.id}</td>
                        <td style={{ padding: '0.75rem 0.5rem', textTransform: 'capitalize' }}>{b.entity_type}</td>
                        <td style={{ padding: '0.75rem 0.5rem', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {b.file_name}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.3rem',
                              padding: '0.2rem 0.55rem',
                              borderRadius: '999px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              backgroundColor:
                                b.status === 'committed'
                                  ? 'rgba(16, 185, 129, 0.2)'
                                  : b.status === 'validated'
                                  ? 'rgba(56, 189, 248, 0.2)'
                                  : 'rgba(239, 68, 68, 0.2)',
                              color:
                                b.status === 'committed'
                                  ? '#34d399'
                                  : b.status === 'validated'
                                  ? '#38bdf8'
                                  : '#f87171',
                            }}
                          >
                            {b.status === 'committed' && <CheckCircle2 size={12} />}
                            {b.status === 'validated' && <FileCheck2 size={12} />}
                            {b.status === 'failed' && <XCircle size={12} />}
                            {b.status}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>{b.row_count}</td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: '#34d399' }}>{b.valid_count}</td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: b.error_count > 0 ? '#f87171' : '#94a3b8' }}>
                          {b.error_count}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: '#10b981', fontWeight: 600 }}>
                          {b.committed_count}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              loadBatchDetail(b.id)
                            }}
                            style={{
                              padding: '0.35rem 0.65rem',
                              borderRadius: '6px',
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              border: '1px solid rgba(255, 255, 255, 0.1)',
                              color: '#cbd5e1',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                            }}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detail Section: Staging Inspection & Partial Commit */}
      {selectedBatch && (
        <div
          style={{
            backgroundColor: 'rgba(30, 41, 59, 0.6)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '14px',
            padding: '1.75rem',
          }}
        >
          {/* Detail Controls Header */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1.25rem',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
                  Batch #{selectedBatch.id}: {selectedBatch.file_name}
                </h3>
                <span
                  style={{
                    padding: '0.2rem 0.6rem',
                    borderRadius: '6px',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase',
                    fontWeight: 700,
                    letterSpacing: '0.05em',
                    backgroundColor: 'rgba(99, 102, 241, 0.2)',
                    color: '#818cf8',
                  }}
                >
                  {selectedBatch.entity_type}
                </span>
              </div>
              <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '0.3rem', display: 'flex', gap: '1rem' }}>
                <span>SHA-256: {selectedBatch.file_sha256.slice(0, 16)}...</span>
                <span>Created: {new Date(selectedBatch.created_at).toLocaleString()}</span>
                {selectedBatch.committed_at && (
                  <span>Committed: {new Date(selectedBatch.committed_at).toLocaleString()}</span>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <button
                type="button"
                onClick={() => handleRevalidate(selectedBatch.id)}
                disabled={isLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.6rem 1rem',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.12)',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                }}
              >
                <RefreshCw size={14} />
                Re-Validate
              </button>

              <button
                type="button"
                onClick={() => handleCommit(selectedBatch.id)}
                disabled={isCommitting || !canCommit || selectedBatch.valid_count === 0}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.6rem 1.25rem',
                  borderRadius: '8px',
                  background:
                    selectedBatch.valid_count > 0
                      ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                      : 'rgba(255, 255, 255, 0.1)',
                  border: 'none',
                  color: '#ffffff',
                  cursor: selectedBatch.valid_count > 0 && !isCommitting ? 'pointer' : 'not-allowed',
                  fontSize: '0.875rem',
                  fontWeight: 700,
                  boxShadow: selectedBatch.valid_count > 0 ? '0 4px 12px rgba(16, 185, 129, 0.3)' : 'none',
                }}
              >
                <ArrowRight size={16} />
                {isCommitting
                  ? 'Committing Valid Rows...'
                  : `Partial Commit (${selectedBatch.valid_count} Valid Rows)`}
              </button>
            </div>
          </div>

          {/* Filter Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              backgroundColor: 'rgba(15, 23, 42, 0.5)',
              padding: '0.75rem 1rem',
              borderRadius: '10px',
              marginBottom: '1rem',
              gap: '1rem',
              flexWrap: 'wrap',
            }}
          >
            {/* Filter Tabs */}
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <Filter size={15} color="#94a3b8" />
              {(['all', 'valid', 'error', 'committed'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setRowStatusFilter(mode)}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '6px',
                    fontSize: '0.775rem',
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    cursor: 'pointer',
                    backgroundColor: rowStatusFilter === mode ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
                    border: rowStatusFilter === mode ? '1px solid #6366f1' : '1px solid transparent',
                    color: rowStatusFilter === mode ? '#818cf8' : '#94a3b8',
                  }}
                >
                  {mode === 'all'
                    ? `All (${stagingRows.length})`
                    : mode === 'valid'
                    ? `Valid (${selectedBatch.valid_count})`
                    : mode === 'error'
                    ? `Defects (${selectedBatch.error_count})`
                    : `Committed (${selectedBatch.committed_count})`}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <Search size={14} color="#94a3b8" />
              <input
                type="text"
                placeholder="Search row text..."
                value={rowSearchQuery}
                onChange={(e) => setRowSearchQuery(e.target.value)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#f8fafc',
                  fontSize: '0.825rem',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Staging Rows Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: '#94a3b8', textAlign: 'left' }}>
                  <th style={{ padding: '0.65rem 0.5rem', width: '60px' }}>Row</th>
                  <th style={{ padding: '0.65rem 0.5rem' }}>Primary Field</th>
                  <th style={{ padding: '0.65rem 0.5rem' }}>Secondary Details</th>
                  <th style={{ padding: '0.65rem 0.5rem' }}>Amount / Pricing</th>
                  <th style={{ padding: '0.65rem 0.5rem' }}>Validation Status & Defects</th>
                  <th style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>ERP Record</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '2.5rem', color: '#64748b' }}>
                      No staging rows matching filter criteria.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((r) => {
                    const hasErrors = r.validation_errors && r.validation_errors.length > 0
                    return (
                      <tr
                        key={r.id}
                        style={{
                          borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                          backgroundColor: hasErrors
                            ? 'rgba(239, 68, 68, 0.04)'
                            : r.committed_id
                            ? 'rgba(16, 185, 129, 0.04)'
                            : 'transparent',
                        }}
                      >
                        <td style={{ padding: '0.65rem 0.5rem', color: '#94a3b8' }}>#{r.row_number}</td>

                        {/* Primary Field */}
                        <td style={{ padding: '0.65rem 0.5rem', fontWeight: 600, color: '#f8fafc' }}>
                          {r.name || r.sku || r.first_name || (
                            <span style={{ color: '#ef4444', fontStyle: 'italic' }}>[Missing Value]</span>
                          )}
                          {r.customer_type && (
                            <span
                              style={{
                                display: 'inline-block',
                                marginLeft: '0.5rem',
                                fontSize: '0.7rem',
                                color: '#94a3b8',
                                backgroundColor: 'rgba(255, 255, 255, 0.06)',
                                padding: '0.1rem 0.4rem',
                                borderRadius: '4px',
                              }}
                            >
                              {r.customer_type}
                            </span>
                          )}
                        </td>

                        {/* Secondary Details */}
                        <td style={{ padding: '0.65rem 0.5rem', color: '#cbd5e1' }}>
                          <div>{r.email || r.phone || r.uom || r.job_title || '—'}</div>
                          {(r.city || r.province) && (
                            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                              {r.city}
                              {r.province ? `, ${r.province}` : ''}
                            </div>
                          )}
                        </td>

                        {/* Amount / Pricing */}
                        <td style={{ padding: '0.65rem 0.5rem', color: '#cbd5e1' }}>
                          {r.credit_limit || r.list_price || '—'}
                        </td>

                        {/* Validation Defects */}
                        <td style={{ padding: '0.65rem 0.5rem' }}>
                          {hasErrors ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                              {r.validation_errors!.map((err, idx) => (
                                <div
                                  key={idx}
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.35rem',
                                    padding: '0.2rem 0.5rem',
                                    borderRadius: '4px',
                                    backgroundColor: 'rgba(239, 68, 68, 0.15)',
                                    color: '#f87171',
                                    fontSize: '0.75rem',
                                    fontWeight: 500,
                                  }}
                                >
                                  <AlertTriangle size={12} />
                                  <span>
                                    <strong>{err.field}</strong>: {err.message}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                padding: '0.2rem 0.5rem',
                                borderRadius: '4px',
                                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                color: '#34d399',
                                fontSize: '0.75rem',
                                fontWeight: 500,
                              }}
                            >
                              <CheckCircle2 size={12} />
                              Valid Staging Row
                            </span>
                          )}
                        </td>

                        {/* ERP Record */}
                        <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                          {r.committed_id ? (
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '0.2rem 0.6rem',
                                borderRadius: '6px',
                                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                                color: '#34d399',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                              }}
                            >
                              ID #{r.committed_id}
                            </span>
                          ) : (
                            <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                              <Clock size={12} style={{ verticalAlign: 'middle', marginRight: '0.2rem' }} />
                              Pending
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
    </div>
  )
}
export default ImportsPage
