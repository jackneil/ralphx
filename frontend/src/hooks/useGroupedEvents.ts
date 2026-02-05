import { useState, useEffect, useCallback, useRef } from 'react'
import { useSSE, type SSEEvent } from './useSSE'

export interface SessionEvent {
  id: number
  session_id: string
  event_type: string
  timestamp: string
  content?: string
  tool_name?: string
  tool_input?: object
  tool_result?: string
  error_message?: string
  raw_data?: string
}

export interface IterationData {
  session_id: string
  mode: string | null
  status: string | null
  is_live: boolean
  events: SessionEvent[]
}

export interface RunData {
  status: string
  loop_name: string
  started_at: string | null
  completed_at: string | null
  iterations_completed: number
  items_generated: number
  error_message?: string
  iterations: Record<number, IterationData>
}

export interface GroupedRuns {
  [runId: string]: RunData
}

interface UseGroupedEventsOptions {
  projectSlug: string
  loopName: string
  enabled?: boolean
  pollInterval?: number
}

interface UseGroupedEventsResult {
  runs: GroupedRuns
  loading: boolean
  error: string | null
  isConnected: boolean
  refresh: () => Promise<void>
}

// Counter for generating unique event IDs (avoids Date.now() collisions)
let eventIdCounter = 0

function generateUniqueEventId(): number {
  return Date.now() * 1000 + (eventIdCounter++ % 1000)
}

export function useGroupedEvents({
  projectSlug,
  loopName,
  enabled = true,
  pollInterval = 5000,
}: UseGroupedEventsOptions): UseGroupedEventsResult {
  const [runs, setRuns] = useState<GroupedRuns>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track the current run and iteration for live event insertion
  const liveContextRef = useRef<{ runId: string | null; iteration: number | null }>({
    runId: null,
    iteration: null,
  })

  // Load historical/grouped events from API
  const loadGroupedEvents = useCallback(async () => {
    if (!enabled) return

    try {
      const response = await fetch(
        `/api/projects/${projectSlug}/loops/${loopName}/events/grouped`
      )

      if (!response.ok) {
        throw new Error(`Failed to fetch events: ${response.statusText}`)
      }

      const data = await response.json()
      const polledRuns: GroupedRuns = data.runs || {}

      // Merge polled data with existing state, preserving live SSE events
      // that may not have been persisted to DB yet. Without this merge,
      // polling would overwrite SSE-inserted events causing them to flash
      // and disappear from the UI.
      setRuns((prev) => {
        const merged: GroupedRuns = { ...polledRuns }

        for (const [runId, prevRun] of Object.entries(prev)) {
          for (const [iterKey, prevIter] of Object.entries(prevRun.iterations)) {
            // Only preserve live SSE events that aren't in the polled data
            if (!prevIter.is_live) continue

            const polledRun = merged[runId]
            if (!polledRun) continue

            const polledIter = polledRun.iterations[Number(iterKey)]
            if (!polledIter) {
              // Polled data doesn't have this iteration yet - keep live data
              polledRun.iterations[Number(iterKey)] = prevIter
              continue
            }

            // Append any SSE events whose IDs are not in the polled set.
            // SSE-generated events use large synthetic IDs (Date.now()*1000+counter)
            // while DB events use small auto-increment IDs, so we can distinguish them.
            const polledEventIds = new Set(polledIter.events.map((e: SessionEvent) => e.id))
            const extraSseEvents = prevIter.events.filter(
              (e: SessionEvent) => !polledEventIds.has(e.id) && e.id > 1_000_000_000_000
            )

            if (extraSseEvents.length > 0) {
              polledIter.events = [...polledIter.events, ...extraSseEvents]
            }

            // Preserve the is_live flag if the previous state had it
            if (prevIter.is_live) {
              polledIter.is_live = true
            }
          }
        }

        return merged
      })

      // Find the live run/iteration
      for (const [runId, run] of Object.entries(polledRuns)) {
        if (run.status === 'running' || run.status === 'paused') {
          liveContextRef.current.runId = runId
          const iterations = Object.keys(run.iterations).map(Number)
          if (iterations.length > 0) {
            liveContextRef.current.iteration = Math.max(...iterations)
          }
          break
        }
      }

      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, loopName, enabled])

  // Handle live SSE events
  const handleSSEEvent = useCallback((event: SSEEvent) => {
    const { type, data } = event

    // Skip non-content events (heartbeat, connected, disconnected are control events;
    // info is a backend status message like "No session found" that should not
    // be inserted into the run/iteration event tree)
    if (['heartbeat', 'connected', 'disconnected', 'info'].includes(type)) {
      return
    }

    // Get run_id and iteration from event data
    const eventRunId = data.run_id as string | undefined
    const eventIteration = data.iteration as number | undefined

    if (!eventRunId || eventIteration === undefined) {
      // Fallback to tracked context
      if (!liveContextRef.current.runId || !liveContextRef.current.iteration) {
        return
      }
    }

    const runId = eventRunId || liveContextRef.current.runId!
    const iteration = eventIteration ?? liveContextRef.current.iteration!

    // Update live context
    liveContextRef.current.runId = runId
    liveContextRef.current.iteration = iteration

    // Create a synthetic event object
    const newEvent: SessionEvent = {
      id: generateUniqueEventId(), // Unique ID using counter to avoid collisions
      session_id: data.session_id as string || '',
      event_type: type,
      timestamp: new Date().toISOString(),
      content: data.content as string | undefined,
      tool_name: data.name as string | undefined,
      tool_input: data.input as object | undefined,
      tool_result: data.result as string | undefined,
      error_message: data.message as string | undefined,
    }

    setRuns((prev) => {
      const updated = { ...prev }

      // Ensure run exists
      if (!updated[runId]) {
        updated[runId] = {
          status: 'running',
          loop_name: loopName, // Use the loopName from the hook options
          started_at: null,
          completed_at: null,
          iterations_completed: 0,
          items_generated: 0,
          iterations: {},
        }
      }

      // Ensure iteration exists
      if (!updated[runId].iterations[iteration]) {
        updated[runId].iterations[iteration] = {
          session_id: data.session_id as string || '',
          mode: null,
          status: 'active',
          is_live: true,
          events: [],
        }
      }

      // Add event to iteration
      updated[runId].iterations[iteration].events = [
        ...updated[runId].iterations[iteration].events,
        newEvent,
      ]

      // Mark as live
      updated[runId].iterations[iteration].is_live = true

      // Handle status event - might indicate new iteration or run state change
      if (type === 'status') {
        updated[runId].status = data.status as string || updated[runId].status
        liveContextRef.current.iteration = data.iteration as number || iteration
      }

      // Handle complete event
      if (type === 'complete') {
        updated[runId].iterations[iteration].is_live = false
        updated[runId].iterations[iteration].status = 'completed'
      }

      return updated
    })
  }, [loopName])

  // SSE for live updates
  const sseUrl = enabled ? `/api/projects/${projectSlug}/loops/${loopName}/stream` : ''
  const { isConnected } = useSSE({
    url: sseUrl,
    enabled: enabled && !!sseUrl,
    onEvent: handleSSEEvent,
    maxStoredEvents: 0, // We manage our own storage
  })

  // Load on mount and poll for updates
  useEffect(() => {
    loadGroupedEvents()

    // Poll for updates (to catch any missed events and get new runs)
    const poll = () => {
      pollTimeoutRef.current = setTimeout(() => {
        loadGroupedEvents()
        poll()
      }, pollInterval)
    }

    poll()

    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
      }
    }
  }, [loadGroupedEvents, pollInterval])

  return {
    runs,
    loading,
    error,
    isConnected,
    refresh: loadGroupedEvents,
  }
}

// Helper to get total event count across all runs
export function getTotalEventCount(runs: GroupedRuns): number {
  let total = 0
  for (const run of Object.values(runs)) {
    for (const iteration of Object.values(run.iterations)) {
      total += iteration.events.length
    }
  }
  return total
}

// Helper to get total events for a run
export function getRunEventCount(run: RunData): number {
  let total = 0
  for (const iteration of Object.values(run.iterations)) {
    total += iteration.events.length
  }
  return total
}
