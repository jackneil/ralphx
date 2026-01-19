import type { WorkflowStep } from '../../api'
import { formatLocalFull } from '../../utils/time'

interface StepCardProps {
  step: WorkflowStep
  isCurrent: boolean
  isSelected?: boolean  // True if this step is selected for viewing
  onSelect?: () => void
  onEdit?: () => void
  onRun?: (stepNumber: number) => void
  onStop?: () => void
  isRunning?: boolean  // True while the run/stop action is in progress
  hasActiveRun?: boolean  // True if there's an actual run in 'running' status
}

export default function StepCard({ step, isCurrent: _isCurrent, isSelected, onSelect, onEdit, onRun, onStop, isRunning, hasActiveRun }: StepCardProps) {
  const isActive = step.status === 'active'
  // Show running state only if there's actually a run executing
  const isActuallyRunning = hasActiveRun === true
  const isCompleted = step.status === 'completed'
  const isSkipped = step.status === 'skipped'

  const getBorderStyle = () => {
    // Selected step (the one you're viewing) gets the highlight
    if (isSelected) return 'border-[var(--color-cyan)] shadow-[0_0_15px_var(--color-cyan-dim)]'
    if (isCompleted) return 'border-[var(--color-emerald)]/30'
    return 'border-[var(--color-border)]'
  }

  const getStatusLabel = () => {
    if (isActuallyRunning) return 'Running'
    if (isCompleted) return 'Done'
    if (isActive) return 'In Progress'
    if (isSkipped) return 'Skipped'
    return 'Queued'
  }

  const getBadgeClass = () => {
    if (isActuallyRunning) return 'badge-running'
    if (isCompleted) return 'badge-completed'
    if (isActive) return 'badge-active'
    if (isSkipped) return 'badge-pending'
    return 'badge-pending'
  }

  const getStepIcon = () => {
    if (step.step_type === 'interactive') {
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      )
    }
    // Autonomous step - spin when running
    return (
      <svg className={`w-5 h-5 ${isActuallyRunning ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    )
  }

  return (
    <div
      onClick={onSelect}
      className={`
        relative p-5 rounded-xl border transition-all duration-300 cursor-pointer
        bg-[var(--color-surface)] hover:bg-[var(--color-elevated)]
        ${getBorderStyle()}
        ${isSelected ? 'ring-2 ring-[var(--color-cyan)]/30' : ''}
      `}
    >
      {/* Glow effect for selected step */}
      {isSelected && (
        <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-[var(--color-cyan)]/5 to-transparent pointer-events-none" />
      )}

      {/* Header */}
      <div className="relative flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          {/* Step Icon */}
          <div className={`
            w-10 h-10 rounded-lg flex items-center justify-center
            ${isActuallyRunning ? 'bg-[var(--color-cyan)]/20 text-[var(--color-cyan)]' : ''}
            ${isCompleted && !isActuallyRunning ? 'bg-[var(--color-emerald)]/20 text-[var(--color-emerald)]' : ''}
            ${!isCompleted && !isActuallyRunning ? 'bg-[var(--color-elevated)] text-[var(--color-text-muted)]' : ''}
          `}>
            {isCompleted ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              getStepIcon()
            )}
          </div>

          {/* Step Info */}
          <div>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              STEP {step.step_number}
            </span>
            <h3 className="font-semibold text-[var(--color-text-primary)] mt-0.5">
              {step.name}
            </h3>
          </div>
        </div>

        {/* Status and Indicators */}
        <div className="flex items-center gap-2">
          {step.has_guardrails && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-violet-900/50 text-violet-400 border border-violet-700/50" title="Has guardrails configured">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </span>
          )}
          <span className={`badge ${getBadgeClass()}`}>
            {getStatusLabel()}
          </span>
        </div>
      </div>

      {/* Description */}
      {step.config?.description && (
        <p className="text-sm text-[var(--color-text-secondary)] mb-4 line-clamp-2">
          {step.config.description}
        </p>
      )}

      {/* Progress Display */}
      {step.step_type === 'autonomous' && (step.iterations_completed !== undefined && step.iterations_completed > 0 || step.items_generated !== undefined && step.items_generated > 0 || step.input_items || hasActiveRun) && (
        <div className="mb-4 p-3 bg-[var(--color-void)] rounded-lg border border-[var(--color-border)]">
          {/* Items Row - consistent format for both step types */}
          {/* Generator steps show items_generated, consumer steps show input_items.total */}
          {(step.items_generated !== undefined && step.items_generated > 0) || (step.input_items && step.input_items.total > 0) ? (
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono text-[var(--color-text-muted)] uppercase tracking-wider">
                {step.input_items ? 'Stories' : 'Generated'}
              </span>
              <span className="text-sm font-semibold text-[var(--color-emerald)]">
                {step.input_items ? step.input_items.total : step.items_generated}
              </span>
            </div>
          ) : null}

          {/* Iterations Row - same format for both */}
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-[var(--color-text-muted)] uppercase tracking-wider">
              Iterations
            </span>
            <span className="text-xs font-mono text-[var(--color-text-secondary)]">
              {step.iterations_completed || 0}
              {step.iterations_target ? ` / ${step.iterations_target}` : ''}
            </span>
          </div>
          {step.iterations_target && (
            <div className="mt-2 h-1.5 bg-[var(--color-elevated)] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[var(--color-cyan)] to-[var(--color-emerald)] transition-all duration-300"
                style={{
                  width: `${Math.min(100, ((step.iterations_completed || 0) / step.iterations_target) * 100)}%`
                }}
              />
            </div>
          )}

          {/* Status Breakdown - ONLY for consumer steps with input_items */}
          {step.input_items && step.input_items.total > 0 && (
            <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
              {/* Progress bar showing status distribution */}
              <div className="h-2 bg-[var(--color-elevated)] rounded-full overflow-hidden mb-2">
                <div className="h-full flex">
                  {step.input_items.completed > 0 && (
                    <div
                      className="bg-[var(--color-emerald)] transition-all duration-300"
                      style={{ width: `${(step.input_items.completed / step.input_items.total) * 100}%` }}
                      title={`${step.input_items.completed} done`}
                    />
                  )}
                  {step.input_items.in_progress > 0 && (
                    <div
                      className="bg-[var(--color-cyan)] transition-all duration-300"
                      style={{ width: `${(step.input_items.in_progress / step.input_items.total) * 100}%` }}
                      title={`${step.input_items.in_progress} in progress`}
                    />
                  )}
                  {step.input_items.duplicate > 0 && (
                    <div
                      className="bg-[var(--color-amber)] transition-all duration-300"
                      style={{ width: `${(step.input_items.duplicate / step.input_items.total) * 100}%` }}
                      title={`${step.input_items.duplicate} duplicates`}
                    />
                  )}
                  {step.input_items.skipped > 0 && (
                    <div
                      className="bg-[var(--color-slate)] transition-all duration-300"
                      style={{ width: `${(step.input_items.skipped / step.input_items.total) * 100}%` }}
                      title={`${step.input_items.skipped} skipped`}
                    />
                  )}
                  {step.input_items.failed > 0 && (
                    <div
                      className="bg-[var(--color-rose)] transition-all duration-300"
                      style={{ width: `${(step.input_items.failed / step.input_items.total) * 100}%` }}
                      title={`${step.input_items.failed} failed`}
                    />
                  )}
                </div>
              </div>
              {/* Status breakdown chips */}
              <div className="flex flex-wrap gap-1.5 text-xs">
                {step.input_items.pending > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-cyan)]/20 text-[var(--color-cyan)] font-mono">
                    {step.input_items.pending} new
                  </span>
                )}
                {step.input_items.in_progress > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-amber)]/20 text-[var(--color-amber)] font-mono">
                    {step.input_items.in_progress} in progress
                  </span>
                )}
                {step.input_items.completed > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-emerald)]/20 text-[var(--color-emerald)] font-mono">
                    {step.input_items.completed} implemented
                  </span>
                )}
                {step.input_items.duplicate > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-slate)]/20 text-[var(--color-text-muted)] font-mono">
                    {step.input_items.duplicate} dups
                  </span>
                )}
                {step.input_items.skipped > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-slate)]/20 text-[var(--color-text-muted)] font-mono">
                    {step.input_items.skipped} skipped
                  </span>
                )}
                {step.input_items.failed > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-rose)]/20 text-[var(--color-rose)] font-mono">
                    {step.input_items.failed} failed
                  </span>
                )}
                {step.input_items.rejected > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--color-rose)]/20 text-[var(--color-rose)] font-mono">
                    {step.input_items.rejected} rejected
                  </span>
                )}
              </div>
            </div>
          )}

          {hasActiveRun && (
            <div className="mt-2 flex items-center gap-2 text-xs font-mono text-[var(--color-cyan)]">
              <span className="status-dot status-dot-running" />
              Running...
            </div>
          )}
        </div>
      )}

      {/* Timestamps */}
      {(step.started_at || step.completed_at) && (
        <div className="text-xs font-mono text-[var(--color-text-muted)] mb-4 space-y-1">
          {step.started_at && (
            <div className="flex items-center gap-2">
              <span className="text-[var(--color-text-muted)]/60">Started:</span>
              <span>{formatLocalFull(step.started_at)}</span>
            </div>
          )}
          {step.completed_at && (
            <div className="flex items-center gap-2">
              <span className="text-[var(--color-text-muted)]/60">Completed:</span>
              <span>{formatLocalFull(step.completed_at)}</span>
            </div>
          )}
        </div>
      )}

      {/* Artifacts */}
      {step.artifacts && Object.keys(step.artifacts).length > 0 && (
        <div className="mb-4 pt-3 border-t border-[var(--color-border)]">
          <div className="text-xs font-mono text-[var(--color-text-muted)] mb-2 uppercase tracking-wider">
            Artifacts
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.keys(step.artifacts).map(key => (
              <span
                key={key}
                className="px-2 py-1 text-xs font-mono bg-[var(--color-elevated)] text-[var(--color-text-secondary)] rounded border border-[var(--color-border)]"
              >
                {key}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center gap-2 pt-3 border-t border-[var(--color-border)]">
        {/* Run Button - show when not running and step not completed */}
        {onRun && step.status !== 'completed' && !isActuallyRunning && (
          <button
            onClick={() => onRun(step.step_number)}
            disabled={isRunning}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed bg-[var(--color-cyan)]/10 text-[var(--color-cyan)] border border-[var(--color-cyan)]/30 hover:bg-[var(--color-cyan)]/20 hover:border-[var(--color-cyan)]/50"
            title="Run this step"
          >
            {isRunning ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Starting...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
                <span>Run</span>
              </>
            )}
          </button>
        )}

        {/* Stop Button - show when step is actually running */}
        {onStop && isActuallyRunning && (
          <button
            onClick={onStop}
            disabled={isRunning}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed bg-[var(--color-rose)]/10 text-[var(--color-rose)] border border-[var(--color-rose)]/30 hover:bg-[var(--color-rose)]/20 hover:border-[var(--color-rose)]/50"
            title="Stop this step"
          >
            {isRunning ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Stopping...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                </svg>
                <span>Stop</span>
              </>
            )}
          </button>
        )}

        {/* Completed State */}
        {step.status === 'completed' && (
          <div className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--color-emerald)]/10 text-[var(--color-emerald)]">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="font-medium text-sm">Completed</span>
          </div>
        )}

        {/* Edit Button */}
        {onEdit && (
          <button
            onClick={onEdit}
            className="p-2.5 rounded-lg bg-[var(--color-elevated)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
            aria-label={`Edit step ${step.step_number}`}
            title="Edit step"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
