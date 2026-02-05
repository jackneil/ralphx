import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  startIterationSession,
  streamIterationProgress,
  cancelIterationSession,
  completePlanningSession,
  getPlanningSession,
  listIterationSessions,
  getIterationEvents,
  getIterationDiff,
} from '../../api'
import type {
  IterationSession,
  IterationSSEEvent,
  IterationDiffResponse,
} from '../../api'
import PlanningSessionHistory from './PlanningSessionHistory'

interface PlanningIterationPanelProps {
  projectSlug: string
  workflowId: string
  stepId: number
  designDocPath?: string
  onComplete: () => void
}

interface ToolActivity {
  id: number
  tool: string
  input?: Record<string, unknown>
  result?: string
  status: 'running' | 'completed'
}

interface CompletedIteration {
  id?: number
  iteration: number
  summary: string
  chars_added: number
  chars_removed: number
}

export default function PlanningIterationPanel({
  projectSlug,
  workflowId,
  stepId,
  // designDocPath is available via props but the design doc is loaded from session artifacts
  onComplete,
}: PlanningIterationPanelProps) {
  // Prompt form state
  const [prompt, setPrompt] = useState('')
  const [iterations, setIterations] = useState(3)

  // Execution state
  const [session, setSession] = useState<IterationSession | null>(null)
  const [running, setRunning] = useState(false)
  const [currentIteration, setCurrentIteration] = useState(0)
  const [totalIterations, setTotalIterations] = useState(0)
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([])
  const [completedIterations, setCompletedIterations] = useState<CompletedIteration[]>([])
  const [error, setError] = useState<string | null>(null)

  // Design doc state
  const [designDoc, setDesignDoc] = useState<string | null>(null)

  // Session history refresh key
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)

  // Streaming content state (Claude's raw response text)
  const [streamingText, setStreamingText] = useState('')

  // Completing state
  const [completing, setCompleting] = useState(false)
  const [starting, setStarting] = useState(false)

  // Diff modal state
  const [diffData, setDiffData] = useState<IterationDiffResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)

  // Right panel: diff-first view
  const [rightPanelView, setRightPanelView] = useState<'diff' | 'full'>('diff')
  const [latestDiff, setLatestDiff] = useState<IterationDiffResponse | null>(null)
  const [latestDiffLoading, setLatestDiffLoading] = useState(false)
  const userSelectedTabRef = useRef(false)

  const toolIdCounter = useRef(0)
  const eventSourceRef = useRef<EventSource | null>(null)
  const currentIterationRef = useRef(0)
  const streamingTextRef = useRef<HTMLDivElement>(null)
  const lastEventIdRef = useRef(0)
  const mountedRef = useRef(true)
  const reconnectAttemptsRef = useRef(0)
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const MAX_RECONNECT_ATTEMPTS = 5

  const clearStaleTimer = useCallback(() => {
    if (staleTimerRef.current) {
      clearTimeout(staleTimerRef.current)
      staleTimerRef.current = null
    }
  }, [])

  const resetStaleTimer = useCallback(() => {
    clearStaleTimer()
    staleTimerRef.current = setTimeout(async () => {
      if (!mountedRef.current) return
      try {
        const sessions = await listIterationSessions(projectSlug, workflowId)
        const active = sessions.find(s => s.run_status === 'running')
        if (!active) {
          if (eventSourceRef.current) { eventSourceRef.current.close(); eventSourceRef.current = null }
          setRunning(false)
          setStarting(false)
          setHistoryRefreshKey(k => k + 1)
        }
      } catch { /* ignore */ }
    }, 90_000)
  }, [projectSlug, workflowId, clearStaleTimer])

  // Auto-fetch diff for the latest completed iteration
  useEffect(() => {
    const last = [...completedIterations].reverse().find(ci => ci.id)
    if (!last?.id || !session) return

    setLatestDiffLoading(true)
    getIterationDiff(projectSlug, workflowId, session.id, last.id)
      .then(data => {
        setLatestDiff(data)
        if (!userSelectedTabRef.current) {
          setRightPanelView('diff')
        }
      })
      .catch(() => {})
      .finally(() => setLatestDiffLoading(false))
  }, [completedIterations, session, projectSlug, workflowId])

  const connectToStream = useCallback((sessionId: string, afterEventId: number) => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = streamIterationProgress(
      projectSlug,
      workflowId,
      sessionId,
      afterEventId
    )
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const data: IterationSSEEvent = JSON.parse(event.data)
        if (data.type === 'heartbeat') return
        console.log('[SSE]', data.type, data)
        // Reset reconnect counter on successful data
        reconnectAttemptsRef.current = 0
        // Track last event ID for reconnection
        if (data._event_id) {
          lastEventIdRef.current = data._event_id
        }
        handleSSEEvent(data)
        resetStaleTimer()
      } catch {
        // Skip unparseable events
      }
    }

    resetStaleTimer()

    es.onerror = () => {
      // Try to reconnect after a brief delay
      es.close()
      eventSourceRef.current = null

      reconnectAttemptsRef.current += 1
      if (reconnectAttemptsRef.current > MAX_RECONNECT_ATTEMPTS) {
        setRunning(false)
        setStarting(false)
        setError('Lost connection to server after multiple retries')
        setHistoryRefreshKey(k => k + 1)
        return
      }

      // Check if session is still running before reconnecting
      setTimeout(async () => {
        if (!mountedRef.current) return
        try {
          const sessions = await listIterationSessions(projectSlug, workflowId)
          if (!mountedRef.current) return
          const active = sessions.find(s => s.run_status === 'running')
          if (active) {
            connectToStream(active.id, lastEventIdRef.current)
          } else {
            setRunning(false)
            setStarting(false)
            setHistoryRefreshKey(k => k + 1)
          }
        } catch {
          if (!mountedRef.current) return
          setRunning(false)
          setStarting(false)
        }
      }, 2000)
    }
  }, [projectSlug, workflowId, resetStaleTimer]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadExistingState = useCallback(async () => {
    try {
      // Try to load existing planning session (which has the design doc)
      const existingSession = await getPlanningSession(projectSlug, workflowId)
      if (existingSession?.artifacts?.design_doc) {
        setDesignDoc(existingSession.artifacts.design_doc)
      }
    } catch {
      // No existing session, that's fine
    }

    // Auto-reconnect to running session
    try {
      const sessions = await listIterationSessions(projectSlug, workflowId)
      const activeSession = sessions.find(s => s.run_status === 'running')
      if (activeSession) {
        const currentIter = activeSession.current_iteration ?? 0
        setSession({
          id: activeSession.id,
          workflow_id: workflowId,
          step_id: activeSession.step_id,
          prompt: activeSession.prompt || '',
          iterations_requested: activeSession.iterations_requested,
          iterations_completed: activeSession.iterations_completed,
          current_iteration: currentIter,
          run_status: 'running',
          is_legacy: false,
          status: 'active',
          created_at: activeSession.created_at,
          updated_at: activeSession.updated_at,
        } as IterationSession)
        setRunning(true)
        setTotalIterations(activeSession.iterations_requested)
        setCurrentIteration(currentIter)
        currentIterationRef.current = currentIter

        // Restore completed iterations from session data to avoid duplicates on replay
        const restored: CompletedIteration[] = activeSession.iterations
          .filter(it => it.status === 'completed')
          .map(it => ({
            id: it.id,
            iteration: it.iteration_number,
            summary: it.summary || 'Updated design document',
            chars_added: it.chars_added,
            chars_removed: it.chars_removed,
          }))
        setCompletedIterations(restored)

        // Get last event ID from REST to avoid replaying all events
        try {
          const events = await getIterationEvents(projectSlug, workflowId, activeSession.id)
          if (events.length > 0) {
            lastEventIdRef.current = events[events.length - 1].id
          }
        } catch {
          // Fall back to streaming from beginning
        }

        connectToStream(activeSession.id, lastEventIdRef.current)
      }
    } catch {
      // Ignore
    }
  }, [projectSlug, workflowId, connectToStream])

  // Load existing session on mount
  useEffect(() => {
    loadExistingState()
  }, [loadExistingState])

  // Cleanup EventSource on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  // Auto-scroll streaming text to bottom as content arrives
  useEffect(() => {
    if (streamingTextRef.current) {
      streamingTextRef.current.scrollTop = streamingTextRef.current.scrollHeight
    }
  }, [streamingText])

  const handleStartIterations = async () => {
    if (!prompt.trim() || starting) return

    setStarting(true)
    setError(null)
    setToolActivities([])
    setCompletedIterations([])
    setStreamingText('')
    setLatestDiff(null)
    userSelectedTabRef.current = false

    try {
      // Start the iteration session
      const newSession = await startIterationSession(
        projectSlug,
        workflowId,
        prompt.trim(),
        iterations
      )
      setSession(newSession)
      setRunning(true)
      setTotalIterations(iterations)
      setCurrentIteration(0)
      lastEventIdRef.current = 0
      reconnectAttemptsRef.current = 0

      // Connect to SSE stream (DB-polling based, supports reconnection)
      connectToStream(newSession.id, 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start iterations')
      setRunning(false)
      setStarting(false)
    }
  }

  const handleSSEEvent = (data: IterationSSEEvent) => {
    switch (data.type) {
      case 'iteration_start':
        currentIterationRef.current = data.iteration || 0
        setCurrentIteration(data.iteration || 0)
        setTotalIterations(data.total || 0)
        setToolActivities([]) // Clear tools for new iteration
        setStreamingText('') // Clear streaming text for new iteration
        break

      case 'content':
        // Claude's response text — append to streaming display
        if (data.text) {
          setStreamingText(prev => prev + data.text)
        }
        break

      case 'tool_use':
        setToolActivities(prev => [
          ...prev,
          {
            id: ++toolIdCounter.current,
            tool: data.tool || 'unknown',
            input: data.input,
            status: 'running',
          },
        ])
        break

      case 'tool_result':
        setToolActivities(prev =>
          prev.map(t =>
            t.status === 'running' && t.tool === data.tool
              ? { ...t, result: data.result, status: 'completed' as const }
              : t
          )
        )
        break

      case 'design_doc_updated':
        // Reload design doc from session after update
        // Always attempt reload - don't depend on stale `session` closure
        getPlanningSession(projectSlug, workflowId)
          .then(s => {
            if (s?.artifacts?.design_doc) {
              setDesignDoc(s.artifacts.design_doc)
            }
          })
          .catch(() => {})
        // Record the update in the iteration (use ref for current value)
        setCompletedIterations(prev => {
          const last = prev[prev.length - 1]
          if (last && last.iteration === currentIterationRef.current) {
            return [
              ...prev.slice(0, -1),
              {
                ...last,
                chars_added: data.chars_added || 0,
                chars_removed: data.chars_removed || 0,
              },
            ]
          }
          return prev
        })
        break

      case 'iteration_complete':
        setCompletedIterations(prev => [
          ...prev,
          {
            id: data.iteration_id,
            iteration: data.iteration || currentIterationRef.current,
            summary: data.summary || 'Updated design document',
            chars_added: 0,
            chars_removed: 0,
          },
        ])
        break

      case 'error':
        if (data.fatal) {
          clearStaleTimer()
          setError(data.message || 'Execution failed')
          setRunning(false)
          setStarting(false)
        }
        break

      case 'cancelled':
        clearStaleTimer()
        setRunning(false)
        setStarting(false)
        setHistoryRefreshKey(k => k + 1)
        break

      case 'done':
        clearStaleTimer()
        setRunning(false)
        setStarting(false)
        // Reload design doc and history
        loadExistingState()
        setHistoryRefreshKey(k => k + 1)
        break
    }
  }

  const handleCancel = async () => {
    if (!session) return

    try {
      await cancelIterationSession(projectSlug, workflowId, session.id)
    } catch {
      // Force close the event source
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setRunning(false)
    setStarting(false)
  }

  const handleCompleteStep = async () => {
    if (!designDoc || completing) return

    setCompleting(true)
    try {
      await completePlanningSession(projectSlug, workflowId, {
        design_doc: designDoc,
      })
      onComplete()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete step')
    } finally {
      setCompleting(false)
    }
  }

  const handleViewDiff = async (ci: CompletedIteration) => {
    if (!ci.id || !session) return
    setDiffLoading(true)
    try {
      const data = await getIterationDiff(projectSlug, workflowId, session.id, ci.id)
      setDiffData(data)
    } catch {
      // Diff may not be available for old iterations — show empty-state modal
      setDiffData({
        iteration_id: ci.id,
        iteration_number: ci.iteration,
        diff_text: null,
        chars_added: 0,
        chars_removed: 0,
        diff_lines: [],
      })
    } finally {
      setDiffLoading(false)
    }
  }

  const getDiffLineClass = (type: string) => {
    switch (type) {
      case 'add': return 'bg-green-900/30 text-green-300'
      case 'remove': return 'bg-red-900/30 text-red-300'
      case 'hunk': return 'bg-blue-900/30 text-blue-300'
      default: return 'text-gray-400'
    }
  }

  const progressPercent = totalIterations > 0
    ? Math.round((completedIterations.length / totalIterations) * 100)
    : 0

  return (
    <div className="planning-iteration-panel" style={{ display: 'flex', gap: '1.5rem' }}>
      {/* Left Panel: Prompt + Progress + History */}
      <div style={{ flex: '0 0 400px', display: 'flex', flexDirection: 'column', gap: '1rem', overflow: 'hidden' }}>
        {/* Prompt Form */}
        <div className="card" style={{ padding: '1rem' }}>
          <h3 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem', fontWeight: 600 }}>
            What should Claude focus on?
          </h3>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Describe the design document you want to create or refine. E.g., 'Research authentication approaches and create a design doc for a JWT-based auth system with refresh tokens.'"
            disabled={running}
            style={{
              width: '100%',
              minHeight: '120px',
              padding: '0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color, #ddd)',
              fontFamily: 'inherit',
              fontSize: '0.875rem',
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />

          <div style={{ margin: '0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <label style={{ fontSize: '0.85rem', fontWeight: 500, whiteSpace: 'nowrap' }}>
              Iterations:
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={iterations}
              onChange={e => setIterations(parseInt(e.target.value))}
              disabled={running}
              style={{ flex: 1 }}
            />
            <span style={{
              fontSize: '0.85rem',
              fontWeight: 600,
              minWidth: '20px',
              textAlign: 'center',
            }}>
              {iterations}
            </span>
          </div>

          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #888)', marginBottom: '0.75rem' }}>
            {iterations === 1 ? 'Quick single pass' :
             iterations <= 3 ? 'Good for focused refinement' :
             iterations <= 6 ? 'Thorough research and iteration' :
             'Comprehensive deep dive'}
          </div>

          <button
            onClick={handleStartIterations}
            disabled={!prompt.trim() || running || starting}
            className="btn btn-primary"
            style={{ width: '100%' }}
          >
            {starting ? 'Starting...' : running ? 'Running...' : `Run ${iterations} Iteration${iterations !== 1 ? 's' : ''}`}
          </button>
        </div>

        {/* Execution Progress */}
        {running && (
          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                Iteration {currentIteration} of {totalIterations}
              </span>
              <button
                onClick={handleCancel}
                className="btn btn-sm"
                style={{
                  fontSize: '0.75rem',
                  padding: '0.25rem 0.5rem',
                  background: 'var(--danger-bg, #fee)',
                  color: 'var(--danger-color, #c00)',
                  border: '1px solid var(--danger-border, #fcc)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>

            {/* Progress bar */}
            <div style={{
              height: '6px',
              background: 'var(--bg-secondary, #f0f0f0)',
              borderRadius: '3px',
              overflow: 'hidden',
              marginBottom: '0.75rem',
            }}>
              <div style={{
                height: '100%',
                width: `${progressPercent}%`,
                background: 'var(--primary-color, #0066cc)',
                borderRadius: '3px',
                transition: 'width 0.3s ease',
              }} />
            </div>

            {/* Tool Activity */}
            {toolActivities.length > 0 && (
              <div style={{ marginBottom: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem', color: 'var(--text-muted, #888)' }}>
                  Tool Activity
                </div>
                <div style={{ maxHeight: '150px', overflow: 'auto' }}>
                  {toolActivities.map(t => (
                    <div key={t.id} style={{
                      fontSize: '0.75rem',
                      padding: '0.2rem 0',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}>
                      <span>{t.status === 'completed' ? '\u2713' : '\u25CF'}</span>
                      <span style={{ fontWeight: 500 }}>{t.tool}</span>
                      {t.input && (
                        <span style={{ color: 'var(--text-muted, #888)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {typeof t.input === 'object' ? JSON.stringify(t.input).slice(0, 60) : String(t.input).slice(0, 60)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Streaming Claude Response */}
            {streamingText && (
              <div style={{ marginBottom: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem', color: 'var(--text-muted, #888)' }}>
                  Claude Response
                </div>
                <div
                  ref={streamingTextRef}
                  className="prose prose-invert prose-xs max-w-none"
                  style={{
                    maxHeight: '200px',
                    overflow: 'auto',
                    padding: '0.5rem',
                    background: 'var(--bg-secondary, #1e2028)',
                    color: 'var(--text-primary, #e0e0e0)',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    lineHeight: 1.5,
                  }}>
                  <ReactMarkdown>{streamingText}</ReactMarkdown>
                </div>
              </div>
            )}

            {/* Completed iterations */}
            {completedIterations.length > 0 && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem', color: 'var(--text-muted, #888)' }}>
                  Completed
                </div>
                {completedIterations.map(ci => (
                  <div key={ci.iteration} style={{
                    fontSize: '0.75rem',
                    padding: '0.2rem 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}>
                    <span style={{ color: 'green' }}>{'\u2713'}</span>
                    <span>Iteration {ci.iteration}</span>
                    {ci.chars_added > 0 && (
                      <span style={{ color: 'green' }}>+{ci.chars_added}</span>
                    )}
                    {ci.chars_removed > 0 && (
                      <span style={{ color: 'red' }}>-{ci.chars_removed}</span>
                    )}
                    {ci.id && (
                      <button
                        onClick={() => handleViewDiff(ci)}
                        disabled={diffLoading}
                        style={{
                          fontSize: '0.7rem',
                          padding: '0.1rem 0.4rem',
                          background: 'var(--bg-secondary, #2a2a3a)',
                          color: 'var(--text-muted, #888)',
                          border: '1px solid var(--border-color, #444)',
                          borderRadius: '3px',
                          cursor: 'pointer',
                          marginLeft: 'auto',
                        }}
                      >
                        View Diff
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="card" style={{
            padding: '0.75rem',
            background: 'var(--danger-bg, #fee)',
            border: '1px solid var(--danger-border, #fcc)',
            color: 'var(--danger-color, #c00)',
            fontSize: '0.85rem',
          }}>
            {error}
          </div>
        )}

        {/* Complete Step Button */}
        {designDoc && !running && (
          <button
            onClick={handleCompleteStep}
            disabled={completing || running}
            className="btn btn-success"
            style={{ width: '100%' }}
          >
            {completing ? 'Completing...' : 'Complete Planning Step'}
          </button>
        )}

        {/* Session History */}
        <PlanningSessionHistory
          projectSlug={projectSlug}
          workflowId={workflowId}
          stepId={stepId}
          refreshKey={historyRefreshKey}
          onClonePrompt={(p, iters) => {
            if (prompt.trim() && !confirm('Replace current prompt?')) return
            setPrompt(p)
            setIterations(Math.max(1, iters || 3))
          }}
          cloneDisabled={running}
        />
      </div>

      {/* Right Panel: Design Doc Preview */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="card" style={{ padding: '1rem', height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600 }}>
              Design Document
            </h3>
            {designDoc && (
              <div style={{ display: 'flex', gap: '2px', background: 'var(--bg-secondary, #1e2028)', borderRadius: '6px', padding: '2px' }}>
                <button
                  onClick={() => { userSelectedTabRef.current = true; setRightPanelView('diff') }}
                  style={{
                    padding: '0.25rem 0.6rem',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    borderRadius: '4px',
                    border: 'none',
                    cursor: 'pointer',
                    background: rightPanelView === 'diff' ? 'var(--primary-color, #0891b2)' : 'transparent',
                    color: rightPanelView === 'diff' ? '#fff' : 'var(--text-muted, #888)',
                  }}
                >
                  Latest Changes
                </button>
                <button
                  onClick={() => { userSelectedTabRef.current = true; setRightPanelView('full') }}
                  style={{
                    padding: '0.25rem 0.6rem',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    borderRadius: '4px',
                    border: 'none',
                    cursor: 'pointer',
                    background: rightPanelView === 'full' ? 'var(--primary-color, #0891b2)' : 'transparent',
                    color: rightPanelView === 'full' ? '#fff' : 'var(--text-muted, #888)',
                  }}
                >
                  Full Document
                </button>
              </div>
            )}
          </div>

          {designDoc ? (
            rightPanelView === 'diff' ? (
              <div style={{ flex: 1, overflow: 'auto' }}>
                {latestDiffLoading ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem', color: 'var(--text-muted, #888)' }}>
                    <div className="animate-spin" style={{ width: '16px', height: '16px', border: '2px solid var(--text-muted, #888)', borderTopColor: 'transparent', borderRadius: '50%', marginRight: '0.5rem' }} />
                    Loading diff...
                  </div>
                ) : latestDiff && latestDiff.diff_lines.length > 0 ? (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                      <span style={{ color: 'var(--text-muted, #888)' }}>Iteration {latestDiff.iteration_number}</span>
                      {latestDiff.chars_added > 0 && <span style={{ color: '#4ade80' }}>+{latestDiff.chars_added} chars</span>}
                      {latestDiff.chars_removed > 0 && <span style={{ color: '#f87171' }}>-{latestDiff.chars_removed} chars</span>}
                    </div>
                    <div style={{ background: 'var(--bg-secondary, #1e2028)', borderRadius: '6px', overflow: 'hidden' }}>
                      <pre style={{ margin: 0, fontSize: '0.75rem', fontFamily: 'monospace', lineHeight: 1.6 }}>
                        {latestDiff.diff_lines.map((dl, idx) => (
                          <div key={idx} className={`px-3 py-0.5 ${getDiffLineClass(dl.type)}`}>
                            {dl.line}
                          </div>
                        ))}
                      </pre>
                    </div>
                  </div>
                ) : latestDiff && latestDiff.diff_text === null ? (
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted, #888)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                    Diff not recorded for this iteration. Future iterations include diffs automatically.
                  </div>
                ) : (
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted, #888)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                    No changes yet. Run iterations to see a diff.
                  </div>
                )}
              </div>
            ) : (
              <div style={{
                flex: 1,
                overflow: 'auto',
                padding: '0.75rem',
                background: 'var(--bg-secondary, #f8f9fa)',
                borderRadius: '6px',
                fontFamily: 'monospace',
                fontSize: '0.8rem',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {designDoc}
              </div>
            )
          ) : (
            <div style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted, #888)',
              fontSize: '0.9rem',
              fontStyle: 'italic',
            }}>
              No design document yet. Enter a prompt and run iterations to create one.
            </div>
          )}
        </div>
      </div>

      {/* Diff Modal */}
      {diffData && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
          onClick={() => setDiffData(null)}
        >
          <div
            className="bg-gray-800 rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div>
                <h3 className="text-lg font-semibold text-white">
                  Iteration {diffData.iteration_number} Diff
                </h3>
                <p className="text-sm text-gray-400 mt-0.5">
                  {diffData.chars_added > 0 && (
                    <span className="text-green-400 mr-2">+{diffData.chars_added} chars</span>
                  )}
                  {diffData.chars_removed > 0 && (
                    <span className="text-red-400">-{diffData.chars_removed} chars</span>
                  )}
                </p>
              </div>
              <button
                onClick={() => setDiffData(null)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {diffData.diff_lines.length > 0 ? (
                <pre className="text-xs font-mono leading-relaxed">
                  {diffData.diff_lines.map((dl, idx) => (
                    <div key={idx} className={`px-2 py-0.5 ${getDiffLineClass(dl.type)}`}>
                      {dl.line}
                    </div>
                  ))}
                </pre>
              ) : (
                <div className="text-gray-500 text-center py-8">
                  {diffData.diff_text === null
                    ? 'Diff not recorded for this iteration. Future iterations include diffs automatically.'
                    : 'No changes in this iteration'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
