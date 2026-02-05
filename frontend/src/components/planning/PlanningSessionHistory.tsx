import { useState, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  listIterationSessions,
  getPlanningSessionDetail,
  getIterationEvents,
  getIterationDiff,
} from '../../api'
import type { IterationSessionSummary, PlanningSessionDetail, IterationEvent, IterationDiffResponse } from '../../api'

interface PlanningSessionHistoryProps {
  projectSlug: string
  workflowId: string
  stepId: number
  refreshKey?: number
  onClonePrompt?: (prompt: string, iterations: number) => void
  cloneDisabled?: boolean
}

const EVENT_STYLES: Record<string, { icon: string; color: string }> = {
  tool_use: { icon: '\u2699', color: 'text-blue-400' },
  tool_result: { icon: '\u2713', color: 'text-green-400' },
  content: { icon: '\u270E', color: 'text-gray-400' },
  iteration_start: { icon: '\u25B6', color: 'text-cyan-400' },
  iteration_complete: { icon: '\u2714', color: 'text-green-400' },
  error: { icon: '\u2717', color: 'text-red-400' },
}

export default function PlanningSessionHistory({
  projectSlug,
  workflowId,
  stepId,
  refreshKey,
  onClonePrompt,
  cloneDisabled,
}: PlanningSessionHistoryProps) {
  const [sessions, setSessions] = useState<IterationSessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSession, setExpandedSession] = useState<string | null>(null)
  const [legacyDetail, setLegacyDetail] = useState<PlanningSessionDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [expandedMessages, setExpandedMessages] = useState<Set<number>>(new Set())

  // Event state
  const [sessionEvents, setSessionEvents] = useState<IterationEvent[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [expandedIterations, setExpandedIterations] = useState<Set<number>>(new Set())
  const [expandedEventIds, setExpandedEventIds] = useState<Set<number>>(new Set())

  // Diff modal state
  const [diffData, setDiffData] = useState<IterationDiffResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listIterationSessions(projectSlug, workflowId)
      // Filter to only sessions for this step
      const stepSessions = data.filter(s => s.step_id === stepId)
      setSessions(stepSessions)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, workflowId, stepId])

  useEffect(() => {
    loadSessions()
  }, [loadSessions, refreshKey])

  const handleExpandSession = async (session: IterationSessionSummary) => {
    if (expandedSession === session.id) {
      setExpandedSession(null)
      setLegacyDetail(null)
      setExpandedMessages(new Set())
      setSessionEvents([])
      setEventsError(null)
      setExpandedIterations(new Set())
      setExpandedEventIds(new Set())
      return
    }

    setExpandedSession(session.id)
    setExpandedMessages(new Set())
    setSessionEvents([])
    setEventsError(null)
    setExpandedIterations(new Set())
    setExpandedEventIds(new Set())

    if (session.is_legacy) {
      // For legacy sessions, load full message detail
      setLoadingDetail(true)
      try {
        const detail = await getPlanningSessionDetail(projectSlug, workflowId, session.id)
        setLegacyDetail(detail)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load session detail')
      } finally {
        setLoadingDetail(false)
      }
    } else {
      // For iteration sessions, load events
      setLoadingEvents(true)
      try {
        const events = await getIterationEvents(projectSlug, workflowId, session.id)
        setSessionEvents(events)
      } catch (err) {
        setEventsError(err instanceof Error ? err.message : 'Failed to load events')
      } finally {
        setLoadingEvents(false)
      }
    }
  }

  const formatRelativeTime = (dateStr: string) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return 'Unknown'
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return 'just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const toggleIteration = (iterNum: number) => {
    setExpandedIterations(prev => {
      const next = new Set(prev)
      if (next.has(iterNum)) next.delete(iterNum)
      else next.add(iterNum)
      return next
    })
  }

  const toggleEvent = (eventId: number) => {
    setExpandedEventIds(prev => {
      const next = new Set(prev)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }

  const formatToolInput = (raw?: string): string => {
    if (!raw) return ''
    try {
      return JSON.stringify(JSON.parse(raw), null, 2)
    } catch {
      return raw
    }
  }

  const getEventStyle = (eventType: string) => {
    return EVENT_STYLES[eventType] || { icon: '\u25CF', color: 'text-gray-500' }
  }

  const getEventLabel = (event: IterationEvent) => {
    const style = getEventStyle(event.event_type)
    if (event.event_type === 'tool_use') return `${style.icon} ${event.tool_name || 'tool'}`
    if (event.event_type === 'tool_result') return `${style.icon} ${event.tool_name || 'result'}`
    if (event.event_type === 'content') return `${style.icon} content`
    if (event.event_type === 'iteration_start') return `${style.icon} iter ${event.iteration_number}`
    if (event.event_type === 'iteration_complete') return `${style.icon} iter ${event.iteration_number} done`
    if (event.event_type === 'error') return `${style.icon} error`
    return `${style.icon} ${event.event_type}`
  }

  const handleViewDiff = async (sessionId: string, iterationId: number, iterationNumber?: number) => {
    setDiffLoading(true)
    try {
      const data = await getIterationDiff(projectSlug, workflowId, sessionId, iterationId)
      setDiffData(data)
    } catch {
      // Diff may not be available for old iterations — show empty-state modal
      setDiffData({
        iteration_id: iterationId,
        iteration_number: iterationNumber ?? 0,
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

  // Group events by iteration number
  const groupEventsByIteration = (events: IterationEvent[]) => {
    const groups: Map<number, IterationEvent[]> = new Map()
    let currentIter = 0
    for (const ev of events) {
      if (ev.event_type === 'iteration_start' && ev.iteration_number) {
        currentIter = ev.iteration_number
      }
      const iter = ev.iteration_number || currentIter || 0
      if (!groups.has(iter)) groups.set(iter, [])
      groups.get(iter)!.push(ev)
    }
    return groups
  }

  if (loading) {
    return (
      <div className="card">
        <div className="flex items-center space-x-2 text-gray-400">
          <div className="animate-spin w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full" />
          <span>Loading session history...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card border-red-800 bg-red-900/20">
        <div className="flex items-center justify-between">
          <p className="text-red-400">{error}</p>
          <button onClick={loadSessions} className="text-sm text-red-400 hover:text-red-300 underline">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (sessions.length === 0) {
    return null
  }

  const filteredEvents = sessionEvents.filter(e => e.event_type !== 'heartbeat')
  const iterationGroups = groupEventsByIteration(filteredEvents)

  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Planning Sessions
      </h3>

      <div className="space-y-3">
        {sessions.map((session, index) => (
          <div
            key={session.id}
            className="border border-gray-700 rounded-lg overflow-hidden"
          >
            {/* Session Header */}
            <button
              onClick={() => handleExpandSession(session)}
              className="w-full px-4 py-3 bg-gray-800/50 hover:bg-gray-800 flex items-center justify-between text-left transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-white font-medium">
                    Session {sessions.length - index}
                  </span>
                  <span className="text-gray-500 text-sm">
                    {formatRelativeTime(session.created_at)}
                  </span>
                  {session.is_legacy && (
                    <span className="px-2 py-0.5 bg-gray-600/30 text-gray-400 text-xs rounded">
                      Legacy chat
                    </span>
                  )}
                  {!session.is_legacy && (
                    <span className="text-gray-500 text-sm">
                      {session.iterations_completed}/{session.iterations_requested} iterations
                    </span>
                  )}
                  <span className={`px-2 py-0.5 text-xs rounded ${
                    session.run_status === 'completed' ? 'bg-green-600/30 text-green-400' :
                    session.run_status === 'running' ? 'bg-yellow-600/30 text-yellow-400' :
                    session.run_status === 'cancelled' ? 'bg-red-600/30 text-red-400' :
                    session.run_status === 'error' ? 'bg-red-600/30 text-red-400' :
                    'bg-blue-600/30 text-blue-400'
                  }`}>
                    {session.run_status}
                  </span>
                </div>

                {session.prompt && (
                  <p className="text-gray-400 text-sm mt-1 truncate">
                    &quot;{session.prompt}{session.prompt.length >= 100 ? '...' : ''}&quot;
                  </p>
                )}

                {!session.is_legacy && (session.total_chars_added > 0 || session.total_chars_removed > 0) && (
                  <p className="text-sm mt-1 flex items-center gap-2">
                    {session.total_chars_added > 0 && (
                      <span className="text-green-400">
                        +{session.total_chars_added.toLocaleString()} chars
                      </span>
                    )}
                    {session.total_chars_removed > 0 && (
                      <span className="text-red-400">
                        -{session.total_chars_removed.toLocaleString()} chars
                      </span>
                    )}
                  </p>
                )}
              </div>

              <svg
                className={`w-5 h-5 text-gray-400 transition-transform flex-shrink-0 ml-2 ${
                  expandedSession === session.id ? 'rotate-180' : ''
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Expanded Detail */}
            {expandedSession === session.id && (
              <div className="px-4 py-3 border-t border-gray-700 bg-gray-900/50">
                {/* Full prompt display */}
                {session.prompt && (
                  <div className="mb-3">
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Prompt</div>
                    <div className="bg-gray-800/50 rounded-lg p-3 text-gray-300 text-sm whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {session.prompt}
                    </div>
                  </div>
                )}

                {/* Metadata */}
                <div className="text-xs text-gray-500 mb-3">
                  {!session.is_legacy && <>{session.iterations_requested} iteration{session.iterations_requested !== 1 ? 's' : ''} requested &middot; </>}
                  {new Date(session.created_at).toLocaleString()}
                </div>

                {/* Clone button */}
                {!session.is_legacy && onClonePrompt && (
                  <button
                    disabled={cloneDisabled}
                    onClick={() => onClonePrompt(session.prompt || '', session.iterations_requested)}
                    className="mb-3 px-3 py-1.5 text-xs font-medium bg-gray-700 hover:bg-gray-600 text-gray-200 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Clone Session
                  </button>
                )}

                {/* Error message for failed sessions */}
                {session.run_status === 'error' && (
                  <div className="text-sm p-2 bg-red-900/30 text-red-400 rounded mb-3">
                    Session failed
                  </div>
                )}

                {/* Iteration-based sessions: show iteration summary + events */}
                {!session.is_legacy && (
                  <>
                    {session.iterations.length > 0 && (
                      <div className="space-y-1 mb-3">
                        {session.iterations.map(it => (
                          <div
                            key={it.id}
                            className="flex items-center gap-3 text-sm py-1"
                          >
                            <span className={`${
                              it.status === 'completed' ? 'text-green-400' :
                              it.status === 'failed' ? 'text-red-400' :
                              it.status === 'running' ? 'text-yellow-400' :
                              'text-gray-500'
                            }`}>
                              {it.status === 'completed' ? '\u2713' :
                               it.status === 'failed' ? '\u2717' :
                               it.status === 'running' ? '\u25CF' : '\u25CB'}
                            </span>
                            <span className="text-gray-300">
                              Iteration {it.iteration_number}
                            </span>
                            {it.chars_added > 0 && (
                              <span className="text-green-400 text-xs">
                                +{it.chars_added}
                              </span>
                            )}
                            {it.chars_removed > 0 && (
                              <span className="text-red-400 text-xs">
                                -{it.chars_removed}
                              </span>
                            )}
                            {it.summary && (
                              <span className="text-gray-500 text-xs truncate">
                                {it.summary}
                              </span>
                            )}
                            {it.status === 'completed' && (
                              <button
                                onClick={(e) => { e.stopPropagation(); handleViewDiff(session.id, it.id, it.iteration_number) }}
                                disabled={diffLoading}
                                className="ml-auto text-xs px-2 py-0.5 bg-gray-700/50 hover:bg-gray-600/50 text-gray-400 hover:text-gray-200 border border-gray-600 rounded transition-colors flex-shrink-0"
                              >
                                View Diff
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {session.iterations.length === 0 && !loadingEvents && (
                      <div className="text-gray-500 text-sm text-center py-4">
                        No iteration data available
                      </div>
                    )}

                    {/* Event log */}
                    {loadingEvents && (
                      <div className="flex items-center space-x-2 text-gray-400 text-sm py-2">
                        <div className="animate-spin w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full" />
                        <span>Loading events...</span>
                      </div>
                    )}

                    {eventsError && (
                      <div className="text-sm text-red-400 py-2">
                        Failed to load events: {eventsError}
                      </div>
                    )}

                    {!loadingEvents && !eventsError && filteredEvents.length > 0 && expandedSession === session.id && (
                      <div>
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                          Event Log ({filteredEvents.length})
                        </div>
                        <div className="space-y-1 max-h-80 overflow-y-auto">
                          {Array.from(iterationGroups.entries()).map(([iterNum, events]) => (
                            <div key={iterNum} className="border border-gray-700/50 rounded">
                              {/* Iteration header */}
                              <button
                                onClick={() => toggleIteration(iterNum)}
                                className="w-full px-3 py-2 flex items-center gap-2 text-sm text-left bg-gray-800/30 hover:bg-gray-800/60 transition-colors"
                              >
                                <svg
                                  className={`w-3 h-3 text-gray-500 transition-transform ${expandedIterations.has(iterNum) ? 'rotate-90' : ''}`}
                                  fill="currentColor" viewBox="0 0 20 20"
                                >
                                  <path d="M6 4l8 6-8 6V4z" />
                                </svg>
                                <span className="text-cyan-400 font-medium">
                                  Iteration {iterNum || '?'}
                                </span>
                                <span className="text-gray-500 text-xs">
                                  {events.filter(e => e.event_type === 'tool_use').length} tool calls
                                </span>
                              </button>

                              {/* Iteration events */}
                              {expandedIterations.has(iterNum) && (
                                <div className="px-3 py-1 space-y-0.5">
                                  {events
                                    .filter(e => e.event_type !== 'iteration_start' && e.event_type !== 'iteration_complete')
                                    .map(ev => {
                                      const style = getEventStyle(ev.event_type)
                                      const isExpanded = expandedEventIds.has(ev.id)
                                      const hasDetail = ev.event_type === 'tool_use' || ev.event_type === 'tool_result' || ev.event_type === 'content' || ev.event_type === 'error'

                                      return (
                                        <div key={ev.id}>
                                          <button
                                            onClick={() => hasDetail && toggleEvent(ev.id)}
                                            className={`w-full text-left flex items-center gap-2 py-1 text-xs ${hasDetail ? 'cursor-pointer hover:bg-gray-800/40' : 'cursor-default'} rounded px-1`}
                                          >
                                            <span className={style.color}>{getEventLabel(ev)}</span>
                                            {ev.content && !isExpanded && (
                                              <span className="text-gray-600 truncate flex-1">
                                                {ev.content.slice(0, 80)}
                                              </span>
                                            )}
                                            {hasDetail && (
                                              <svg
                                                className={`w-3 h-3 text-gray-600 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
                                                fill="currentColor" viewBox="0 0 20 20"
                                              >
                                                <path d="M6 4l8 6-8 6V4z" />
                                              </svg>
                                            )}
                                          </button>

                                          {isExpanded && (
                                            <div className="ml-5 mb-1">
                                              {ev.event_type === 'tool_use' && ev.tool_input && (
                                                <pre className="text-xs text-gray-400 bg-gray-800/50 rounded p-2 max-h-40 overflow-auto whitespace-pre-wrap break-all">
                                                  {formatToolInput(ev.tool_input)}
                                                </pre>
                                              )}
                                              {ev.event_type === 'tool_result' && ev.tool_result && (
                                                <pre className="text-xs text-gray-400 bg-gray-800/50 rounded p-2 max-h-40 overflow-auto whitespace-pre-wrap break-all">
                                                  {ev.tool_result.length > 2000 ? ev.tool_result.slice(0, 2000) + '...' : ev.tool_result}
                                                </pre>
                                              )}
                                              {ev.event_type === 'content' && ev.content && (
                                                <div className="text-xs text-gray-300 bg-gray-800/50 rounded p-2 max-h-40 overflow-auto prose prose-invert prose-xs max-w-none">
                                                  <ReactMarkdown>{ev.content}</ReactMarkdown>
                                                </div>
                                              )}
                                              {ev.event_type === 'error' && (
                                                <div className="text-xs text-red-400 bg-red-900/20 rounded p-2">
                                                  {ev.content || ev.event_data || 'Unknown error'}
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      )
                                    })}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {!loadingEvents && !eventsError && filteredEvents.length === 0 && session.iterations.length > 0 && expandedSession === session.id && (
                      <div className="text-gray-500 text-xs text-center py-2">
                        No events recorded
                      </div>
                    )}
                  </>
                )}

                {/* Legacy sessions: show messages */}
                {session.is_legacy && loadingDetail && (
                  <div className="flex items-center space-x-2 text-gray-400 py-4">
                    <div className="animate-spin w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full" />
                    <span>Loading messages...</span>
                  </div>
                )}

                {session.is_legacy && legacyDetail && (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {legacyDetail.messages.map((msg, msgIndex) => {
                      const isExpanded = expandedMessages.has(msgIndex)
                      const needsTruncation = msg.content.length > 500
                      return (
                        <div
                          key={msgIndex}
                          className={`p-3 rounded-lg ${
                            msg.role === 'user'
                              ? 'bg-primary-900/30 border border-primary-800'
                              : 'bg-gray-800/50 border border-gray-700'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs font-medium ${
                              msg.role === 'user' ? 'text-primary-400' : 'text-gray-400'
                            }`}>
                              {msg.role === 'user' ? 'You' : 'Claude'}
                            </span>
                            {msg.timestamp && (
                              <span className="text-gray-600 text-xs">
                                {formatRelativeTime(msg.timestamp)}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-300 text-sm whitespace-pre-wrap">
                            {needsTruncation && !isExpanded
                              ? msg.content.slice(0, 500) + '...'
                              : msg.content}
                          </p>
                          {needsTruncation && (
                            <button
                              onClick={() => {
                                setExpandedMessages(prev => {
                                  const next = new Set(prev)
                                  if (isExpanded) {
                                    next.delete(msgIndex)
                                  } else {
                                    next.add(msgIndex)
                                  }
                                  return next
                                })
                              }}
                              className="text-xs text-primary-400 hover:text-primary-300 mt-1"
                            >
                              {isExpanded
                                ? 'Show less'
                                : `Show more (${(msg.content.length - 500).toLocaleString()} more chars)`}
                            </button>
                          )}
                        </div>
                      )
                    })}
                    {legacyDetail.messages.length === 0 && (
                      <div className="text-gray-500 text-sm text-center py-4">
                        No messages in this session
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
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
