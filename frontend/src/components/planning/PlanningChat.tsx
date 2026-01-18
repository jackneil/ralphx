import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getPlanningSession,
  sendPlanningMessage,
  streamPlanningResponse,
  completePlanningSession,
} from '../../api'
import type { PlanningSession } from '../../api'
import ChatMessage from './ChatMessage'
import ArtifactPreview from './ArtifactPreview'

interface PlanningChatProps {
  projectSlug: string
  workflowId: string
  onComplete: () => void
}

export default function PlanningChat({ projectSlug, workflowId, onComplete }: PlanningChatProps) {
  const [session, setSession] = useState<PlanningSession | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamedContent, setStreamedContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showArtifacts, setShowArtifacts] = useState(false)
  const [completing, setCompleting] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadSession = useCallback(async () => {
    try {
      const data = await getPlanningSession(projectSlug, workflowId)
      setSession(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, workflowId])

  useEffect(() => {
    loadSession()
  }, [loadSession])

  useEffect(() => {
    scrollToBottom()
  }, [session?.messages, streamedContent])

  const handleSend = async () => {
    if (!input.trim() || sending || streaming) return

    const message = input.trim()
    setInput('')
    setSending(true)
    setError(null)

    try {
      // Send the user message
      const updatedSession = await sendPlanningMessage(projectSlug, workflowId, message)
      setSession(updatedSession)

      // Start streaming the response
      setStreaming(true)
      setStreamedContent('')

      // Close any existing EventSource before creating a new one
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const eventSource = streamPlanningResponse(projectSlug, workflowId)
      eventSourceRef.current = eventSource

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'content') {
            setStreamedContent((prev) => prev + data.content)
          } else if (data.type === 'error') {
            eventSource.close()
            eventSourceRef.current = null
            setStreaming(false)
            setError(data.message || 'An error occurred')
          } else if (data.type === 'done') {
            eventSource.close()
            eventSourceRef.current = null
            setStreaming(false)
            loadSession() // Reload to get the assistant message
          }
        } catch (parseError) {
          // Handle malformed SSE data gracefully
          console.error('Failed to parse SSE event:', parseError, event.data)
          // Don't close connection for parse errors - might be temporary
        }
      }

      eventSource.onerror = () => {
        eventSource.close()
        eventSourceRef.current = null
        setStreaming(false)
        setError('Connection lost. Please try again.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleComplete = async () => {
    if (!session) return

    setCompleting(true)
    try {
      await completePlanningSession(projectSlug, workflowId, session.artifacts)
      onComplete()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete session')
      setCompleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-400">Loading planning session...</div>
      </div>
    )
  }

  if (error && !session) {
    return (
      <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400">
        {error}
      </div>
    )
  }

  const hasMessages = session && session.messages.length > 0
  const hasArtifacts = session?.artifacts && (session.artifacts.design_doc || session.artifacts.guardrails)

  return (
    <div className="flex flex-col h-[600px]">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        {/* Welcome message if no messages */}
        {!hasMessages && !streaming && (
          <div className="text-center py-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-primary-900/30 flex items-center justify-center">
              <svg className="w-8 h-8 text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Let's plan your project</h3>
            <p className="text-gray-400 max-w-md mx-auto">
              Describe what you want to build, and I'll help you create a detailed design document.
            </p>
          </div>
        )}

        {/* Chat Messages */}
        {session?.messages.map((message, index) => (
          <ChatMessage key={index} message={message} />
        ))}

        {/* Streaming Response */}
        {streaming && streamedContent && (
          <ChatMessage
            message={{
              role: 'assistant',
              content: streamedContent,
              timestamp: new Date().toISOString(),
            }}
            isStreaming
          />
        )}

        {/* Loading indicator */}
        {sending && !streaming && (
          <div className="flex items-center space-x-2 text-gray-400">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error message */}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-900/20 border border-red-800 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Artifacts Preview */}
      {hasArtifacts && (
        <div className="mb-4">
          <button
            onClick={() => setShowArtifacts(!showArtifacts)}
            className="flex items-center space-x-2 text-sm text-primary-400 hover:text-primary-300"
          >
            <svg
              className={`w-4 h-4 transition-transform ${showArtifacts ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            <span>View Generated Artifacts</span>
          </button>
          {showArtifacts && session?.artifacts && (
            <ArtifactPreview artifacts={session.artifacts} />
          )}
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-700 pt-4">
        <div className="flex items-end space-x-3">
          <div className="flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your project or answer questions..."
              rows={3}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 resize-none"
              disabled={sending || streaming}
            />
          </div>
          <div className="flex flex-col space-y-2">
            <button
              onClick={handleSend}
              disabled={!input.trim() || sending || streaming}
              className="px-4 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-500 transition-colors disabled:opacity-50"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>

        {/* Complete Button */}
        {hasMessages && (
          <div className="mt-4 flex justify-end">
            <button
              onClick={handleComplete}
              disabled={completing || sending || streaming}
              className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500 transition-colors disabled:opacity-50"
            >
              {completing ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Completing...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Complete Planning</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
