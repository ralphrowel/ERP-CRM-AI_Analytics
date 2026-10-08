import React, { useEffect, useState } from 'react'
import { ArrowRight, Clock, User, AlertCircle } from 'lucide-react'
import { crmApi, type StatusHistoryItem } from '../api/crm'

interface StatusHistoryTimelineProps {
  entityType: string
  entityId: number
}

export const StatusHistoryTimeline: React.FC<StatusHistoryTimelineProps> = ({
  entityType,
  entityId,
}) => {
  const [history, setHistory] = useState<StatusHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)
    crmApi
      .getStatusHistory(entityType, entityId)
      .then((items) => {
        if (isMounted) {
          setHistory(items)
          setError(null)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err?.message || 'Failed to fetch status transition history')
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [entityType, entityId])

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-dim)', padding: '1rem 0' }}>
        <Clock size={16} className="animate-spin" />
        <span style={{ fontSize: '0.85rem' }}>Loading lifecycle audit trail...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--danger)', padding: '1rem 0' }}>
        <AlertCircle size={16} />
        <span style={{ fontSize: '0.85rem' }}>{error}</span>
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div style={{ color: 'var(--text-dim)', fontSize: '0.85rem', padding: '1rem 0', fontStyle: 'italic' }}>
        No state transition history recorded yet.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0.5rem 0' }}>
      <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', letterSpacing: '0.05em' }}>
        Audit Trail ({history.length} Event{history.length > 1 ? 's' : ''})
      </div>
      <div style={{ position: 'relative', paddingLeft: '1.25rem', borderLeft: '2px solid rgba(255, 255, 255, 0.1)' }}>
        {history.map((item) => (
          <div key={item.id} style={{ position: 'relative', marginBottom: '1.25rem' }}>
            {/* Timeline bullet */}
            <div
              style={{
                position: 'absolute',
                left: '-1.65rem',
                top: '0.2rem',
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: '#6366f1',
                boxShadow: '0 0 8px rgba(99, 102, 241, 0.8)',
              }}
            />

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              {item.from_status ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <span className="badge badge-subtle">{item.from_status}</span>
                  <ArrowRight size={12} color="var(--text-dim)" />
                  <span className="badge badge-indigo">{item.to_status}</span>
                </div>
              ) : (
                <span className="badge badge-emerald">Created as {item.to_status}</span>
              )}

              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Clock size={11} />
                {new Date(item.changed_at).toLocaleString()}
              </span>

              {item.changed_by && (
                <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <User size={11} /> User #{item.changed_by}
                </span>
              )}
            </div>

            {item.reason && (
              <div
                style={{
                  marginTop: '0.35rem',
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  backgroundColor: 'rgba(255, 255, 255, 0.03)',
                  padding: '0.4rem 0.6rem',
                  borderRadius: '4px',
                  borderLeft: '2px solid #6366f1',
                }}
              >
                <strong>Reason:</strong> {item.reason}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
