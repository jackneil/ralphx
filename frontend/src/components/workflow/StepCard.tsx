import type { WorkflowStep } from '../../api'

interface StepCardProps {
  step: WorkflowStep
  isCurrent: boolean
  onEdit?: () => void
}

export default function StepCard({ step, isCurrent, onEdit }: StepCardProps) {
  const statusColors: Record<string, string> = {
    pending: 'border-gray-600 bg-gray-800/50',
    active: 'border-primary-500 bg-primary-900/20',
    completed: 'border-green-500 bg-green-900/20',
    skipped: 'border-gray-500 bg-gray-800/30',
  }

  const statusBadgeColors: Record<string, string> = {
    pending: 'bg-gray-600 text-gray-200',
    active: 'bg-primary-600 text-white',
    completed: 'bg-green-600 text-white',
    skipped: 'bg-gray-500 text-gray-200',
  }

  const getStepIcon = () => {
    if (step.step_type === 'interactive') {
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      )
    }
    return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    )
  }

  return (
    <div className={`p-4 rounded-lg border ${statusColors[step.status]} ${isCurrent ? 'ring-2 ring-primary-500' : ''}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center space-x-2">
          <div className={`p-1.5 rounded ${step.status === 'active' ? 'bg-primary-600' : 'bg-gray-700'}`}>
            {getStepIcon()}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium text-white">
                Step {step.step_number}
              </span>
              {isCurrent && (
                <span className="text-xs text-primary-400">Current</span>
              )}
            </div>
            <span className="text-sm text-gray-400">{step.name}</span>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusBadgeColors[step.status]}`}>
            {step.status}
          </span>
          {onEdit && (
            <button
              onClick={onEdit}
              className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
              aria-label={`Edit step ${step.step_number}`}
              title="Edit step"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {step.config?.description && (
        <p className="text-xs text-gray-500 mt-2 line-clamp-2">
          {step.config.description}
        </p>
      )}

      {/* Timestamps */}
      <div className="mt-3 text-xs text-gray-500 space-y-1">
        {step.started_at && (
          <div>Started: {new Date(step.started_at).toLocaleString()}</div>
        )}
        {step.completed_at && (
          <div>Completed: {new Date(step.completed_at).toLocaleString()}</div>
        )}
      </div>

      {/* Artifacts */}
      {step.artifacts && Object.keys(step.artifacts).length > 0 && (
        <div className="mt-3 pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-400 mb-1">Artifacts:</div>
          <div className="flex flex-wrap gap-1">
            {Object.keys(step.artifacts).map(key => (
              <span key={key} className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300">
                {key}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
