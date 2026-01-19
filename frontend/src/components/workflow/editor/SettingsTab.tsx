import { useNavigate } from 'react-router-dom'
import type { Workflow } from '../../../api'

interface SettingsTabProps {
  workflow: Workflow
  projectSlug: string
  onWorkflowUpdate: () => void
  onError: (error: string) => void
}

export default function SettingsTab({
  workflow,
  projectSlug,
  onWorkflowUpdate: _onWorkflowUpdate,
  onError: _onError,
}: SettingsTabProps) {
  const navigate = useNavigate()
  // Settings tab currently shows read-only info and guidance
  // Future: Add auto-advance rules, notification settings, etc.

  return (
    <div className="max-w-2xl space-y-6">
      {/* Workflow Information */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wide mb-4">
          Workflow Information
        </h3>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-500 mb-1">Workflow ID</label>
            <div className="text-white font-mono text-sm">{workflow.id}</div>
          </div>

          <div>
            <label className="block text-sm text-gray-500 mb-1">Status</label>
            <div className="text-white">{workflow.status}</div>
          </div>

          <div>
            <label className="block text-sm text-gray-500 mb-1">Current Step</label>
            <div className="text-white">{workflow.current_step} of {workflow.steps.length}</div>
          </div>

          <div>
            <label className="block text-sm text-gray-500 mb-1">Steps</label>
            <div className="text-white">{workflow.steps.length}</div>
          </div>
        </div>
      </div>

      {/* Auto-Advance Settings */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wide mb-4">
          Auto-Advance Rules
        </h3>

        <div className="rounded-lg bg-gray-800 border border-gray-700 p-4">
          <div className="flex items-start space-x-3">
            <svg className="w-5 h-5 text-gray-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="text-sm text-gray-300">
                Auto-advance rules let you define when a workflow should automatically move to the next step.
              </p>
              <p className="mt-2 text-xs text-gray-500">
                Coming soon: Configure conditions like "advance when all items are completed" or "advance after approval".
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="card border-red-900/50">
        <h3 className="text-sm font-medium text-red-400 uppercase tracking-wide mb-4">
          Danger Zone
        </h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-white font-medium">Reset Workflow</h4>
              <p className="text-sm text-gray-500">Reset the workflow to its initial state. All progress will be lost.</p>
            </div>
            <button
              onClick={() => {
                if (confirm('Are you sure you want to reset this workflow? All progress will be lost.')) {
                  // TODO: Implement workflow reset
                  alert('Workflow reset is not yet implemented')
                }
              }}
              className="px-4 py-2 bg-red-900/30 text-red-400 rounded-lg hover:bg-red-900/50 border border-red-800/50"
            >
              Reset
            </button>
          </div>

          <div className="border-t border-red-900/30" />

          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-white font-medium">Archive Workflow</h4>
              <p className="text-sm text-gray-500">Move this workflow to the archive. You can restore it later.</p>
            </div>
            <button
              onClick={() => {
                // Navigate back to handle archive through WorkflowDetail
                navigate(`/projects/${projectSlug}/workflows/${workflow.id}`)
              }}
              className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
            >
              Archive
            </button>
          </div>
        </div>
      </div>

      {/* Tips */}
      <div className="rounded-lg bg-gray-800/50 border border-gray-700 p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-2">Tips</h3>
        <ul className="text-sm text-gray-400 space-y-2">
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">•</span>
            <span>Use keyboard shortcut <kbd className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">Cmd+S</kbd> to save changes quickly</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">•</span>
            <span>Press <kbd className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">Esc</kbd> to return to the workflow detail view</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">•</span>
            <span>Add a design document to help Claude understand your project requirements</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">•</span>
            <span>Configure guidelines to set boundaries and coding standards for Claude</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
