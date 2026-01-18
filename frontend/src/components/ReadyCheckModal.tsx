import { useState, useEffect, useCallback } from 'react'
import {
  triggerReadyCheck,
  submitReadyCheckAnswers,
  type ReadyCheckQuestion,
  type ReadyCheckAnswer,
} from '../api'

interface ReadyCheckModalProps {
  projectSlug: string
  loopName: string
  onClose: () => void
  onComplete: (startLoop: boolean) => void
}

type ModalState = 'analyzing' | 'questions' | 'ready' | 'error' | 'saving'

export default function ReadyCheckModal({
  projectSlug,
  loopName,
  onClose,
  onComplete,
}: ReadyCheckModalProps) {
  const [state, setState] = useState<ModalState>('analyzing')
  const [questions, setQuestions] = useState<ReadyCheckQuestion[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [assessment, setAssessment] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  // Handle Escape key to close modal
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && state !== 'saving' && state !== 'analyzing') {
        onClose()
      }
    },
    [onClose, state]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Trigger the ready check on mount or retry
  useEffect(() => {
    let cancelled = false
    let pollTimeout: ReturnType<typeof setTimeout> | null = null

    const processResult = (result: Awaited<ReturnType<typeof triggerReadyCheck>>) => {
      if (result.status === 'ready') {
        setState('ready')
        setAssessment(result.assessment || 'Ready to start')
        return true // Done
      } else if (result.status === 'questions') {
        // Defensive: ensure questions is a non-empty array
        const questionList = Array.isArray(result.questions) ? result.questions : []
        if (questionList.length === 0) {
          // No questions means ready
          setState('ready')
          setAssessment(result.assessment || 'No clarifications needed')
        } else {
          setState('questions')
          setQuestions(questionList)
          setAssessment(result.assessment || '')
          // Initialize answers
          const initialAnswers: Record<string, string> = {}
          questionList.forEach((q) => {
            initialAnswers[q.id] = ''
          })
          setAnswers(initialAnswers)
        }
        return true // Done
      } else if (result.status === 'analyzing') {
        // Backend still processing - poll again
        return false
      } else {
        // Unexpected status from API - treat as error
        setState('error')
        setError(`Unexpected response status: ${result.status}`)
        return true // Done (error state)
      }
    }

    const runCheck = async () => {
      try {
        const result = await triggerReadyCheck(projectSlug, loopName)
        if (cancelled) return

        const done = processResult(result)
        if (!done && !cancelled) {
          // Poll again after 2 seconds
          pollTimeout = setTimeout(runCheck, 2000)
        }
      } catch (err) {
        if (cancelled) return
        setState('error')
        setError(err instanceof Error ? err.message : 'Failed to run ready check')
      }
    }

    runCheck()

    return () => {
      cancelled = true
      if (pollTimeout) clearTimeout(pollTimeout)
    }
  }, [projectSlug, loopName, retryCount])

  const handleAnswerChange = (questionId: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  const allAnswered = questions.every((q) => answers[q.id]?.trim())

  const handleSubmit = async (startAfter: boolean) => {
    if (!allAnswered) return

    setState('saving')
    try {
      const answerList: ReadyCheckAnswer[] = questions.map((q) => ({
        question_id: q.id,
        answer: answers[q.id],
      }))

      await submitReadyCheckAnswers(projectSlug, loopName, questions, answerList)
      onComplete(startAfter)
    } catch (err) {
      setState('error')
      setError(err instanceof Error ? err.message : 'Failed to save answers')
    }
  }

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // Only close if clicking the backdrop itself, not the modal content
    if (e.target === e.currentTarget && state !== 'saving' && state !== 'analyzing') {
      onClose()
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={handleBackdropClick}
    >
      <div className="bg-gray-800 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-xl font-semibold text-white">Pre-Flight Ready Check</h2>
          {state !== 'saving' && state !== 'analyzing' && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white text-2xl leading-none"
              aria-label="Close modal"
            >
              &times;
            </button>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {state === 'analyzing' && (
            <div className="text-center py-8">
              <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-300">Analyzing loop configuration...</p>
              <p className="text-sm text-gray-500 mt-2">
                Claude is reviewing your resources and configuration
              </p>
            </div>
          )}

          {state === 'ready' && (
            <div className="text-center py-8">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg
                  className="w-8 h-8 text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-white mb-2">Ready to Start</h3>
              <p className="text-gray-400">{assessment}</p>
            </div>
          )}

          {state === 'questions' && (
            <div className="space-y-6">
              {assessment && (
                <div className="bg-gray-700/50 rounded-lg p-4 mb-4">
                  <p className="text-sm text-gray-300">{assessment}</p>
                </div>
              )}

              <p className="text-gray-300">
                Claude has {questions.length} question{questions.length !== 1 ? 's' : ''} before
                starting:
              </p>

              {questions.map((q, index) => (
                <div key={q.id} className="bg-gray-700/30 rounded-lg p-4">
                  <div className="flex items-start gap-3 mb-3">
                    <span className="bg-primary-500/20 text-primary-400 px-2 py-0.5 rounded text-sm font-medium">
                      {index + 1}. {q.category}
                    </span>
                  </div>

                  <div className="bg-gray-800 rounded p-3 mb-3">
                    <p className="text-gray-200">{q.question}</p>
                    {q.context && <p className="text-sm text-gray-500 mt-2">{q.context}</p>}
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Your answer:</label>
                    <textarea
                      value={answers[q.id] || ''}
                      onChange={(e) => handleAnswerChange(q.id, e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white resize-none"
                      rows={3}
                      maxLength={10000}
                      placeholder="Enter your answer..."
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {state === 'saving' && (
            <div className="text-center py-8">
              <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-gray-300">Saving your answers...</p>
            </div>
          )}

          {state === 'error' && (
            <div className="text-center py-8">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg
                  className="w-8 h-8 text-red-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-white mb-2">Error</h3>
              <p className="text-red-400">{error}</p>
              <div className="mt-4 flex justify-center gap-3">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
                >
                  Close
                </button>
                <button
                  onClick={() => {
                    setError(null)
                    setState('analyzing')
                    setRetryCount((c) => c + 1)
                  }}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded text-white"
                >
                  Retry
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {(state === 'questions' || state === 'ready') && (
          <div className="px-6 py-4 border-t border-gray-700 flex justify-end gap-3">
            {state === 'ready' && (
              <>
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-gray-400 hover:text-white"
                >
                  Close
                </button>
                <button
                  onClick={() => onComplete(true)}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded text-white"
                >
                  Start Loop
                </button>
              </>
            )}

            {state === 'questions' && (
              <>
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleSubmit(false)}
                  disabled={!allAnswered}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Save Without Starting
                </button>
                <button
                  onClick={() => handleSubmit(true)}
                  disabled={!allAnswered}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-500 rounded text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Save & Start Loop
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
