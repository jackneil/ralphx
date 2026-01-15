import { useState, useEffect, useRef } from 'react'
import { startLoop, stopLoop, pauseLoop, resumeLoop, getLoopPhases, PhaseInfoResponse, StartLoopOptions } from '../api'

interface LoopControlProps {
  projectSlug: string
  loopName: string
  loopType?: string
  isRunning: boolean
  isPaused: boolean
  onStatusChange?: () => void
}

export default function LoopControl({
  projectSlug,
  loopName,
  loopType,
  isRunning,
  isPaused,
  onStatusChange,
}: LoopControlProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showStartOptions, setShowStartOptions] = useState(false)
  const [phaseInfo, setPhaseInfo] = useState<PhaseInfoResponse | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Click outside to close dropdown
  useEffect(() => {
    if (!showStartOptions) return

    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowStartOptions(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showStartOptions])

  // Start options state
  const [selectedPhase, setSelectedPhase] = useState<number | undefined>(undefined)
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(undefined)
  const [respectDependencies, setRespectDependencies] = useState(true)
  const [batchMode, setBatchMode] = useState(false)
  const [batchSize, setBatchSize] = useState(10)

  // Load phase info for consumer loops
  useEffect(() => {
    if (loopType !== 'consumer' || isRunning) return

    let isMounted = true
    getLoopPhases(projectSlug, loopName)
      .then(info => {
        if (isMounted) setPhaseInfo(info)
      })
      .catch(() => {
        if (isMounted) setPhaseInfo(null)
      })

    return () => { isMounted = false }
  }, [projectSlug, loopName, loopType, isRunning])

  const handleAction = async (action: () => Promise<unknown>) => {
    setLoading(true)
    setError(null)
    try {
      await action()
      onStatusChange?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setLoading(false)
    }
  }

  const handleStart = async () => {
    const options: StartLoopOptions = {}

    if (selectedPhase !== undefined) {
      options.phase = selectedPhase
    }
    if (selectedCategory) {
      options.category = selectedCategory
    }
    options.respect_dependencies = respectDependencies
    options.batch_mode = batchMode
    if (batchMode) {
      options.batch_size = batchSize
    }

    await handleAction(() => startLoop(projectSlug, loopName, options))
    setShowStartOptions(false)
  }

  const isConsumer = loopType === 'consumer' || phaseInfo?.source_loop

  return (
    <div className="flex flex-col">
      <div className="flex items-center space-x-3">
        {!isRunning && (
          <>
            {isConsumer && phaseInfo && phaseInfo.total_items > 0 ? (
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowStartOptions(!showStartOptions)}
                  className="btn-primary disabled:opacity-50 flex items-center space-x-2"
                  aria-haspopup="true"
                  aria-expanded={showStartOptions}
                  aria-label="Start loop with options"
                >
                  <PlayIcon />
                  <span>Start</span>
                  <ChevronIcon />
                </button>

                {showStartOptions && (
                  <div className="absolute top-full left-0 mt-2 w-80 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50 p-4">
                    <div className="space-y-4">
                      {/* Phase selection */}
                      {phaseInfo.phases.length > 0 && (
                        <div>
                          <label htmlFor="phaseSelect" className="block text-sm font-medium text-gray-300 mb-1">
                            Phase
                          </label>
                          <select
                            id="phaseSelect"
                            value={selectedPhase ?? ''}
                            onChange={(e) => setSelectedPhase(e.target.value ? parseInt(e.target.value) : undefined)}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                          >
                            <option value="">All Phases</option>
                            {phaseInfo.phases.map(phase => (
                              <option key={phase.phase_number} value={phase.phase_number}>
                                Phase {phase.phase_number} ({phase.pending_count} pending / {phase.item_count} total)
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      {/* Category selection */}
                      {phaseInfo.categories.length > 0 && (
                        <div>
                          <label htmlFor="categorySelect" className="block text-sm font-medium text-gray-300 mb-1">
                            Category
                          </label>
                          <select
                            id="categorySelect"
                            value={selectedCategory ?? ''}
                            onChange={(e) => setSelectedCategory(e.target.value || undefined)}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                          >
                            <option value="">All Categories</option>
                            {phaseInfo.categories.map(cat => (
                              <option key={cat.name} value={cat.name}>
                                {cat.name.toUpperCase()} ({cat.pending_count} pending / {cat.item_count} total)
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      {/* Dependency ordering */}
                      {phaseInfo.has_dependencies && (
                        <div className="flex items-center space-x-2">
                          <input
                            type="checkbox"
                            id="respectDeps"
                            checked={respectDependencies}
                            onChange={(e) => setRespectDependencies(e.target.checked)}
                            className="rounded bg-gray-700 border-gray-600"
                          />
                          <label htmlFor="respectDeps" className="text-sm text-gray-300">
                            Respect dependency order
                          </label>
                        </div>
                      )}

                      {/* Batch mode */}
                      <div className="space-y-2">
                        <div className="flex items-center space-x-2">
                          <input
                            type="checkbox"
                            id="batchMode"
                            checked={batchMode}
                            onChange={(e) => setBatchMode(e.target.checked)}
                            className="rounded bg-gray-700 border-gray-600"
                          />
                          <label htmlFor="batchMode" className="text-sm text-gray-300">
                            Batch mode (implement multiple together)
                          </label>
                        </div>

                        {batchMode && (
                          <div className="ml-6">
                            <label htmlFor="batchSizeInput" className="block text-xs text-gray-400 mb-1">
                              Batch size
                            </label>
                            <input
                              id="batchSizeInput"
                              type="number"
                              min={1}
                              max={50}
                              value={batchSize}
                              onChange={(e) => setBatchSize(Math.min(50, Math.max(1, parseInt(e.target.value) || 10)))}
                              className="w-20 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                            />
                          </div>
                        )}
                      </div>

                      {/* Warnings from API */}
                      {phaseInfo.warnings && phaseInfo.warnings.length > 0 && (
                        <div className="space-y-1">
                          {phaseInfo.warnings.map((warning, index) => (
                            <div key={index} className="text-xs text-yellow-400 flex items-start space-x-1">
                              <WarningIcon />
                              <span>{warning}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Stats summary */}
                      <div className="text-xs text-gray-400 border-t border-gray-700 pt-2">
                        {phaseInfo.total_items} total items from {phaseInfo.source_loop}
                        {phaseInfo.graph_stats.items_with_dependencies > 0 && (
                          <span> | {phaseInfo.graph_stats.items_with_dependencies} with dependencies</span>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex justify-end space-x-2 pt-2 border-t border-gray-700">
                        <button
                          onClick={() => setShowStartOptions(false)}
                          className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleStart}
                          disabled={loading}
                          className="px-4 py-1.5 text-sm bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
                        >
                          {loading ? 'Starting...' : 'Start Loop'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => handleAction(() => startLoop(projectSlug, loopName))}
                disabled={loading}
                className="btn-primary disabled:opacity-50 flex items-center space-x-2"
              >
                <PlayIcon />
                <span>Start</span>
              </button>
            )}
          </>
        )}

        {isRunning && !isPaused && (
          <>
            <button
              onClick={() => handleAction(() => pauseLoop(projectSlug, loopName))}
              disabled={loading}
              className="btn-secondary disabled:opacity-50 flex items-center space-x-2"
            >
              <PauseIcon />
              <span>Pause</span>
            </button>
            <button
              onClick={() => handleAction(() => stopLoop(projectSlug, loopName))}
              disabled={loading}
              className="btn-danger disabled:opacity-50 flex items-center space-x-2"
            >
              <StopIcon />
              <span>Stop</span>
            </button>
          </>
        )}

        {isRunning && isPaused && (
          <>
            <button
              onClick={() => handleAction(() => resumeLoop(projectSlug, loopName))}
              disabled={loading}
              className="btn-primary disabled:opacity-50 flex items-center space-x-2"
            >
              <PlayIcon />
              <span>Resume</span>
            </button>
            <button
              onClick={() => handleAction(() => stopLoop(projectSlug, loopName))}
              disabled={loading}
              className="btn-danger disabled:opacity-50 flex items-center space-x-2"
            >
              <StopIcon />
              <span>Stop</span>
            </button>
          </>
        )}

        {loading && (
          <span className="text-sm text-gray-400 animate-pulse">
            Processing...
          </span>
        )}
      </div>

      {error && (
        <div className="mt-2 text-sm text-red-400" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}

function PlayIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function WarningIcon() {
  return (
    <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}
