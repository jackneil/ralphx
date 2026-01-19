import { Link } from 'react-router-dom'
import type { Workflow } from '../../api'
import { formatLocalDate } from '../../utils/time'

interface WorkflowCardProps {
  workflow: Workflow
  projectSlug: string
}

export default function WorkflowCard({ workflow, projectSlug }: WorkflowCardProps) {
  const steps = workflow.steps || []
  const completedSteps = steps.filter(s => s.status === 'completed' || s.status === 'skipped').length
  const totalSteps = steps.length
  const progressPercent = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0

  // Determine if workflow is actually running vs just "active"
  const isActuallyRunning = steps.some(s => s.has_active_run === true)

  // Map workflow.status to display status
  const getDisplayStatus = () => {
    if (workflow.status === 'active') {
      return isActuallyRunning ? 'running' : 'idle'
    }
    return workflow.status
  }

  const displayStatus = getDisplayStatus()

  const statusColors: Record<string, string> = {
    draft: 'bg-gray-600',
    running: 'bg-green-600',
    idle: 'bg-amber-600',
    active: 'bg-green-600', // Keep for fallback
    paused: 'bg-yellow-600',
    completed: 'bg-blue-600',
    failed: 'bg-red-600',
  }

  const statusIcons: Record<string, React.ReactNode> = {
    draft: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    ),
    running: (
      <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    idle: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    active: (
      <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    paused: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    completed: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    failed: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  }

  const currentStep = steps.find(s => s.step_number === workflow.current_step)

  return (
    <Link
      to={`/projects/${projectSlug}/workflows/${workflow.id}`}
      className="card hover:border-gray-600 transition-colors block"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-white mb-1">{workflow.name}</h3>
          <div className="flex items-center space-x-2">
            <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-xs font-medium text-white ${statusColors[displayStatus]}`}>
              {statusIcons[displayStatus]}
              <span>{displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-sm text-gray-400 mb-1">
          <span>Progress</span>
          <span>{completedSteps} / {totalSteps} steps</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary-500 transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Current Step */}
      {currentStep && workflow.status !== 'completed' && (
        <div className="text-sm text-gray-400">
          <span className="text-gray-500">Current: </span>
          <span className="text-gray-300">{currentStep.name}</span>
          {currentStep.step_type === 'interactive' && (
            <span className="ml-2 text-primary-400">(Chat)</span>
          )}
        </div>
      )}

      {/* Timestamps */}
      <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-500">
        Created {formatLocalDate(workflow.created_at)}
      </div>
    </Link>
  )
}
