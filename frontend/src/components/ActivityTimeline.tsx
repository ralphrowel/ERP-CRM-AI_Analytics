import React, { useEffect, useState } from 'react';
import { auditApi, type ActivityFeedItem } from '../api/audit';

interface ActivityTimelineProps {
  entityType: string;
  entityId: number;
}

export const ActivityTimeline: React.FC<ActivityTimelineProps> = ({ entityType, entityId }) => {
  const [items, setItems] = useState<ActivityFeedItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFeed();
  }, [entityType, entityId]);

  const fetchFeed = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await auditApi.getEntityFeed(entityType, entityId, 50, 0);
      setItems(res.items);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load activity feed');
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  const getSourceBadge = (source: ActivityFeedItem['source']) => {
    switch (source) {
      case 'status_history':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-purple-100 text-purple-800">State Transition</span>;
      case 'activity':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-100 text-blue-800">CRM Activity</span>;
      case 'audit_log':
      default:
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-100 text-amber-800">Audit Change</span>;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 text-gray-500">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600 mr-2"></div>
        Loading activity feed...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded-lg text-sm flex items-center justify-between">
        <span>{error}</span>
        <button
          onClick={fetchFeed}
          className="underline font-medium hover:text-red-900"
        >
          Retry
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 text-sm">
        No recorded activities or audit changes for this {entityType}.
      </div>
    );
  }

  return (
    <div className="flow-root">
      <ul className="-mb-8">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;
          return (
            <li key={item.id}>
              <div className="relative pb-8">
                {!isLast && (
                  <span
                    className="absolute top-4 left-4 -ml-px h-full w-0.5 bg-gray-200"
                    aria-hidden="true"
                  />
                )}
                <div className="relative flex space-x-3">
                  <div>
                    <span className="h-8 w-8 rounded-full bg-indigo-50 border border-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-700">
                      {item.source === 'status_history' ? '⇄' : item.source === 'activity' ? '✓' : '✎'}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                        <span>{item.title}</span>
                        {getSourceBadge(item.source)}
                      </div>
                      <time className="text-xs text-gray-400">
                        {formatTimestamp(item.timestamp)}
                      </time>
                    </div>

                    <p className="mt-0.5 text-xs text-gray-600">
                      {item.summary}
                    </p>

                    {item.actor_name && (
                      <p className="mt-0.5 text-xs text-gray-400">
                        By <span className="font-medium text-gray-600">{item.actor_name}</span> {item.actor_email ? `(${item.actor_email})` : ''}
                      </p>
                    )}

                    {/* Diff changes if present */}
                    {item.changes && Object.keys(item.changes).length > 0 && (
                      <div className="mt-2 bg-gray-50 border border-gray-200 rounded p-2 text-xs">
                        <span className="font-semibold text-gray-700 block mb-1">Field Changes:</span>
                        <div className="grid grid-cols-1 gap-1">
                          {Object.entries(item.changes).map(([field, [oldVal, newVal]]) => (
                            <div key={field} className="flex items-center gap-2 font-mono text-[11px]">
                              <span className="text-gray-500 font-semibold">{field}:</span>
                              <span className="line-through text-red-600">{oldVal === null ? 'null' : String(oldVal)}</span>
                              <span className="text-gray-400">→</span>
                              <span className="text-green-600 font-bold">{newVal === null ? 'null' : String(newVal)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
