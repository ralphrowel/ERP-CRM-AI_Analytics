import React from 'react'
import { AlertCircle, X } from 'lucide-react'
import { ApiError } from '../api/client'

interface ProblemAlertProps {
  error: ApiError | Error | string | null
  onDismiss?: () => void
}

export const ProblemAlert: React.FC<ProblemAlertProps> = ({ error, onDismiss }) => {
  if (!error) return null

  const isApiError = error instanceof ApiError
  const problem = isApiError ? error.problem : null
  const message = typeof error === 'string' ? error : error.message

  return (
    <div
      id="problem-details-banner"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        padding: '0.85rem 1.25rem',
        borderRadius: '10px',
        backgroundColor: 'rgba(239, 68, 68, 0.12)',
        border: '1px solid rgba(239, 68, 68, 0.35)',
        color: '#fca5a5',
        marginBottom: '1.25rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <AlertCircle size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong style={{ display: 'block', fontSize: '0.875rem' }}>
            {problem?.title || 'Action Failed'}
          </strong>
          <span style={{ fontSize: '0.825rem' }}>{message}</span>
          {problem?.invalid_params && problem.invalid_params.length > 0 && (
            <ul style={{ marginTop: '0.5rem', paddingLeft: '1.2rem', fontSize: '0.775rem' }}>
              {problem.invalid_params.map((p, idx) => (
                <li key={idx}>
                  <strong>{p.name}:</strong> {p.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: 'none',
            border: 'none',
            color: '#fca5a5',
            cursor: 'pointer',
            padding: '2px',
          }}
        >
          <X size={16} />
        </button>
      )}
    </div>
  )
}
