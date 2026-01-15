import { useEffect, useRef, useState } from 'react'
import { useSSE, type SSEEvent } from '../hooks/useSSE'

interface SessionTailProps {
  projectSlug: string
  loopName?: string
  sessionId?: string
  enabled?: boolean
  maxEvents?: number
}

export default function SessionTail({
  projectSlug,
  loopName,
  sessionId,
  enabled = true,
  maxEvents = 500,
}: SessionTailProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const [isPaused, setIsPaused] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Construct URL
  let url = `/api/projects/${projectSlug}`
  if (sessionId) {
    url += `/sessions/${sessionId}/tail`
  } else if (loopName) {
    url += `/loops/${loopName}/stream`
  } else {
    url = '' // No valid URL
  }

  const {
    events,
    isConnected,
    error,
    connect,
    disconnect,
    clearEvents,
  } = useSSE({
    url,
    enabled: enabled && !isPaused && !!url,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [events, autoScroll])

  // Limit events
  const displayEvents = events.slice(-maxEvents)

  const handlePauseToggle = () => {
    if (isPaused) {
      setIsPaused(false)
      connect()
    } else {
      setIsPaused(true)
      disconnect()
    }
  }

  const [copyStatus, setCopyStatus] = useState<'idle' | 'success' | 'error'>('idle')

  const handleCopy = async () => {
    const text = displayEvents
      .map((e) => formatEventForCopy(e))
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopyStatus('success')
      setTimeout(() => setCopyStatus('idle'), 2000)
    } catch {
      setCopyStatus('error')
      setTimeout(() => setCopyStatus('idle'), 2000)
    }
  }

  if (!url) {
    return (
      <div className="card text-center py-8">
        <p className="text-gray-400">No session or loop specified</p>
      </div>
    )
  }

  return (
    <div className="card flex flex-col h-[500px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center space-x-3">
          <h3 className="text-lg font-semibold text-white">Live Output</h3>
          <StatusBadge isConnected={isConnected} isPaused={isPaused} />
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`px-3 py-1 text-sm rounded ${
              autoScroll
                ? 'bg-primary-600 text-white'
                : 'bg-gray-700 text-gray-300'
            }`}
          >
            Auto-scroll
          </button>
          <button
            onClick={handlePauseToggle}
            className={`px-3 py-1 text-sm rounded ${
              isPaused
                ? 'bg-yellow-600 text-white'
                : 'bg-gray-700 text-gray-300'
            }`}
          >
            {isPaused ? 'Resume' : 'Pause'}
          </button>
          <button
            onClick={handleCopy}
            className={`px-3 py-1 text-sm rounded ${
              copyStatus === 'success'
                ? 'bg-green-700 text-green-200'
                : copyStatus === 'error'
                ? 'bg-red-700 text-red-200'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {copyStatus === 'success' ? 'Copied!' : copyStatus === 'error' ? 'Failed' : 'Copy'}
          </button>
          <button
            onClick={clearEvents}
            className="px-3 py-1 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-2 px-3 py-2 bg-red-900/30 border border-red-800 rounded text-sm text-red-400 flex-shrink-0">
          {error}
        </div>
      )}

      {/* Event Stream */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-gray-900 rounded font-mono text-sm"
      >
        {displayEvents.length === 0 ? (
          <div className="p-4 text-gray-500 text-center">
            {isConnected ? 'Waiting for events...' : 'Not connected'}
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {displayEvents.map((event, index) => (
              <EventLine key={index} event={event} />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="mt-2 text-xs text-gray-500 flex-shrink-0">
        {displayEvents.length} events
        {events.length > maxEvents && ` (${events.length - maxEvents} truncated)`}
      </div>
    </div>
  )
}

function StatusBadge({ isConnected, isPaused }: { isConnected: boolean; isPaused: boolean }) {
  if (isPaused) {
    return (
      <span className="flex items-center space-x-1.5 text-sm text-yellow-400">
        <span className="w-2 h-2 rounded-full bg-yellow-400" />
        <span>Paused</span>
      </span>
    )
  }

  return (
    <span
      className={`flex items-center space-x-1.5 text-sm ${
        isConnected ? 'text-green-400' : 'text-gray-400'
      }`}
    >
      <span
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
        }`}
      />
      <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
    </span>
  )
}

function EventLine({ event }: { event: SSEEvent }) {
  const time = event.timestamp.toLocaleTimeString()

  switch (event.type) {
    case 'text':
      return (
        <div className="text-gray-200 whitespace-pre-wrap">
          <span className="text-gray-500 mr-2">{time}</span>
          {String(event.data.content || '')}
        </div>
      )

    case 'tool_call':
      return (
        <div className="text-blue-400">
          <span className="text-gray-500 mr-2">{time}</span>
          <span className="font-semibold">Tool:</span>{' '}
          {String(event.data.name || 'unknown')}
          {event.data.input ? (
            <span className="text-gray-400 ml-2">
              {JSON.stringify(event.data.input).slice(0, 100)}...
            </span>
          ) : null}
        </div>
      )

    case 'tool_result':
      return (
        <div className="text-green-400">
          <span className="text-gray-500 mr-2">{time}</span>
          <span className="font-semibold">Result:</span>{' '}
          {String(event.data.result || '').slice(0, 200)}
          {String(event.data.result || '').length > 200 && '...'}
        </div>
      )

    case 'error':
      return (
        <div className="text-red-400">
          <span className="text-gray-500 mr-2">{time}</span>
          <span className="font-semibold">Error:</span>{' '}
          {String(event.data.message || 'Unknown error')}
        </div>
      )

    case 'status':
      return (
        <div className="text-yellow-400">
          <span className="text-gray-500 mr-2">{time}</span>
          <span className="font-semibold">Status:</span>{' '}
          {String(event.data.status || '')}
          {event.data.iteration ? ` (iteration ${String(event.data.iteration)})` : null}
        </div>
      )

    case 'connected':
    case 'session_start':
      return (
        <div className="text-primary-400">
          <span className="text-gray-500 mr-2">{time}</span>
          <span className="font-semibold">Connected</span>
        </div>
      )

    case 'complete':
      return (
        <div className="text-green-400 font-semibold">
          <span className="text-gray-500 mr-2">{time}</span>
          Session Complete
        </div>
      )

    case 'heartbeat':
      return null // Don't show heartbeats

    case 'info':
      return (
        <div className="text-gray-400">
          <span className="text-gray-500 mr-2">{time}</span>
          {String(event.data.message || '')}
        </div>
      )

    default:
      return (
        <div className="text-gray-500">
          <span className="mr-2">{time}</span>
          [{event.type}] {JSON.stringify(event.data).slice(0, 100)}
        </div>
      )
  }
}

function formatEventForCopy(event: SSEEvent): string {
  const time = event.timestamp.toISOString()
  switch (event.type) {
    case 'text':
      return `[${time}] ${event.data.content}`
    case 'tool_call':
      return `[${time}] Tool: ${event.data.name}`
    case 'tool_result':
      return `[${time}] Result: ${String(event.data.result).slice(0, 500)}`
    case 'error':
      return `[${time}] Error: ${event.data.message}`
    default:
      return `[${time}] [${event.type}] ${JSON.stringify(event.data)}`
  }
}
