import { useState, useCallback, useRef, useEffect } from 'react'
import {
  useGroupedEvents,
  getTotalEventCount,
  getRunEventCount,
  type RunData,
  type IterationData,
  type SessionEvent,
} from '../hooks/useGroupedEvents'
import { formatLocalTime, formatLocalDateTime } from '../utils/time'

interface SessionHistoryProps {
  projectSlug: string
  loopName: string
  enabled?: boolean
}

export default function SessionHistory({
  projectSlug,
  loopName,
  enabled = true,
}: SessionHistoryProps) {
  const { runs, loading, error, isConnected, refresh } = useGroupedEvents({
    projectSlug,
    loopName,
    enabled,
  })

  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set())
  const [expandedIterations, setExpandedIterations] = useState<Set<string>>(new Set())
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)

  // Track if we've done initial auto-expansion
  const hasAutoExpandedRef = useRef(false)

  // Track if user has manually scrolled away from bottom
  const userScrolledRef = useRef(false)
  const lastScrollTopRef = useRef(0)

  // Auto-expand only on INITIAL load
  useEffect(() => {
    if (hasAutoExpandedRef.current || Object.keys(runs).length === 0) {
      return
    }

    hasAutoExpandedRef.current = true

    const newExpandedRuns = new Set<string>()
    const newExpandedIterations = new Set<string>()

    // Sort oldest to newest (newest at bottom)
    const sortedRuns = Object.entries(runs).sort(([, a], [, b]) => {
      const aTime = a.started_at ? new Date(a.started_at).getTime() : 0
      const bTime = b.started_at ? new Date(b.started_at).getTime() : 0
      return aTime - bTime
    })

    // Find the most recent running/active run (will be at end of sorted array)
    for (let i = sortedRuns.length - 1; i >= 0; i--) {
      const [runId, run] = sortedRuns[i]
      if (run.status === 'running' || run.status === 'paused') {
        newExpandedRuns.add(runId)

        Object.entries(run.iterations).forEach(([iter, data]) => {
          if (data.is_live) {
            newExpandedIterations.add(`${runId}-${iter}`)
          }
        })
        break
      }
    }

    setExpandedRuns(newExpandedRuns)
    setExpandedIterations(newExpandedIterations)
  }, [runs])

  // Track user scroll behavior
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 50
    userScrolledRef.current = !isNearBottom
    lastScrollTopRef.current = scrollTop
  }, [])

  // Auto-scroll to bottom when new content arrives (if user hasn't scrolled away)
  useEffect(() => {
    if (!containerRef.current || userScrolledRef.current) return
    containerRef.current.scrollTop = containerRef.current.scrollHeight
  }, [runs])

  const toggleRun = useCallback((runId: string) => {
    setExpandedRuns((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) {
        next.delete(runId)
      } else {
        next.add(runId)
      }
      return next
    })
  }, [])

  const toggleIteration = useCallback((runId: string, iteration: number) => {
    const key = `${runId}-${iteration}`
    setExpandedIterations((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }, [])

  const toggleEvent = useCallback((eventId: number) => {
    setExpandedEvents((prev) => {
      const next = new Set(prev)
      if (next.has(eventId)) {
        next.delete(eventId)
      } else {
        next.add(eventId)
      }
      return next
    })
  }, [])

  const expandAll = useCallback(() => {
    const allRuns = new Set(Object.keys(runs))
    const allIterations = new Set<string>()

    Object.entries(runs).forEach(([runId, run]) => {
      Object.keys(run.iterations).forEach((iter) => {
        allIterations.add(`${runId}-${iter}`)
      })
    })

    setExpandedRuns(allRuns)
    setExpandedIterations(allIterations)
  }, [runs])

  const collapseAll = useCallback(() => {
    setExpandedRuns(new Set())
    setExpandedIterations(new Set())
    setExpandedEvents(new Set())
  }, [])

  if (error) {
    return (
      <div className="card-panel p-6">
        <div className="flex items-center gap-3 text-[var(--color-rose)]">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="font-medium">{error}</span>
        </div>
        <button
          onClick={refresh}
          className="mt-4 btn-secondary"
        >
          Retry
        </button>
      </div>
    )
  }

  // Sort oldest to newest (newest at bottom)
  const runEntries = Object.entries(runs).sort(([, a], [, b]) => {
    const aTime = a.started_at ? new Date(a.started_at).getTime() : 0
    const bTime = b.started_at ? new Date(b.started_at).getTime() : 0
    return aTime - bTime
  })

  return (
    <div className="card-panel overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]/50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--color-violet)]/20 flex items-center justify-center">
            <svg className="w-4 h-4 text-[var(--color-violet)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-[var(--color-text-primary)]">Session Log</h3>
            <div className="flex items-center gap-2 text-xs">
              {isConnected ? (
                <span className="flex items-center gap-1.5 text-[var(--color-emerald)]">
                  <span className="status-dot status-dot-running" />
                  Live
                </span>
              ) : (
                <span className="text-[var(--color-text-muted)]">Disconnected</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] rounded-md transition-colors"
          >
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] rounded-md transition-colors"
          >
            Collapse
          </button>
        </div>
      </div>

      {/* Content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="max-h-[500px] overflow-y-auto custom-scrollbar"
      >
        {loading ? (
          <div className="flex items-center justify-center py-12 text-[var(--color-text-muted)]">
            <svg className="w-5 h-5 animate-spin mr-3" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Loading session history...
          </div>
        ) : runEntries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-[var(--color-text-muted)]">
            <div className="w-12 h-12 rounded-full bg-[var(--color-elevated)] flex items-center justify-center mb-3">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <p className="font-medium">No session history yet</p>
            <p className="text-sm mt-1">Events will appear here when the step runs</p>
          </div>
        ) : (
          <div className="p-3 space-y-1">
            {runEntries.map(([runId, run], index) => (
              <RunSection
                key={runId}
                runId={runId}
                run={run}
                isExpanded={expandedRuns.has(runId)}
                expandedIterations={expandedIterations}
                expandedEvents={expandedEvents}
                onToggleRun={toggleRun}
                onToggleIteration={toggleIteration}
                onToggleEvent={toggleEvent}
                index={index}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 text-xs font-mono text-[var(--color-text-muted)] border-t border-[var(--color-border)] bg-[var(--color-deep)]">
        <span className="text-[var(--color-cyan)]">{getTotalEventCount(runs)}</span> events across{' '}
        <span className="text-[var(--color-cyan)]">{Object.keys(runs).length}</span> runs
      </div>
    </div>
  )
}

// Run Section Component
interface RunSectionProps {
  runId: string
  run: RunData
  isExpanded: boolean
  expandedIterations: Set<string>
  expandedEvents: Set<number>
  onToggleRun: (runId: string) => void
  onToggleIteration: (runId: string, iteration: number) => void
  onToggleEvent: (eventId: number) => void
  index: number
}

// Extract step number from loop_name (format: wf_{wf_id}_step{N})
function parseStepFromLoopName(loopName: string): number | null {
  const match = loopName.match(/_step(\d+)$/)
  return match ? parseInt(match[1], 10) : null
}


function RunSection({
  runId,
  run,
  isExpanded,
  expandedIterations,
  expandedEvents,
  onToggleRun,
  onToggleIteration,
  onToggleEvent,
  index,
}: RunSectionProps) {
  const eventCount = getRunEventCount(run)
  const stepNumber = parseStepFromLoopName(run.loop_name)

  // Get the most recent timestamp for this run
  const lastUpdate = run.completed_at || run.started_at
  const lastUpdateStr = formatLocalDateTime(lastUpdate)

  const getStatusDot = () => {
    switch (run.status) {
      case 'running': return 'status-dot-running'
      case 'paused': return 'status-dot-paused'
      case 'completed': return 'status-dot-completed'
      case 'aborted': return 'status-dot-aborted'
      default: return ''
    }
  }

  const getStatusBadge = () => {
    switch (run.status) {
      case 'running': return 'badge-running'
      case 'paused': return 'badge-pending'
      case 'completed': return 'badge-completed'
      case 'aborted': return 'badge-aborted'
      default: return 'badge-pending'
    }
  }

  const iterationEntries = Object.entries(run.iterations)
    .map(([k, v]) => [parseInt(k, 10), v] as [number, IterationData])
    .sort(([a], [b]) => a - b)

  return (
    <div className={`animate-fade-in-up stagger-${Math.min(index + 1, 5)}`} style={{ opacity: 0 }}>
      {/* Run Header */}
      <button
        onClick={() => onToggleRun(runId)}
        className="flex items-center gap-3 w-full py-2.5 px-3 hover:bg-[var(--color-elevated)] rounded-lg transition-colors group"
      >
        <svg
          className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>

        <span className={`status-dot ${getStatusDot()}`} />

        <span className="font-mono text-sm text-[var(--color-text-primary)]">
          Run #{index + 1}
        </span>

        {stepNumber && (
          <span className="px-2 py-0.5 text-xs font-mono bg-[var(--color-violet)]/20 text-[var(--color-violet)] rounded border border-[var(--color-violet)]/30">
            Step {stepNumber}
          </span>
        )}

        <span className={`badge ${getStatusBadge()} ml-1`}>
          {run.status}
        </span>

        <span className="ml-auto flex items-center gap-3 font-mono text-xs text-[var(--color-text-muted)]">
          {lastUpdateStr && (
            <span title="Last update">{lastUpdateStr}</span>
          )}
          <span className="text-[var(--color-text-muted)]/60">{eventCount} events</span>
        </span>
      </button>

      {/* Run Content */}
      <div
        className={`overflow-hidden transition-all duration-300 ${isExpanded ? 'max-h-[3000px] opacity-100' : 'max-h-0 opacity-0'}`}
      >
        <div className="ml-4 pl-4 border-l-2 border-[var(--color-border)] space-y-0.5">
          {iterationEntries.map(([iteration, data]) => (
            <IterationSection
              key={`${runId}-${iteration}`}
              runId={runId}
              iteration={iteration}
              data={data}
              isExpanded={expandedIterations.has(`${runId}-${iteration}`)}
              expandedEvents={expandedEvents}
              onToggle={() => onToggleIteration(runId, iteration)}
              onToggleEvent={onToggleEvent}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// Iteration Section Component
interface IterationSectionProps {
  runId: string
  iteration: number
  data: IterationData
  isExpanded: boolean
  expandedEvents: Set<number>
  onToggle: () => void
  onToggleEvent: (eventId: number) => void
}

function IterationSection({
  runId: _runId,
  iteration,
  data,
  isExpanded,
  expandedEvents,
  onToggle,
  onToggleEvent,
}: IterationSectionProps) {
  return (
    <div>
      {/* Iteration Header */}
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full py-2 px-3 hover:bg-[var(--color-elevated)] rounded-md transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 text-[var(--color-text-muted)] transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>

        {data.is_live ? (
          <span className="status-dot status-dot-running" />
        ) : (
          <svg className="w-4 h-4 text-[var(--color-emerald)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )}

        <span className="font-mono text-sm text-[var(--color-text-secondary)]">
          Iteration <span className="text-[var(--color-text-primary)]">{iteration}</span>
        </span>

        {data.mode && (
          <span className="text-xs text-[var(--color-text-muted)]">({data.mode})</span>
        )}

        <span className="ml-auto font-mono text-xs text-[var(--color-text-muted)]">
          {data.events.length} events
        </span>
      </button>

      {/* Iteration Events */}
      <div
        className={`overflow-hidden transition-all duration-200 ${isExpanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'}`}
      >
        <div className="ml-4 pl-4 border-l border-[var(--color-border)]/50 space-y-0.5 py-1">
          {data.events.map((event, idx) => {
            const eventKey = `${event.id}-${idx}`
            return (
              <EventItem
                key={eventKey}
                event={event}
                isExpanded={expandedEvents.has(event.id)}
                isLive={data.is_live && idx === data.events.length - 1}
                onToggle={() => onToggleEvent(event.id)}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}

// Event type styling
const EVENT_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  text: { icon: '💬', color: 'text-[var(--color-text-secondary)]', bg: 'bg-[var(--color-elevated)]' },
  tool_call: { icon: '🔧', color: 'text-[var(--color-cyan)]', bg: 'bg-[var(--color-cyan)]/10' },
  tool_result: { icon: '✓', color: 'text-[var(--color-emerald)]', bg: 'bg-[var(--color-emerald)]/10' },
  error: { icon: '✕', color: 'text-[var(--color-rose)]', bg: 'bg-[var(--color-rose)]/10' },
  init: { icon: '⚡', color: 'text-[var(--color-violet)]', bg: 'bg-[var(--color-violet)]/10' },
  complete: { icon: '✓', color: 'text-[var(--color-emerald)]', bg: 'bg-[var(--color-emerald)]/10' },
  session_start: { icon: '▶', color: 'text-[var(--color-amber)]', bg: 'bg-[var(--color-amber)]/10' },
  status: { icon: '◉', color: 'text-[var(--color-amber)]', bg: 'bg-[var(--color-amber)]/10' },
}

// Event Item Component
interface EventItemProps {
  event: SessionEvent
  isExpanded: boolean
  isLive: boolean
  onToggle: () => void
}

function EventItem({ event, isExpanded, isLive, onToggle }: EventItemProps) {
  const style = EVENT_STYLES[event.event_type] || EVENT_STYLES.text
  const preview = getEventPreview(event, 40)
  const hasContent = hasExpandableContent(event)
  const contentRef = useRef<HTMLDivElement>(null)

  const time = formatLocalTime(event.timestamp)

  // Scroll expanded content into view
  useEffect(() => {
    if (isExpanded && contentRef.current) {
      // Small delay to allow expansion animation to start
      setTimeout(() => {
        contentRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }, 50)
    }
  }, [isExpanded])

  return (
    <div>
      {/* Event Header */}
      <button
        onClick={hasContent ? onToggle : undefined}
        className={`flex items-center gap-2 w-full py-1.5 px-2 rounded text-sm transition-colors ${hasContent ? 'hover:bg-[var(--color-elevated)] cursor-pointer' : 'cursor-default'}`}
      >
        {hasContent && (
          <svg
            className={`w-3 h-3 text-[var(--color-text-muted)] transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        )}
        {!hasContent && <span className="w-3" />}

        <span className={`w-5 h-5 rounded flex items-center justify-center text-xs ${style.bg}`}>
          {style.icon}
        </span>

        <span className={`font-mono text-xs ${style.color} truncate flex-1 text-left`}>
          {event.tool_name || truncate(preview, 35)}
        </span>

        <span className="font-mono text-xs text-[var(--color-text-muted)]">{time}</span>

        {isLive && <span className="status-dot status-dot-running ml-1" />}
      </button>

      {/* Event Details */}
      {hasContent && (
        <div
          ref={contentRef}
          className={`overflow-hidden transition-all duration-200 ${isExpanded ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}
        >
          <div className="ml-8 mr-2 mb-2 p-3 bg-[var(--color-deep)] rounded-lg border border-[var(--color-border)]">
            <EventContent event={event} />
          </div>
        </div>
      )}
    </div>
  )
}

// Render text content with smart formatting
function TextContent({ content }: { content: string }) {
  // Check if content contains JSON code block
  const jsonBlockMatch = content.match(/```json\s*([\s\S]*?)```/)
  if (jsonBlockMatch) {
    const beforeJson = content.slice(0, jsonBlockMatch.index).trim()
    const jsonStr = jsonBlockMatch[1].trim()
    const afterJson = content.slice((jsonBlockMatch.index || 0) + jsonBlockMatch[0].length).trim()

    // Try to parse the JSON
    let parsed: unknown = null
    try {
      parsed = JSON.parse(jsonStr)
    } catch {
      // Not valid JSON, show as code block
    }

    // Check if it's a stories array
    const isStories = parsed && typeof parsed === 'object' && 'stories' in (parsed as Record<string, unknown>)

    return (
      <div className="space-y-3">
        {beforeJson && (
          <p className="text-sm text-[var(--color-text-secondary)]">{beforeJson}</p>
        )}
        {isStories ? (
          <StoriesDisplay stories={(parsed as { stories: Array<{ id?: string; title?: string; content?: string }> }).stories} />
        ) : parsed ? (
          <div className="p-3 bg-[var(--color-void)] rounded-lg border border-[var(--color-border)]">
            <pre className="text-xs font-mono text-[var(--color-text-secondary)] overflow-auto max-h-48 custom-scrollbar">
              {JSON.stringify(parsed, null, 2)}
            </pre>
          </div>
        ) : (
          <div className="p-3 bg-[var(--color-void)] rounded-lg border border-[var(--color-border)]">
            <pre className="text-xs font-mono text-[var(--color-text-secondary)] overflow-auto max-h-48 custom-scrollbar whitespace-pre-wrap">
              {jsonStr}
            </pre>
          </div>
        )}
        {afterJson && (
          <p className="text-sm text-[var(--color-text-secondary)]">{afterJson}</p>
        )}
      </div>
    )
  }

  // Regular text content
  return (
    <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap">
      {content}
    </p>
  )
}

// Display user stories in a nice format
function StoriesDisplay({ stories }: { stories: Array<{ id?: string; title?: string; content?: string }> }) {
  const [expanded, setExpanded] = useState(false)
  const displayStories = expanded ? stories : stories.slice(0, 2)
  const hasMore = stories.length > 2

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-[var(--color-emerald)] uppercase tracking-wider">
          {stories.length} User {stories.length === 1 ? 'Story' : 'Stories'}
        </span>
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[var(--color-cyan)] hover:underline"
          >
            {expanded ? 'Show less' : `Show all ${stories.length}`}
          </button>
        )}
      </div>
      <div className="space-y-2 max-h-64 overflow-y-auto custom-scrollbar">
        {displayStories.map((story, idx) => (
          <div
            key={story.id || idx}
            className="p-3 bg-[var(--color-void)] rounded-lg border border-[var(--color-border)]"
          >
            <div className="flex items-start gap-2">
              {story.id && (
                <span className="px-1.5 py-0.5 text-xs font-mono bg-[var(--color-cyan)]/20 text-[var(--color-cyan)] rounded">
                  {story.id}
                </span>
              )}
              <div className="flex-1 min-w-0">
                {story.title && (
                  <div className="font-medium text-sm text-[var(--color-text-primary)] mb-1">
                    {story.title}
                  </div>
                )}
                {story.content && (
                  <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2">
                    {story.content}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Event Content Component
function EventContent({ event }: { event: SessionEvent }) {
  // Auto-show input by default - user already expanded the item, don't make them click again
  const [showJson, setShowJson] = useState(true)

  switch (event.event_type) {
    case 'text':
      return <TextContent content={event.content || ''} />

    case 'tool_call':
      return (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold text-[var(--color-cyan)]">{event.tool_name}</span>
          </div>
          {event.tool_input && (
            <div>
              <button
                onClick={() => setShowJson(!showJson)}
                className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
              >
                <svg
                  className={`w-3 h-3 transition-transform ${showJson ? 'rotate-90' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                {showJson ? 'Hide' : 'Show'} Input
              </button>
              {showJson && (
                <pre className="mt-2 p-2 bg-[var(--color-void)] rounded text-xs font-mono overflow-auto max-h-48 text-[var(--color-text-secondary)] custom-scrollbar">
                  {JSON.stringify(event.tool_input, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      )

    case 'tool_result':
      return (
        <div className="space-y-2">
          <div className="font-mono text-sm font-semibold text-[var(--color-emerald)]">
            {event.tool_name} → result
          </div>
          <pre className="p-2 bg-[var(--color-void)] rounded text-xs font-mono overflow-auto max-h-48 text-[var(--color-text-secondary)] custom-scrollbar whitespace-pre-wrap">
            {truncate(event.tool_result || '', 1000)}
          </pre>
        </div>
      )

    case 'error':
      return (
        <div className="text-[var(--color-rose)] text-sm font-mono">
          {event.error_message || 'Unknown error'}
        </div>
      )

    default:
      return (
        <pre className="text-xs font-mono text-[var(--color-text-muted)] overflow-auto max-h-48 custom-scrollbar">
          {JSON.stringify(event, null, 2)}
        </pre>
      )
  }
}

// Helper functions
function getEventPreview(event: SessionEvent, maxLen: number): string {
  if (event.tool_name) {
    return event.tool_name
  }
  if (event.content) {
    return truncate(event.content.replace(/\n/g, ' '), maxLen)
  }
  if (event.error_message) {
    return truncate(event.error_message, maxLen)
  }
  return event.event_type
}

function truncate(str: string | undefined, maxLen: number): string {
  if (!str) return ''
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}

function hasExpandableContent(event: SessionEvent): boolean {
  if (event.event_type === 'text' && event.content && event.content.length > 40) {
    return true
  }
  if (event.event_type === 'tool_call' && event.tool_input) {
    return true
  }
  if (event.event_type === 'tool_result' && event.tool_result) {
    return true
  }
  if (event.event_type === 'error' && event.error_message) {
    return true
  }
  return false
}
