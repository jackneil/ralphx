import { useState, useEffect, useCallback, useRef } from 'react'

export interface SSEEvent {
  type: string
  data: Record<string, unknown>
  timestamp: Date
}

interface UseSSEOptions {
  url: string
  enabled?: boolean
  onEvent?: (event: SSEEvent) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  retryInterval?: number
  maxRetries?: number
  maxStoredEvents?: number
}

interface UseSSEResult {
  events: SSEEvent[]
  isConnected: boolean
  error: string | null
  connect: () => void
  disconnect: () => void
  clearEvents: () => void
}

export function useSSE({
  url,
  enabled = true,
  onEvent,
  onError,
  onOpen,
  retryInterval = 3000,
  maxRetries = 5,
  maxStoredEvents = 1000,
}: UseSSEOptions): UseSSEResult {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)
  const retriesRef = useRef(0)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearEvents = useCallback(() => {
    setEvents([])
  }, [])

  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsConnected(false)
  }, [])

  const connect = useCallback(() => {
    disconnect()
    setError(null)

    try {
      const eventSource = new EventSource(url)
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        setIsConnected(true)
        setError(null)
        retriesRef.current = 0
        onOpen?.()
      }

      eventSource.onerror = (e) => {
        // Close the EventSource immediately to prevent the browser's native
        // auto-reconnect from firing additional onerror events, which could
        // cause multiple concurrent reconnection timeouts and leaked EventSources.
        eventSource.close()
        eventSourceRef.current = null
        setIsConnected(false)
        onError?.(e)

        // Attempt reconnection (only if no retry is already scheduled)
        if (retryTimeoutRef.current) return
        if (retriesRef.current < maxRetries) {
          retriesRef.current += 1
          setError(`Connection lost. Retrying (${retriesRef.current}/${maxRetries})...`)
          retryTimeoutRef.current = setTimeout(() => {
            retryTimeoutRef.current = null
            connect()
          }, retryInterval)
        } else {
          setError('Connection failed after maximum retries')
        }
      }

      // Handle different event types
      const eventTypes = [
        'connected',
        'status',
        'text',
        'tool_call',
        'tool_result',
        'thinking',
        'usage',
        'init',
        'complete',
        'error',
        'heartbeat',
        'info',
        'session_start',
        'disconnected',
      ]

      eventTypes.forEach((eventType) => {
        eventSource.addEventListener(eventType, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data)
            const event: SSEEvent = {
              type: eventType,
              data,
              timestamp: new Date(),
            }

            // Limit stored events to prevent memory leak for long-running sessions
            setEvents((prev) => {
              const newEvents = [...prev, event]
              return newEvents.length > maxStoredEvents
                ? newEvents.slice(-maxStoredEvents)
                : newEvents
            })
            onEvent?.(event)
          } catch {
            // Ignore parse errors
          }
        })
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect')
    }
  }, [url, disconnect, onOpen, onError, onEvent, maxRetries, retryInterval, maxStoredEvents])

  useEffect(() => {
    if (enabled) {
      connect()
    } else {
      disconnect()
    }

    return () => {
      disconnect()
    }
  }, [enabled, connect, disconnect])

  return {
    events,
    isConnected,
    error,
    connect,
    disconnect,
    clearEvents,
  }
}
