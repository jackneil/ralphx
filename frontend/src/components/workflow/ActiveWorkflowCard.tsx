import { Link } from 'react-router-dom'
import type { Workflow } from '../../api'

interface ActiveWorkflowCardProps {
  workflow: Workflow
  projectSlug: string
}

export default function ActiveWorkflowCard({ workflow, projectSlug }: ActiveWorkflowCardProps) {
  const steps = workflow.steps || []
  const completedSteps = steps.filter(s => s.status === 'completed').length
  const totalSteps = steps.length
  const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0

  const currentStep = steps.find(s => s.step_number === workflow.current_step)
  const isInteractive = currentStep?.step_type === 'interactive'

  const statusColors: Record<string, string> = {
    draft: 'bg-gray-600 text-gray-200',
    active: 'bg-green-600 text-green-100',
    paused: 'bg-yellow-600 text-yellow-100',
    completed: 'bg-blue-600 text-blue-100',
    failed: 'bg-red-600 text-red-100',
  }

  const stepStatusIcons: Record<string, React.ReactNode> = {
    pending: (
      <div className="w-3 h-3 rounded-full border-2 border-gray-500" />
    ),
    active: (
      <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
    ),
    completed: (
      <svg className="w-3 h-3 text-green-400" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
    ),
    skipped: (
      <svg className="w-3 h-3 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
      </svg>
    ),
  }

  return (
    <Link
      to={`/projects/${projectSlug}/workflows/${workflow.id}`}
      className="block p-5 rounded-lg bg-gray-800 border border-gray-700 hover:border-gray-600 transition-all group"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-white group-hover:text-primary-300 transition-colors truncate">
            {workflow.name}
          </h3>
          <p className="text-sm text-gray-400 mt-0.5">
            Step {workflow.current_step} of {totalSteps}
          </p>
        </div>
        <span className={`text-xs px-2 py-1 rounded ${statusColors[workflow.status] || statusColors.draft}`}>
          {workflow.status}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{completedSteps} of {totalSteps} steps complete</span>
          <span>{Math.round(progress)}%</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-600 to-primary-400 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Step Timeline */}
      <div className="space-y-2">
        {steps.slice(0, 4).map((step) => (
          <div
            key={step.id}
            className={`flex items-center space-x-3 text-sm ${
              step.step_number === workflow.current_step
                ? 'text-white'
                : step.status === 'completed'
                ? 'text-gray-400'
                : 'text-gray-500'
            }`}
          >
            <div className="flex-shrink-0">
              {stepStatusIcons[step.status] || stepStatusIcons.pending}
            </div>
            <span className="truncate">{step.name}</span>
            {step.step_number === workflow.current_step && (
              <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
                {isInteractive ? 'Interactive' : 'Running'}
              </span>
            )}
          </div>
        ))}
        {steps.length > 4 && (
          <div className="text-xs text-gray-500 pl-6">
            +{steps.length - 4} more steps
          </div>
        )}
      </div>

      {/* Current Step Action Hint */}
      {currentStep && workflow.status === 'active' && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">
              {isInteractive ? 'Continue planning...' : 'View progress...'}
            </span>
            <svg className="w-4 h-4 text-gray-500 group-hover:text-primary-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>
      )}
    </Link>
  )
}
