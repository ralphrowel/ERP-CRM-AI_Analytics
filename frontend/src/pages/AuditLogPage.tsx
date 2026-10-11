import React, { useEffect, useState } from 'react';
import { auditApi, type AuditLogItem } from '../api/audit';

export const AuditLogPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(20);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedAction, setSelectedAction] = useState<string>('');
  const [selectedEntityType, setSelectedEntityType] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  // Diff inspection modal
  const [activeModalItem, setActiveModalItem] = useState<AuditLogItem | null>(null);

  useEffect(() => {
    fetchLogs();
  }, [page, selectedAction, selectedEntityType, dateFrom, dateTo]);

  const fetchLogs = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await auditApi.listLogs({
        action: selectedAction || undefined,
        entity_type: selectedEntityType || undefined,
        date_from: dateFrom ? `${dateFrom}T00:00:00Z` : undefined,
        date_to: dateTo ? `${dateTo}T23:59:59Z` : undefined,
        page,
        page_size: pageSize,
      });
      setLogs(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  };

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'create':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">create</span>;
      case 'update':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800">update</span>;
      case 'transition':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-800">transition</span>;
      case 'login':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">login</span>;
      case 'login_failed':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800">login_failed</span>;
      case 'logout':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-800">logout</span>;
      case 'permission_change':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800">permission_change</span>;
      case 'export':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-cyan-100 text-cyan-800">export</span>;
      case 'ai_tool_call':
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-violet-100 text-violet-800">ai_tool_call</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-800">{action}</span>;
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">System Audit Log</h1>
          <p className="text-sm text-gray-500 mt-1">
            Immutable, append-only security and operational audit trail with field-level diffs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchLogs()}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition shadow-sm"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Action Filter</label>
          <select
            value={selectedAction}
            onChange={(e) => {
              setSelectedAction(e.target.value);
              setPage(1);
            }}
            className="w-full text-sm border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          >
            <option value="">All Actions</option>
            <option value="create">create</option>
            <option value="update">update</option>
            <option value="transition">transition</option>
            <option value="login">login</option>
            <option value="login_failed">login_failed</option>
            <option value="logout">logout</option>
            <option value="permission_change">permission_change</option>
            <option value="export">export</option>
            <option value="ai_tool_call">ai_tool_call</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Entity Type</label>
          <input
            type="text"
            placeholder="e.g. customer, sales_order..."
            value={selectedEntityType}
            onChange={(e) => {
              setSelectedEntityType(e.target.value);
              setPage(1);
            }}
            className="w-full text-sm border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Date From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              setPage(1);
            }}
            className="w-full text-sm border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Date To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setPage(1);
            }}
            className="w-full text-sm border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-gray-500 flex items-center justify-center gap-2">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600"></div>
            Loading audit records...
          </div>
        ) : error ? (
          <div className="p-6 text-red-600 bg-red-50 text-sm">{error}</div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-gray-400 text-sm">
            No audit records match the current filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
              <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Entity</th>
                  <th className="px-4 py-3">Entity ID</th>
                  <th className="px-4 py-3">Actor</th>
                  <th className="px-4 py-3">Changes / Details</th>
                  <th className="px-4 py-3">IP / Request</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {logs.map((log) => {
                  const numChanges = Object.keys(log.changes || {}).length;
                  return (
                    <tr key={log.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-gray-500 font-mono">
                        {formatTimestamp(log.occurred_at)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {getActionBadge(log.action)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-gray-900 capitalize">
                        {log.entity_type}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-600 font-mono text-xs">
                        {log.entity_id ?? '—'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {log.actor_name ? (
                          <div>
                            <div className="font-medium text-gray-800 text-xs">{log.actor_name}</div>
                            {log.actor_email && (
                              <div className="text-[11px] text-gray-400">{log.actor_email}</div>
                            )}
                          </div>
                        ) : log.actor_user_id ? (
                          <span className="text-gray-500 text-xs">User #{log.actor_user_id}</span>
                        ) : (
                          <span className="text-gray-400 text-xs italic">System</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {numChanges > 0 ? (
                          <button
                            onClick={() => setActiveModalItem(log)}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition"
                          >
                            <span>Inspect {numChanges} field {numChanges === 1 ? 'change' : 'changes'}</span>
                            <span className="text-xs">→</span>
                          </button>
                        ) : log.context && Object.keys(log.context).length > 0 ? (
                          <button
                            onClick={() => setActiveModalItem(log)}
                            className="text-xs text-indigo-600 hover:underline"
                          >
                            View Metadata
                          </button>
                        ) : (
                          <span className="text-gray-400 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-gray-400 font-mono">
                        <div>{log.ip_address || '—'}</div>
                        {log.request_id && (
                          <div className="text-[10px] text-gray-400 truncate max-w-[120px]" title={log.request_id}>
                            {log.request_id}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
          <div>
            Showing <span className="font-semibold">{logs.length}</span> of{' '}
            <span className="font-semibold">{total}</span> records
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Previous
            </button>
            <span>
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Field Changes Modal */}
      {activeModalItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-fadeIn">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
              <div>
                <h3 className="font-semibold text-gray-900">
                  Audit Details: #{activeModalItem.id} ({activeModalItem.action})
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Entity: <span className="capitalize font-medium text-gray-700">{activeModalItem.entity_type}</span>{' '}
                  (ID: {activeModalItem.entity_id}) • {formatTimestamp(activeModalItem.occurred_at)}
                </p>
              </div>
              <button
                onClick={() => setActiveModalItem(null)}
                className="text-gray-400 hover:text-gray-600 text-lg font-bold p-1"
              >
                ✕
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4 text-sm">
              {/* Changes */}
              {activeModalItem.changes && Object.keys(activeModalItem.changes).length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                    Attribute Changes (Before → After)
                  </h4>
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200 text-xs">
                      <thead className="bg-gray-50 text-gray-600 font-semibold">
                        <tr>
                          <th className="px-3 py-2 text-left">Field</th>
                          <th className="px-3 py-2 text-left text-red-700">Before</th>
                          <th className="px-3 py-2 text-left text-emerald-700">After</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 font-mono">
                        {Object.entries(activeModalItem.changes).map(([field, [before, after]]) => (
                          <tr key={field} className="hover:bg-gray-50">
                            <td className="px-3 py-2 font-semibold text-gray-700">{field}</td>
                            <td className="px-3 py-2 text-red-600 bg-red-50/50">
                              {before === null ? 'null' : String(before)}
                            </td>
                            <td className="px-3 py-2 text-emerald-600 bg-emerald-50/50 font-bold">
                              {after === null ? 'null' : String(after)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Context / Metadata */}
              {activeModalItem.context && Object.keys(activeModalItem.context).length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                    Context Metadata
                  </h4>
                  <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs font-mono text-gray-700 overflow-x-auto">
                    {JSON.stringify(activeModalItem.context, null, 2)}
                  </pre>
                </div>
              )}

              {/* Actor & Request Details */}
              <div>
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                  Request Metadata
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs bg-gray-50 border border-gray-200 rounded p-3">
                  <div>
                    <span className="text-gray-500 font-medium">Actor ID:</span>{' '}
                    <span className="font-mono text-gray-800">{activeModalItem.actor_user_id ?? 'System'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 font-medium">Actor Email:</span>{' '}
                    <span className="text-gray-800">{activeModalItem.actor_email ?? '—'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 font-medium">IP Address:</span>{' '}
                    <span className="font-mono text-gray-800">{activeModalItem.ip_address ?? '—'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 font-medium">Request ID:</span>{' '}
                    <span className="font-mono text-gray-800">{activeModalItem.request_id ?? '—'}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-3 border-t border-gray-200 bg-gray-50 flex justify-end">
              <button
                onClick={() => setActiveModalItem(null)}
                className="px-4 py-1.5 bg-gray-800 hover:bg-gray-900 text-white rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
