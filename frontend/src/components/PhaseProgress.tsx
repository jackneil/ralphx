import { useEffect, useState, useId } from 'react'
import { getLoopPhases, PhaseInfoResponse, PhaseInfo } from '../api'

interface PhaseProgressProps {
  projectSlug: string
  loopName: string
  refreshInterval?: number // ms, 0 to disable
}

export default function PhaseProgress({
  projectSlug,
  loopName,
  refreshInterval = 5000,
}: PhaseProgressProps) {
  const instanceId = useId()
  const [phaseInfo, setPhaseInfo] = useState<PhaseInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const fetchPhaseInfo = async () => {
      try {
        const info = await getLoopPhases(projectSlug, loopName)
        if (isMounted) {
          setPhaseInfo(info)
          setError(null)
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load phases')
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    fetchPhaseInfo()

    let interval: ReturnType<typeof setInterval> | undefined
    if (refreshInterval > 0) {
      interval = setInterval(fetchPhaseInfo, refreshInterval)
    }

    return () => {
      isMounted = false
      if (interval) {
        clearInterval(interval)
      }
    }
  }, [projectSlug, loopName, refreshInterval])

  if (loading) {
    return (
      <div className="animate-pulse bg-gray-800 rounded-lg p-4">
        <div className="h-4 bg-gray-700 rounded w-1/4 mb-4"></div>
        <div className="space-y-3">
          <div className="h-8 bg-gray-700 rounded"></div>
          <div className="h-8 bg-gray-700 rounded"></div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-400">
        {error}
      </div>
    )
  }

  if (!phaseInfo || !phaseInfo.source_step_id) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-400">
        Not a consumer loop - no phases to display
      </div>
    )
  }

  if (phaseInfo.total_items === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-400">
        No items found from source step
      </div>
    )
  }

  // Calculate overall progress
  const totalCompleted = phaseInfo.phases.reduce((sum, p) => sum + p.completed_count, 0)
  const overallProgress = (totalCompleted / phaseInfo.total_items) * 100

  return (
    <div className="bg-gray-800 rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white">
          Phase Progress
        </h3>
        <span className="text-sm text-gray-400">
          Step {phaseInfo.source_step_id}
        </span>
      </div>

      {/* Overall progress bar */}
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-400" id={`${instanceId}-overall-label`}>Overall</span>
          <span className="text-gray-300">
            {totalCompleted} / {phaseInfo.total_items} ({overallProgress.toFixed(0)}%)
          </span>
        </div>
        <div
          className="h-3 bg-gray-700 rounded-full overflow-hidden"
          role="progressbar"
          aria-valuenow={Math.round(overallProgress)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-labelledby={`${instanceId}-overall-label`}
        >
          <div
            className="h-full bg-gradient-to-r from-green-500 to-green-400 transition-all duration-500"
            style={{ width: `${overallProgress}%` }}
          />
        </div>
      </div>

      {/* Phase breakdown */}
      <div className="space-y-3">
        {phaseInfo.phases.map((phase) => (
          <PhaseBar key={phase.phase_number} phase={phase} instanceId={instanceId} />
        ))}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 pt-2 border-t border-gray-700">
        <div className="text-center">
          <div className="text-2xl font-bold text-white">{phaseInfo.phases.length}</div>
          <div className="text-xs text-gray-400">Phases</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-white">{phaseInfo.categories.length}</div>
          <div className="text-xs text-gray-400">Categories</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-white">
            {phaseInfo.graph_stats.items_with_dependencies || 0}
          </div>
          <div className="text-xs text-gray-400">With Deps</div>
        </div>
      </div>

      {/* Warnings */}
      {phaseInfo.has_cycles && (
        <div className="flex items-center space-x-2 text-yellow-400 text-sm bg-yellow-900/20 rounded p-2">
          <WarningIcon />
          <span>Dependency cycles detected in graph</span>
        </div>
      )}
    </div>
  )
}

function PhaseBar({ phase, instanceId }: { phase: PhaseInfo; instanceId: string }) {
  const progress = phase.item_count > 0
    ? (phase.completed_count / phase.item_count) * 100
    : 0

  const isComplete = phase.completed_count === phase.item_count
  const labelId = `${instanceId}-phase-${phase.phase_number}-label`

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center text-sm">
        <div className="flex items-center space-x-2">
          <span
            id={labelId}
            className={`font-medium ${isComplete ? 'text-green-400' : 'text-gray-300'}`}
          >
            Phase {phase.phase_number}
          </span>
          {phase.categories.length > 0 && (
            <span className="text-xs text-gray-500">
              ({phase.categories.slice(0, 3).join(', ')}
              {phase.categories.length > 3 && ` +${phase.categories.length - 3}`})
            </span>
          )}
        </div>
        <div className="flex items-center space-x-2">
          {isComplete && <CheckIcon />}
          <span className="text-gray-400">
            {phase.completed_count}/{phase.item_count}
          </span>
        </div>
      </div>
      <div
        className="h-2 bg-gray-700 rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={Math.round(progress)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-labelledby={labelId}
      >
        <div
          className={`h-full transition-all duration-500 ${
            isComplete
              ? 'bg-green-500'
              : phase.completed_count > 0
              ? 'bg-blue-500'
              : 'bg-gray-600'
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function WarningIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
      <path
        fillRule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}
