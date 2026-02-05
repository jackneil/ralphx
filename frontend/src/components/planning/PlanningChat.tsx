import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getPlanningSession,
  sendPlanningMessage,
  streamPlanningResponse,
  completePlanningSession,
  getDesignDocFile,
  saveDesignDocFile,
  listDesignDocBackups,
} from '../../api'
import type { PlanningSession, DesignDocBackup } from '../../api'
import ChatMessage from './ChatMessage'
import ArtifactPreview from './ArtifactPreview'

interface PlanningChatProps {
  projectSlug: string
  workflowId: string
  designDocPath?: string  // Optional: if set, load/edit this file instead of creating new
  onComplete: () => void
}

export default function PlanningChat({ projectSlug, workflowId, designDocPath, onComplete }: PlanningChatProps) {
  const [session, setSession] = useState<PlanningSession | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamedContent, setStreamedContent] = useState('')
  const [toolActivities, setToolActivities] = useState<Array<{
    id: number
    tool: string
    input?: Record<string, unknown>
    result?: string
    startTime: number
    endTime?: number
    status: 'running' | 'completed'
  }>>([])
  const [showToolLog, setShowToolLog] = useState(true) // Auto-show while streaming
  const [error, setError] = useState<string | null>(null)
  const toolIdCounter = useRef(0)
  const [showArtifacts, setShowArtifacts] = useState(false)
  const [completing, setCompleting] = useState(false)

  // Design doc file state
  const [designDocContent, setDesignDocContent] = useState<string | null>(null)
  const [designDocBackups, setDesignDocBackups] = useState<DesignDocBackup[]>([])
  const [loadingDesignDoc, setLoadingDesignDoc] = useState(false)
  const [showBackupsModal, setShowBackupsModal] = useState(false)

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

  // Get the currently running tool (if any)
  const runningTool = toolActivities.find(t => t.status === 'running')

  // Auto-collapse tool log when we get text content (response has started)
  // But keep it expandable

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

  // Cancel streaming - allows user to abort stuck streams
  const cancelStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setStreaming(false)
    setToolActivities([])
    setShowToolLog(true)
    setSending(false)
    loadSession() // Recover any saved content
  }, [loadSession])

  // Load design doc file if path is provided
  const loadDesignDoc = useCallback(async () => {
    if (!designDocPath) return
    setLoadingDesignDoc(true)
    try {
      const [file, backups] = await Promise.all([
        getDesignDocFile(projectSlug, designDocPath),
        listDesignDocBackups(projectSlug, designDocPath),
      ])
      setDesignDocContent(file.content)
      setDesignDocBackups(backups)
    } catch (err) {
      console.error('Failed to load design doc:', err)
      // Don't set error - allow chat to continue even if file doesn't exist
    } finally {
      setLoadingDesignDoc(false)
    }
  }, [projectSlug, designDocPath])

  useEffect(() => {
    loadDesignDoc()
  }, [loadDesignDoc])

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
      setToolActivities([])
      setShowToolLog(true)
      toolIdCounter.current = 0

      // Close any existing EventSource before creating a new one
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const eventSource = streamPlanningResponse(projectSlug, workflowId)
      eventSourceRef.current = eventSource

      let afterToolUse = false // Track if we need paragraph break after tool

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'debug') {
            console.log('[Planning Debug]', data.msg)
          } else if (data.type === 'content') {
            // Mark any running tools as completed when we get text
            setToolActivities(prev => prev.map(t =>
              t.status === 'running' ? { ...t, status: 'completed' as const, endTime: Date.now() } : t
            ))
            // Auto-collapse tool log when response text starts coming in
            setShowToolLog(false)
            // Add paragraph break if this text comes after a tool use
            const prefix = afterToolUse ? '\n\n' : ''
            afterToolUse = false
            setStreamedContent((prev) => prev + prefix + data.content)
          } else if (data.type === 'tool_use') {
            // Add to tool activity log
            afterToolUse = true
            const newId = ++toolIdCounter.current
            setToolActivities(prev => [
              // Mark previous running tools as completed
              ...prev.map(t => t.status === 'running' ? { ...t, status: 'completed' as const, endTime: Date.now() } : t),
              // Add new tool
              {
                id: newId,
                tool: data.tool,
                input: data.input,
                startTime: Date.now(),
                status: 'running' as const,
              }
            ])
          } else if (data.type === 'tool_result') {
            // Mark the tool as completed with result
            setToolActivities(prev => prev.map(t =>
              t.status === 'running' ? {
                ...t,
                status: 'completed' as const,
                endTime: Date.now(),
                result: data.result
              } : t
            ))
          } else if (data.type === 'error') {
            eventSource.close()
            eventSourceRef.current = null
            setStreaming(false)
            setToolActivities([])
            setError(data.message || 'An error occurred')
            // Still reload session - partial content may have been saved
            loadSession()
          } else if (data.type === 'done') {
            eventSource.close()
            eventSourceRef.current = null
            setStreaming(false)
            // Keep tool activities for review, but ensure all are marked completed
            setToolActivities(prev => prev.map(t =>
              t.status === 'running' ? { ...t, status: 'completed' as const, endTime: Date.now() } : t
            ))
            loadSession() // Reload to get the assistant message
          }
        } catch (parseError) {
          // Handle malformed SSE data gracefully
          console.error('Failed to parse SSE event:', parseError, event.data)
          // Don't close connection for parse errors - might be temporary
        }
      }

      eventSource.onerror = (err) => {
        console.error('[Planning] EventSource error:', err)
        eventSource.close()
        eventSourceRef.current = null
        setStreaming(false)
        setToolActivities([])
        setError('Connection lost. Please try again.')
        loadSession() // Try to recover any saved content
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
      // If we have a design doc path and a design_doc artifact, save to file
      if (designDocPath && session.artifacts?.design_doc) {
        await saveDesignDocFile(projectSlug, designDocPath, session.artifacts.design_doc)
      }

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
      {/* Design Doc File Header */}
      {designDocPath && (
        <div className="mb-4 p-3 rounded-lg bg-blue-900/20 border border-blue-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <div>
                <div className="text-sm font-medium text-blue-300">
                  Editing: {designDocPath}
                </div>
                <div className="text-xs text-blue-400/70">
                  {loadingDesignDoc ? (
                    'Loading file...'
                  ) : designDocContent !== null ? (
                    `${(designDocContent.length / 1024).toFixed(1)} KB • ${designDocBackups.length} backup${designDocBackups.length !== 1 ? 's' : ''} available`
                  ) : (
                    'File not found - will be created on save'
                  )}
                </div>
              </div>
            </div>
            {designDocBackups.length > 0 && (
              <button
                onClick={() => setShowBackupsModal(true)}
                className="text-xs text-blue-400 hover:text-blue-300 underline"
              >
                View Backups
              </button>
            )}
          </div>
        </div>
      )}

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

        {/* Tool Activity Log - shows work being done (only while streaming) */}
        {streaming && toolActivities.length > 0 && (
          <div className="rounded-lg border border-gray-700/50 bg-gray-800/30 overflow-hidden">
            {/* Header - clickable to expand/collapse */}
            <button
              onClick={() => setShowToolLog(!showToolLog)}
              className="w-full px-3 py-2 flex items-center justify-between text-sm hover:bg-gray-700/30 transition-colors"
            >
              <div className="flex items-center space-x-2">
                {runningTool ? (
                  <div className="w-3 h-3 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                <span className="text-gray-400">
                  {runningTool ? (
                    <>Working: <span className="text-primary-400">{runningTool.tool}</span></>
                  ) : (
                    <>{toolActivities.length} tool{toolActivities.length !== 1 ? 's' : ''} used</>
                  )}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                {streaming && (
                  <button
                    onClick={(e) => { e.stopPropagation(); cancelStreaming(); }}
                    className="text-xs text-red-400 hover:text-red-300 px-2 py-0.5 rounded hover:bg-red-900/20"
                  >
                    Cancel
                  </button>
                )}
                <svg
                  className={`w-4 h-4 text-gray-500 transition-transform ${showToolLog ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>

            {/* Expanded tool list */}
            {showToolLog && (
              <div className="border-t border-gray-700/50 px-3 py-2 space-y-1 max-h-48 overflow-y-auto">
                {toolActivities.map((activity) => (
                  <div
                    key={activity.id}
                    className={`flex items-start space-x-2 text-xs py-1 ${
                      activity.status === 'running' ? 'text-primary-400' : 'text-gray-500'
                    }`}
                  >
                    {activity.status === 'running' ? (
                      <div className="w-3 h-3 mt-0.5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    ) : (
                      <svg className="w-3 h-3 mt-0.5 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    <div className="flex-1 min-w-0">
                      <span className={activity.status === 'running' ? 'text-primary-400 font-medium' : 'text-gray-400'}>
                        {activity.tool}
                      </span>
                      {activity.input && (
                        <span className="text-gray-500 ml-1 truncate">
                          {(() => {
                            const input = activity.input
                            if (input.query) return `"${String(input.query).slice(0, 40)}..."`
                            if (input.url) return String(input.url).slice(0, 50)
                            if (input.file_path) return String(input.file_path).split('/').pop()
                            if (input.pattern) return `${input.pattern}`
                            if (input.command) return `$ ${String(input.command).slice(0, 30)}...`
                            return ''
                          })()}
                        </span>
                      )}
                      {activity.endTime && (
                        <span className="text-gray-600 ml-1">
                          ({((activity.endTime - activity.startTime) / 1000).toFixed(1)}s)
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Streaming Response - appears after tool log */}
        {streaming && streamedContent && (
          <>
            <ChatMessage
              message={{
                role: 'assistant',
                content: streamedContent,
                timestamp: new Date().toISOString(),
              }}
              isStreaming
            />
            {/* Cancel button for streaming with content */}
            {!runningTool && (
              <div className="flex justify-end">
                <button
                  onClick={cancelStreaming}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20"
                >
                  Cancel
                </button>
              </div>
            )}
          </>
        )}

        {/* Initial thinking indicator (before any response or tool use) */}
        {streaming && !streamedContent && toolActivities.length === 0 && (
          <div className="flex items-center justify-between px-4 py-2">
            <div className="flex items-center space-x-3 text-gray-400">
              <div className="w-4 h-4 border-2 border-gray-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">Thinking...</span>
            </div>
            <button
              onClick={cancelStreaming}
              className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Loading indicator (sending message) */}
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

      {/* Backups Modal */}
      {showBackupsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 max-h-[80vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Design Doc Backups</h3>
              <button
                onClick={() => setShowBackupsModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-sm text-gray-400 mb-4">
              Backups are created automatically each time you save changes.
            </p>
            <div className="overflow-y-auto flex-1 space-y-2">
              {designDocBackups.length === 0 ? (
                <p className="text-gray-500 text-sm">No backups available yet.</p>
              ) : (
                designDocBackups.map((backup, index) => (
                  <div
                    key={backup.path}
                    className="p-3 bg-gray-700/50 rounded-lg flex items-center justify-between"
                  >
                    <div>
                      <div className="text-sm text-white">{backup.name}</div>
                      <div className="text-xs text-gray-400">
                        {new Date(backup.created).toLocaleString()} • {(backup.size / 1024).toFixed(1)} KB
                      </div>
                    </div>
                    {index === 0 && (
                      <span className="text-xs bg-blue-600/30 text-blue-300 px-2 py-1 rounded">
                        Latest
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
            <div className="mt-4 pt-4 border-t border-gray-700">
              <button
                onClick={() => setShowBackupsModal(false)}
                className="w-full px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
