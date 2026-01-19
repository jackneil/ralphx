import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { listRuns, getRun, getProject } from '../api'
import { formatLocalFull } from '../utils/time'
import { useDashboardStore } from '../stores/dashboard'
import SessionTail from '../components/SessionTail'

interface Run {
  id: string
  project_id: string
  loop_name: string
  status: string
  iterations_completed: number
  items_processed: number
  started_at: string
  ended_at?: string
}

interface Session {
  session_id: string
  iteration: number
  mode?: string
  status: string
  started_at?: string
  duration_seconds?: number
}

export default function RunHistory() {
  const { slug } = useParams<{ slug: string }>()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Expanded run
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)

  // Session tail view
  const [viewingSession, setViewingSession] = useState<string | null>(null)

  const loadRuns = useCallback(async () => {
    if (!slug) return
    setLoading(true)
    setError(null)
    try {
      const result = await listRuns(slug)
      setRuns(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs')
    } finally {
      setLoading(false)
    }
  }, [slug])

  useEffect(() => {
    if (!slug) return

    async function loadProject() {
      try {
        const project = await getProject(slug!)
        setSelectedProject(project)
      } catch {
        // Ignore project load errors
      }
    }

    loadProject()
    loadRuns()
  }, [slug, setSelectedProject, loadRuns])

  const handleExpandRun = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null)
      setSessions([])
      return
    }

    setExpandedRunId(runId)
    setSessionsLoading(true)
    try {
      const run = await getRun(slug!, runId)
      setSessions(run.sessions)
    } catch {
      setSessions([])
    } finally {
      setSessionsLoading(false)
    }
  }

  const statusColors: Record<string, string> = {
    running: 'bg-green-900 text-green-300',
    completed: 'bg-blue-900 text-blue-300',
    stopped: 'bg-yellow-900 text-yellow-300',
    failed: 'bg-red-900 text-red-300',
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <Link to={`/projects/${slug}`} className="hover:text-white">
          {selectedProject?.name || slug}
        </Link>
        <span>/</span>
        <span className="text-white">Run History</span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-1">Run History</h1>
        <p className="text-gray-400">{runs.length} total runs</p>
      </div>

      {/* Session Tail Viewer */}
      {viewingSession && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Session Output</h3>
              <button
                onClick={() => setViewingSession(null)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <SessionTail
                projectSlug={slug!}
                sessionId={viewingSession}
                enabled={true}
              />
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400">
          {error}
        </div>
      )}

      {/* Runs Table */}
      {loading ? (
        <div className="text-gray-400">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-400">No runs yet</p>
          <p className="text-sm text-gray-500 mt-2">
            Start a loop to create run history
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {runs.map((run) => (
            <div key={run.id} className="card">
              {/* Run Header */}
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => handleExpandRun(run.id)}
              >
                <div className="flex items-center space-x-4">
                  <span className={`text-xs px-2 py-0.5 rounded ${statusColors[run.status] || 'bg-gray-600 text-gray-300'}`}>
                    {run.status}
                  </span>
                  <span className="font-medium text-white">{run.loop_name}</span>
                </div>
                <div className="flex items-center space-x-4 text-sm text-gray-400">
                  <span>{run.iterations_completed} iterations</span>
                  <span>{run.items_processed} items</span>
                  <span>{formatLocalFull(run.started_at)}</span>
                  <svg
                    className={`w-5 h-5 transition-transform ${expandedRunId === run.id ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>

              {/* Expanded Sessions */}
              {expandedRunId === run.id && (
                <div className="mt-4 pt-4 border-t border-gray-700">
                  {sessionsLoading ? (
                    <div className="text-gray-400 text-sm">Loading sessions...</div>
                  ) : sessions.length === 0 ? (
                    <div className="text-gray-500 text-sm">No sessions recorded</div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-sm font-medium text-gray-300 mb-2">Sessions</div>
                      {sessions.map((session) => (
                        <div
                          key={session.session_id}
                          className="flex items-center justify-between p-3 bg-gray-700 rounded"
                        >
                          <div className="flex items-center space-x-4">
                            <span className={`text-xs px-2 py-0.5 rounded ${statusColors[session.status] || 'bg-gray-600 text-gray-300'}`}>
                              {session.status}
                            </span>
                            <span className="text-sm text-gray-300">
                              Iteration {session.iteration}
                            </span>
                            {session.mode && (
                              <span className="text-sm text-gray-400">
                                Mode: {session.mode}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center space-x-4">
                            {session.duration_seconds !== undefined && (
                              <span className="text-sm text-gray-400">
                                {session.duration_seconds.toFixed(1)}s
                              </span>
                            )}
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setViewingSession(session.session_id)
                              }}
                              className="text-xs px-2 py-1 rounded bg-primary-600 text-white hover:bg-primary-500"
                            >
                              View Output
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Run Details */}
                  <div className="mt-4 pt-4 border-t border-gray-600 text-xs text-gray-500">
                    <div>Run ID: {run.id}</div>
                    {run.ended_at && (
                      <div>Ended: {formatLocalFull(run.ended_at)}</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
