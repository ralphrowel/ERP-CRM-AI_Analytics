import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface ConflictAlertProps {
  onReload: () => void
  message?: string
}

export const ConflictAlert: React.FC<ConflictAlertProps> = ({
  onReload,
  message = 'This record was modified by another user or session. Please reload the latest version before making changes.',
}) => {
  return (
    <div
      id="conflict-alert-banner"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.85rem 1.25rem',
        borderRadius: '10px',
        backgroundColor: 'rgba(245, 158, 11, 0.12)',
        border: '1px solid rgba(245, 158, 11, 0.35)',
        color: '#fbbf24',
        marginBottom: '1.25rem',
        animation: 'fadeIn 0.2s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <AlertTriangle size={20} style={{ flexShrink: 0 }} />
        <div>
          <strong style={{ display: 'block', fontSize: '0.875rem' }}>Version Conflict (HTTP 409)</strong>
          <span style={{ fontSize: '0.825rem', opacity: 0.9 }}>{message}</span>
        </div>
      </div>
      <button
        id="conflict-reload-btn"
        onClick={onReload}
        className="btn"
        style={{
          backgroundColor: '#f59e0b',
          color: '#000000',
          fontWeight: 700,
          fontSize: '0.8rem',
          padding: '0.4rem 0.85rem',
        }}
      >
        <RefreshCw size={14} />
        Reload Data
      </button>
    </div>
  )
}
