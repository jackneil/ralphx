import { useEffect, useState, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { getLogs, getLogStats, LogEntry, LogFilters, LogStats } from '../api'
import { parseAsUTC } from '../utils/time'

const levelColors: Record<string, string> = {
  DEBUG: 'bg-gray-600 text-gray-300',
  INFO: 'bg-blue-600 text-blue-100',
  WARNING: 'bg-yellow-600 text-yellow-100',
  ERROR: 'bg-red-600 text-red-100',
}

const categoryColors: Record<string, string> = {
  system: 'text-gray-400',
  auth: 'text-purple-400',
  loop: 'text-green-400',
  run: 'text-blue-400',
  iteration: 'text-cyan-400',
}

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [levelFilter, setLevelFilter] = useState<string>('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [limit] = useState(100)
  const [offset, setOffset] = useState(0)

  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(false)

  // Expanded rows
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // Track refreshing state (when we already have logs and are fetching new ones)
  const [refreshing, setRefreshing] = useState(false)

  // Guard against concurrent fetches
  const fetchInProgressRef = useRef(false)

  // Track if this is the very first load (before any data exists)
  const isFirstLoadRef = useRef(true)

  const loadLogs = useCallback(async () => {
    // Prevent concurrent fetches (race condition guard)
    if (fetchInProgressRef.current) return
    fetchInProgressRef.current = true

    // Show appropriate loading state:
    // - First load ever: show "Loading logs..." (full loading state)
    // - Subsequent loads (filter changes, refresh): show subtle "Refreshing..." spinner
    if (isFirstLoadRef.current) {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    setError(null)
    try {
      const filters: LogFilters = { limit, offset }
      if (levelFilter) filters.level = levelFilter
      if (categoryFilter) filters.category = categoryFilter

      const [logsResult, statsResult] = await Promise.all([
        getLogs(filters),
        getLogStats(),
      ])
      setLogs(logsResult.logs)
      setStats(statsResult)
      isFirstLoadRef.current = false // Mark first load complete
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load logs')
    } finally {
      setLoading(false)
      setRefreshing(false)
      fetchInProgressRef.current = false
    }
  }, [levelFilter, categoryFilter, limit, offset])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  // Auto-refresh every 10 seconds
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(loadLogs, 10000)
    return () => clearInterval(interval)
  }, [autoRefresh, loadLogs])

  const formatTimestamp = (ts: string) => {
    const date = parseAsUTC(ts)
    return date.toLocaleString()
  }

  const formatTimeAgo = (ts: string) => {
    const seconds = Math.floor((Date.now() - parseAsUTC(ts).getTime()) / 1000)
    if (seconds < 60) return `${seconds}s ago`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <span className="text-white">Activity Log</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">Activity Log</h1>
          <p className="text-gray-400">
            {stats?.total ?? 0} total entries
            {stats?.recent_errors_24h ? (
              <span className="text-red-400 ml-2">
                ({stats.recent_errors_24h} errors in last 24h)
              </span>
            ) : null}
          </p>
        </div>

        <div className="flex items-center space-x-4">
          {/* Refreshing indicator */}
          {refreshing && (
            <span className="text-sm text-gray-400 flex items-center">
              <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Refreshing...
            </span>
          )}

          {/* Auto-refresh toggle */}
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="form-checkbox bg-gray-700 border-gray-600 text-primary-500 rounded"
            />
            <span className="text-gray-300 text-sm">Auto-refresh</span>
          </label>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card">
            <div className="text-2xl font-bold text-white">{stats.total}</div>
            <div className="text-sm text-gray-400">Total Entries</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-red-400">
              {stats.by_level['ERROR'] || 0}
            </div>
            <div className="text-sm text-gray-400">Errors</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-yellow-400">
              {stats.by_level['WARNING'] || 0}
            </div>
            <div className="text-sm text-gray-400">Warnings</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-blue-400">
              {stats.by_level['INFO'] || 0}
            </div>
            <div className="text-sm text-gray-400">Info</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-4 mb-4">
        <select
          value={levelFilter}
          onChange={(e) => { setLevelFilter(e.target.value); setOffset(0) }}
          className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
          aria-label="Filter by level"
        >
          <option value="">All Levels</option>
          <option value="ERROR">ERROR</option>
          <option value="WARNING">WARNING</option>
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
        </select>

        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setOffset(0) }}
          className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
          aria-label="Filter by category"
        >
          <option value="">All Categories</option>
          <option value="system">system</option>
          <option value="auth">auth</option>
          <option value="loop">loop</option>
          <option value="run">run</option>
          <option value="iteration">iteration</option>
        </select>

        <button
          onClick={() => loadLogs()}
          disabled={refreshing}
          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-white text-sm"
          aria-label="Refresh logs"
        >
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400">
          {error}
        </div>
      )}

      {/* Logs Table */}
      {loading && logs.length === 0 ? (
        <div className="text-gray-400">Loading logs...</div>
      ) : logs.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-400">No logs found</p>
          <p className="text-sm text-gray-500 mt-2">
            Activity will appear here as you use the system
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {logs.map((log) => (
            <div key={log.id} className="card !py-2">
              {/* Log Row */}
              <div
                role="button"
                tabIndex={0}
                aria-expanded={expandedId === log.id}
                aria-label={`${log.level} ${log.category || 'unknown'}.${log.event || 'unknown'}: ${log.message}`}
                className="flex items-center justify-between cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-opacity-50 rounded"
                onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setExpandedId(expandedId === log.id ? null : log.id)
                  }
                }}
              >
                <div className="flex items-center space-x-3 flex-1 min-w-0">
                  {/* Level badge */}
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${
                      levelColors[log.level] || 'bg-gray-600 text-gray-300'
                    }`}
                  >
                    {log.level}
                  </span>

                  {/* Category.Event */}
                  <span
                    className={`text-sm font-mono ${
                      categoryColors[log.category || ''] || 'text-gray-400'
                    }`}
                  >
                    {log.category || 'unknown'}.{log.event || 'unknown'}
                  </span>

                  {/* Message */}
                  <span className="text-sm text-gray-300 truncate">
                    {log.message}
                  </span>
                </div>

                <div className="flex items-center space-x-4 text-xs text-gray-500 ml-4">
                  <span title={formatTimestamp(log.timestamp)}>
                    {formatTimeAgo(log.timestamp)}
                  </span>
                  {log.metadata && (
                    <svg
                      className={`w-4 h-4 transition-transform ${
                        expandedId === log.id ? 'rotate-180' : ''
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === log.id && (
                <div className="mt-2 pt-2 border-t border-gray-700">
                  <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                    <div>
                      <span className="text-gray-500">Timestamp:</span>{' '}
                      {formatTimestamp(log.timestamp)}
                    </div>
                    {log.project_id && (
                      <div>
                        <span className="text-gray-500">Project:</span>{' '}
                        {log.project_id}
                      </div>
                    )}
                    {log.run_id && (
                      <div>
                        <span className="text-gray-500">Run:</span>{' '}
                        {log.run_id}
                      </div>
                    )}
                  </div>
                  {log.metadata && (
                    <div className="mt-2">
                      <span className="text-xs text-gray-500">Metadata:</span>
                      <pre className="mt-1 p-2 bg-gray-900 rounded text-xs text-gray-300 overflow-x-auto overflow-y-auto max-h-64">
                        {JSON.stringify(log.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {logs.length > 0 && (
        <div className="flex items-center justify-between mt-4">
          <div className="text-sm text-gray-400">
            Showing {offset + 1} - {offset + logs.length} of {stats?.total ?? logs.length}
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm text-white"
            >
              Previous
            </button>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={logs.length < limit}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm text-white"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
