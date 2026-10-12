import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Bell,
  Check,
  CheckCheck,
  Clock,
  ExternalLink,
  Filter,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import {
  type DeadLetterEvent,
  fetchDeadLetters,
  fetchNotifications,
  type InAppNotification,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  retryDeadLetterEvent,
} from '../api/notifications'

export const NotificationsPage: React.FC = () => {
  const { isSuperuser } = useAuth()
  const [activeView, setActiveView] = useState<'notifications' | 'dead_letters'>('notifications')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [notifications, setNotifications] = useState<InAppNotification[]>([])
  const [totalNotifications, setTotalNotifications] = useState<number>(0)
  const [unreadCount, setUnreadCount] = useState<number>(0)

  // Dead letters (Worker failure observability)
  const [deadLetters, setDeadLetters] = useState<DeadLetterEvent[]>([])
  const [loadingDeadLetters, setLoadingDeadLetters] = useState<boolean>(false)
  const [retryingId, setRetryingId] = useState<number | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 4000)
  }

  const loadNotifications = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetchNotifications({ unread_only: unreadOnly, page: 1, page_size: 50 })
      setNotifications(resp.items)
      setTotalNotifications(resp.total)
      setUnreadCount(resp.unread_count)
    } catch (err) {
      console.error('Failed to load notifications', err)
    } finally {
      setLoading(false)
    }
  }, [unreadOnly])

  const loadDeadLetters = useCallback(async () => {
    setLoadingDeadLetters(true)
    try {
      const resp = await fetchDeadLetters({ limit: 50 })
      setDeadLetters(resp.items)
    } catch (err) {
      console.error('Failed to load dead letters', err)
    } finally {
      setLoadingDeadLetters(false)
    }
  }, [])

  useEffect(() => {
    if (activeView === 'notifications') {
      loadNotifications()
    } else {
      loadDeadLetters()
    }
  }, [activeView, loadNotifications, loadDeadLetters])

  const handleMarkAsRead = async (id: number) => {
    try {
      await markNotificationAsRead(id)
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      )
      setUnreadCount((c) => Math.max(0, c - 1))
      showToast('Notification marked as read')
    } catch (err) {
      console.error('Failed to mark read', err)
    }
  }

  const handleMarkAllRead = async () => {
    try {
      const resp = await markAllNotificationsAsRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() })))
      setUnreadCount(0)
      showToast(`Marked ${resp.marked_read} notifications as read`)
    } catch (err) {
      console.error('Failed to mark all read', err)
    }
  }

  const handleRetryDeadLetter = async (id: number) => {
    setRetryingId(id)
    try {
      await retryDeadLetterEvent(id)
      showToast(`Event #${id} queued for replay`)
      await loadDeadLetters()
    } catch (err) {
      console.error('Failed to retry event', err)
      showToast('Error replaying event')
    } finally {
      setRetryingId(null)
    }
  }

  const filteredNotifications = notifications.filter((n) => {
    if (categoryFilter === 'all') return true
    return n.category === categoryFilter
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      {toastMessage && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: 'linear-gradient(135deg, #1e293b, #0f172a)',
            border: '1px solid #38bdf8',
            color: '#f8fafc',
            padding: '12px 20px',
            borderRadius: '8px',
            boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
            zIndex: 999,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.875rem',
          }}
        >
          <Check size={16} color="#38bdf8" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              color: '#f8fafc',
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
            }}
          >
            <Bell size={26} color="#6366f1" />
            Notifications & System Events
          </h1>
          <p style={{ margin: '4px 0 0', color: 'var(--text-dim)', fontSize: '0.875rem' }}>
            Milestone V1.8 Transactional Outbox, In-App Dispatch, and Worker Resilience ({totalNotifications} total logged)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {activeView === 'notifications' && unreadCount > 0 && (
            <button
              id="mark-all-read-btn"
              onClick={handleMarkAllRead}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <CheckCheck size={16} /> Mark all read ({unreadCount})
            </button>
          )}

          <button
            id="refresh-notifications-btn"
            onClick={activeView === 'notifications' ? loadNotifications : loadDeadLetters}
            className="btn btn-secondary"
            title="Refresh"
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={16} className={loading || loadingDeadLetters ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Top View Selector: Notifications vs Outbox Dead-Letters */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--border-subtle)' }}>
        <button
          id="view-notifications-tab"
          onClick={() => setActiveView('notifications')}
          style={{
            padding: '10px 18px',
            background: 'transparent',
            border: 'none',
            borderBottom: activeView === 'notifications' ? '2px solid #6366f1' : '2px solid transparent',
            color: activeView === 'notifications' ? '#a5b4fc' : 'var(--text-dim)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '0.95rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Bell size={16} />
          In-App Notifications
          {unreadCount > 0 && (
            <span
              style={{
                background: '#ef4444',
                color: '#fff',
                borderRadius: '999px',
                padding: '2px 8px',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              {unreadCount}
            </span>
          )}
        </button>

        {isSuperuser && (
          <button
            id="view-dead-letters-tab"
            onClick={() => setActiveView('dead_letters')}
            style={{
              padding: '10px 18px',
              background: 'transparent',
              border: 'none',
              borderBottom: activeView === 'dead_letters' ? '2px solid #ef4444' : '2px solid transparent',
              color: activeView === 'dead_letters' ? '#fca5a5' : 'var(--text-dim)',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: '0.95rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <ShieldAlert size={16} />
            Outbox Dead-Letters (Failures)
            {deadLetters.length > 0 && (
              <span
                style={{
                  background: '#991b1b',
                  color: '#fff',
                  borderRadius: '999px',
                  padding: '2px 8px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                {deadLetters.length}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Main View: In-App Notifications */}
      {activeView === 'notifications' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Filter Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
              backgroundColor: 'rgba(15, 23, 42, 0.6)',
              padding: '12px 16px',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <Filter size={15} color="var(--text-dim)" />
              <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)', fontWeight: 500 }}>Category:</span>
              {['all', 'sales', 'purchasing', 'inventory', 'workflow', 'system'].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    border: '1px solid',
                    borderColor: categoryFilter === cat ? '#6366f1' : 'transparent',
                    background: categoryFilter === cat ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                    color: categoryFilter === cat ? '#a5b4fc' : 'var(--text-muted)',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    cursor: 'pointer',
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>

            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.85rem',
                color: 'var(--text-main)',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={(e) => setUnreadOnly(e.target.checked)}
                style={{ accentColor: '#6366f1' }}
              />
              Show Unread Only
            </label>
          </div>

          {/* Notifications List */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
              <RefreshCw size={24} className="spin" style={{ marginBottom: '8px' }} />
              <div>Loading notifications...</div>
            </div>
          ) : filteredNotifications.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '4rem 2rem',
                backgroundColor: 'rgba(15, 23, 42, 0.3)',
                borderRadius: '12px',
                border: '1px dashed var(--border-subtle)',
              }}
            >
              <Bell size={36} color="var(--text-dim)" style={{ marginBottom: '12px', opacity: 0.5 }} />
              <div style={{ fontSize: '1rem', fontWeight: 600, color: '#f8fafc' }}>All caught up!</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                No notifications match your current filter.
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {filteredNotifications.map((notif) => {
                const isUnread = !notif.is_read
                const categoryColor =
                  notif.category === 'workflow'
                    ? '#f59e0b'
                    : notif.category === 'sales'
                    ? '#10b981'
                    : notif.category === 'inventory'
                    ? '#ec4899'
                    : notif.category === 'purchasing'
                    ? '#38bdf8'
                    : '#6366f1'

                return (
                  <div
                    key={notif.id}
                    id={`notification-card-${notif.id}`}
                    style={{
                      padding: '1.25rem',
                      borderRadius: '10px',
                      backgroundColor: isUnread ? 'rgba(30, 41, 59, 0.7)' : 'rgba(15, 23, 42, 0.4)',
                      border: '1px solid',
                      borderColor: isUnread ? 'rgba(99, 102, 241, 0.4)' : 'var(--border-subtle)',
                      boxShadow: isUnread ? '0 4px 18px rgba(0,0,0,0.2)' : 'none',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.5rem',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isUnread && (
                          <span
                            style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              backgroundColor: '#6366f1',
                              boxShadow: '0 0 8px #6366f1',
                              display: 'inline-block',
                            }}
                          />
                        )}
                        <span
                          style={{
                            fontSize: '0.725rem',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            backgroundColor: `${categoryColor}20`,
                            color: categoryColor,
                          }}
                        >
                          {notif.category}
                        </span>
                        <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                          {notif.title}
                        </h3>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Clock size={12} />
                          {new Date(notif.created_at).toLocaleString()}
                        </span>
                        {isUnread && (
                          <button
                            id={`mark-read-btn-${notif.id}`}
                            onClick={() => handleMarkAsRead(notif.id)}
                            title="Mark as read"
                            style={{
                              padding: '4px 8px',
                              borderRadius: '6px',
                              border: '1px solid var(--border-subtle)',
                              background: 'transparent',
                              color: 'var(--text-muted)',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Check size={12} /> Mark read
                          </button>
                        )}
                      </div>
                    </div>

                    <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5 }}>
                      {notif.message}
                    </p>

                    {notif.link && (
                      <div style={{ marginTop: '4px' }}>
                        <a
                          href={notif.link}
                          style={{
                            fontSize: '0.8rem',
                            color: '#38bdf8',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            textDecoration: 'none',
                          }}
                        >
                          View Related Record <ExternalLink size={12} />
                        </a>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Admin View: Outbox Dead-Letters (Worker failure state) */}
      {activeView === 'dead_letters' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              padding: '1rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#fca5a5',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <AlertTriangle size={20} color="#ef4444" />
            <div>
              <strong>Dead-Letter Event Monitoring:</strong> Outbox events that have failed after 8 retry attempts
              with exponential backoff are quarantined here to prevent worker blocking while preserving full event data.
            </div>
          </div>

          {loadingDeadLetters ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-dim)' }}>
              <RefreshCw size={24} className="spin" style={{ marginBottom: '8px' }} />
              <div>Loading dead-letter events...</div>
            </div>
          ) : deadLetters.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '4rem 2rem',
                backgroundColor: 'rgba(15, 23, 42, 0.3)',
                borderRadius: '12px',
                border: '1px dashed var(--border-subtle)',
              }}
            >
              <CheckCheck size={36} color="#10b981" style={{ marginBottom: '12px' }} />
              <div style={{ fontSize: '1rem', fontWeight: 600, color: '#f8fafc' }}>All event handlers healthy!</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                No events currently in dead-letter state (all processed or pending retry).
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {deadLetters.map((dl) => (
                <div
                  key={dl.id}
                  style={{
                    padding: '1.25rem',
                    borderRadius: '10px',
                    backgroundColor: 'rgba(30, 41, 59, 0.6)',
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.75rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="badge badge-rose">{dl.event_type}</span>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                        Aggregate: {dl.aggregate_type} #{dl.aggregate_id}
                      </span>
                      <span className="badge badge-amber">Attempts: {dl.attempts}</span>
                    </div>

                    <button
                      id={`retry-dl-btn-${dl.id}`}
                      onClick={() => handleRetryDeadLetter(dl.id)}
                      disabled={retryingId === dl.id}
                      className="btn btn-secondary"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', padding: '4px 10px' }}
                    >
                      <RotateCcw size={14} className={retryingId === dl.id ? 'spin' : ''} />
                      Retry Event
                    </button>
                  </div>

                  {dl.last_error && (
                    <div
                      style={{
                        padding: '8px 12px',
                        borderRadius: '6px',
                        backgroundColor: '#18181b',
                        fontFamily: 'monospace',
                        fontSize: '0.775rem',
                        color: '#f87171',
                        borderLeft: '3px solid #ef4444',
                      }}
                    >
                      {dl.last_error}
                    </div>
                  )}

                  <details style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>View Payload JSON</summary>
                    <pre
                      style={{
                        margin: '8px 0 0',
                        padding: '10px',
                        borderRadius: '6px',
                        backgroundColor: '#090d16',
                        color: '#94a3b8',
                        fontSize: '0.75rem',
                        overflowX: 'auto',
                      }}
                    >
                      {JSON.stringify(dl.payload, null, 2)}
                    </pre>
                  </details>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
