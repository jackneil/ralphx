import { useState } from 'react'
import type { WorkflowStep } from '../../../api'
import ConfirmDialog from '../../ConfirmDialog'

interface ArchivedStepsProps {
  archivedSteps: WorkflowStep[]
  loading: boolean
  onRestore: (step: WorkflowStep) => Promise<void>
  onPermanentlyDelete: (step: WorkflowStep) => Promise<void>
}

export default function ArchivedSteps({
  archivedSteps,
  loading,
  onRestore,
  onPermanentlyDelete,
}: ArchivedStepsProps) {
  const [expanded, setExpanded] = useState(false)
  const [stepToDelete, setStepToDelete] = useState<WorkflowStep | null>(null)
  const [pendingStepId, setPendingStepId] = useState<number | null>(null)

  // Don't show anything if there are no archived steps and not loading
  if (!loading && archivedSteps.length === 0) {
    return null
  }

  return (
    <div className="mt-4 border-t border-gray-700 pt-4">
      {/* Header - clickable to expand/collapse */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-2 py-1 text-sm text-gray-400 hover:text-gray-300 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          <span>Trash ({archivedSteps.length})</span>
        </div>
        <svg
          className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-2 space-y-2">
          {loading ? (
            <div className="text-center py-2 text-gray-500 text-sm">Loading...</div>
          ) : (
            archivedSteps.map((step) => (
              <div
                key={step.id}
                className="flex items-center justify-between py-2 px-3 bg-gray-800/50 rounded"
              >
                <div className="flex-1 min-w-0">
                  <span className="text-gray-500 text-xs mr-2">#{step.step_number}</span>
                  <span className="text-gray-400 text-sm truncate">{step.name}</span>
                </div>
                <div className="flex gap-1 flex-shrink-0 ml-2">
                  <button
                    onClick={async () => {
                      setPendingStepId(step.id)
                      try {
                        await onRestore(step)
                      } finally {
                        setPendingStepId(null)
                      }
                    }}
                    disabled={pendingStepId !== null}
                    className="px-2 py-1 text-xs text-primary-400 hover:text-primary-300 bg-gray-700 hover:bg-gray-600 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Restore step to original position"
                  >
                    {pendingStepId === step.id ? 'Restoring...' : 'Restore'}
                  </button>
                  <button
                    onClick={() => setStepToDelete(step)}
                    disabled={pendingStepId !== null}
                    className="px-2 py-1 text-xs text-red-400 hover:text-red-300 bg-gray-700 hover:bg-red-900/30 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Permanently delete step"
                  >
                    {pendingStepId === step.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Permanent Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={stepToDelete !== null}
        title={`Permanently delete "${stepToDelete?.name}"?`}
        message="This action cannot be undone. The step and all its data will be permanently removed."
        confirmLabel="Delete Forever"
        variant="danger"
        typeToConfirm="delete"
        onConfirm={async () => {
          if (stepToDelete) {
            const stepToRemove = stepToDelete
            setStepToDelete(null)
            setPendingStepId(stepToRemove.id)
            try {
              await onPermanentlyDelete(stepToRemove)
            } finally {
              setPendingStepId(null)
            }
          }
        }}
        onCancel={() => setStepToDelete(null)}
      />
    </div>
  )
}
