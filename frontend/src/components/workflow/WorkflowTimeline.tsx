import { useNavigate } from 'react-router-dom'
import type { WorkflowStep } from '../../api'
import { formatRelativeTime } from '../../utils/time'

interface WorkflowTimelineProps {
  steps: WorkflowStep[]
  currentStep: number
  projectSlug: string
  workflowId: string
  onRunStep?: (stepNumber: number) => void
  onStopStep?: (stepNumber: number) => void
  onItemsClick?: (stepId: number) => void
  isRunning?: boolean
}

// Model display names and colors
const modelDisplay: Record<string, { label: string; color: string }> = {
  'opus': { label: 'Opus', color: 'text-purple-400' },
  'sonnet': { label: 'Sonnet', color: 'text-cyan-400' },
  'sonnet-1m': { label: 'Sonnet 1M', color: 'text-cyan-400' },
  'haiku': { label: 'Haiku', color: 'text-emerald-400' },
}

// Compact step row for table layout
function StepRow({ step, isCurrent, projectSlug, workflowId, onRun, onStop, onItemsClick, isRunning }: {
  step: WorkflowStep
  isCurrent: boolean
  projectSlug: string
  workflowId: string
  onRun?: () => void
  onStop?: () => void
  onItemsClick?: () => void
  isRunning?: boolean
}) {
  const navigate = useNavigate()
  const isGenerator = step.config?.loopType === 'generator'
  const isConsumer = step.config?.loopType === 'consumer'
  const inputItems = step.input_items
  const hasInputItems = inputItems && inputItems.total > 0
  const isStepRunning = step.has_active_run === true
  const model = step.config?.model
  const modelInfo = model ? (modelDisplay[model] || { label: model, color: 'text-gray-400' }) : null
  const hasGuardrails = step.has_guardrails
  const failedCount = inputItems?.failed ?? 0

  const handleRowClick = () => {
    navigate(`/projects/${projectSlug}/workflows/${workflowId}/steps/${step.step_number}`)
  }

  // Status indicator
  const StatusIndicator = () => {
    if (isStepRunning) {
      return <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_var(--color-emerald)]" />
    }
    if (step.status === 'completed') {
      return (
        <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )
    }
    if (step.status === 'active') {
      return <span className="w-2 h-2 rounded-full bg-amber-400" />
    }
    return <span className="w-2 h-2 rounded-full bg-gray-600" />
  }

  // Only show last run time if step has actually been executed (has iterations)
  const hasBeenRun = (step.iterations_completed ?? 0) > 0
  const lastRunTime = hasBeenRun ? (step.completed_at || step.started_at) : null

  // Output metric based on step type
  const OutputMetric = () => {
    if (isGenerator) {
      const count = step.items_generated ?? 0
      return (
        <span
          className={`font-mono ${onItemsClick && count > 0 ? 'cursor-pointer hover:text-cyan-400' : ''}`}
          onClick={(e) => {
            if (onItemsClick && count > 0) {
              e.stopPropagation()
              onItemsClick()
            }
          }}
        >
          <span className="text-[var(--color-text-primary)] font-semibold">{count}</span>
          <span className="text-[var(--color-text-muted)] ml-1">items</span>
        </span>
      )
    }
    if (isConsumer && hasInputItems) {
      return (
        <div className="font-mono text-right">
          <span className="text-[var(--color-text-primary)] font-semibold">{inputItems.completed}</span>
          <span className="text-[var(--color-text-muted)]">/{inputItems.total}</span>
          {failedCount > 0 && (
            <span className="text-red-400 ml-2" title={`${failedCount} failed`}>
              ({failedCount} err)
            </span>
          )}
        </div>
      )
    }
    return <span className="text-[var(--color-text-muted)]">—</span>
  }

  return (
    <div
      onClick={handleRowClick}
      className={`group relative flex items-center gap-4 px-4 py-3 rounded-lg border cursor-pointer transition-all
        ${isCurrent
          ? 'border-cyan-500/50 bg-cyan-500/5'
          : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-bright)] hover:bg-[var(--color-elevated)]'
        }
        ${isStepRunning ? 'border-emerald-500/50 bg-emerald-500/5' : ''}
      `}
    >
      {/* Step number + status */}
      <div className="flex items-center gap-3 w-8">
        <StatusIndicator />
      </div>

      {/* Step name + description */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-[var(--color-text-muted)]">{step.step_number}.</span>
          <span className="font-medium text-[var(--color-text-primary)] truncate">{step.name}</span>
          {modelInfo && (
            <span className={`text-[10px] font-mono ${modelInfo.color}`} title={`Using ${modelInfo.label} model`}>
              {modelInfo.label}
            </span>
          )}
          {hasGuardrails && (
            <span className="text-[10px] text-amber-400" title="Has guardrails configured">
              <svg className="w-3 h-3 inline" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            </span>
          )}
        </div>
        {step.config?.description && (
          <p className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">
            {step.config.description}
          </p>
        )}
      </div>

      {/* Output metric */}
      <div className="w-24 text-right text-sm">
        <OutputMetric />
      </div>

      {/* Cycles - show progress toward target if set */}
      <div className="w-24 text-right text-sm font-mono">
        <span className="text-[var(--color-text-primary)]">{step.iterations_completed ?? 0}</span>
        {step.iterations_target ? (
          <span className="text-[var(--color-text-muted)]">/{step.iterations_target}</span>
        ) : (
          <span className="text-[var(--color-text-muted)] ml-1 text-xs">cyc</span>
        )}
      </div>

      {/* Last run */}
      <div className="w-24 text-right text-xs text-[var(--color-text-muted)]">
        {formatRelativeTime(lastRunTime, 'Never')}
      </div>

      {/* Progress bar for consumers */}
      {isConsumer && hasInputItems && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-border)] rounded-b-lg overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all"
            style={{ width: `${(inputItems.completed / inputItems.total) * 100}%` }}
          />
        </div>
      )}

      {/* Action button */}
      <div className="w-20 flex justify-end">
        {isStepRunning ? (
          onStop && (
            <button
              onClick={(e) => { e.stopPropagation(); onStop(); }}
              disabled={isRunning}
              className="px-3 py-1 text-xs font-medium bg-red-600/80 hover:bg-red-500 text-white rounded transition-colors disabled:opacity-50"
            >
              Stop
            </button>
          )
        ) : (
          onRun && (
            <button
              onClick={(e) => { e.stopPropagation(); onRun(); }}
              disabled={isRunning}
              className="px-3 py-1 text-xs font-medium bg-[var(--color-elevated)] hover:bg-cyan-600 text-[var(--color-text-secondary)] hover:text-white border border-[var(--color-border)] hover:border-cyan-500 rounded transition-all opacity-0 group-hover:opacity-100"
            >
              Run
            </button>
          )
        )}
      </div>
    </div>
  )
}

export default function WorkflowTimeline({ steps, currentStep, projectSlug, workflowId, onRunStep, onStopStep, onItemsClick, isRunning }: WorkflowTimelineProps) {
  return (
    <div className="space-y-2">
      {/* Header row */}
      {steps.length > 0 && (
        <div className="flex items-center gap-4 px-4 py-2 text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
          <div className="w-8" />
          <div className="flex-1">Step</div>
          <div className="w-24 text-right">Output</div>
          <div className="w-24 text-right">Cycles</div>
          <div className="w-24 text-right">Last Run</div>
          <div className="w-20" />
        </div>
      )}

      {/* Step rows */}
      {steps.map((step) => (
        <StepRow
          key={step.id}
          step={step}
          isCurrent={step.step_number === currentStep}
          projectSlug={projectSlug}
          workflowId={workflowId}
          onRun={onRunStep ? () => onRunStep(step.step_number) : undefined}
          onStop={onStopStep ? () => onStopStep(step.step_number) : undefined}
          onItemsClick={onItemsClick ? () => onItemsClick(step.id) : undefined}
          isRunning={isRunning}
        />
      ))}

      {steps.length === 0 && (
        <div className="text-center py-12 text-[var(--color-text-muted)]">
          <svg className="w-12 h-12 mx-auto mb-4 text-[var(--color-border)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <p>No steps configured yet.</p>
          <p className="text-sm mt-1">Add steps in the workflow editor.</p>
        </div>
      )}
    </div>
  )
}
