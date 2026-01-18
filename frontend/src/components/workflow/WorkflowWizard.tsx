import { useState } from 'react'
import type { WorkflowTemplate } from '../../api'

interface WorkflowWizardProps {
  templates: WorkflowTemplate[]
  onClose: () => void
  onSubmit: (name: string, templateId: string) => Promise<void>
}

export default function WorkflowWizard({ templates, onClose, onSubmit }: WorkflowWizardProps) {
  const [step, setStep] = useState<'template' | 'name'>('template')
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplate | null>(null)
  const [workflowName, setWorkflowName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSelectTemplate = (template: WorkflowTemplate) => {
    setSelectedTemplate(template)
    setWorkflowName(`${template.name}`)
    setStep('name')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTemplate || !workflowName.trim()) return

    setError(null)
    setSubmitting(true)
    try {
      await onSubmit(workflowName.trim(), selectedTemplate.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="workflow-wizard-title"
    >
      <div className="card max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 id="workflow-wizard-title" className="text-xl font-semibold text-white">
            {step === 'template' ? 'Choose a Workflow' : 'Name Your Workflow'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white transition-colors"
            aria-label="Close dialog"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Step 1: Select Template */}
        {step === 'template' && (
          <div className="space-y-4">
            <p className="text-gray-400 mb-6">
              Choose a workflow template to get started. Each template guides you through a specific process.
            </p>

            {templates.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <p>No workflow templates available.</p>
              </div>
            ) : (
              <div className="grid gap-4">
                {templates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => handleSelectTemplate(template)}
                    className="p-4 rounded-lg border border-gray-700 hover:border-primary-500 bg-gray-800/50 hover:bg-gray-800 transition-colors text-left"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-white mb-1">
                          {template.name}
                        </h3>
                        {template.description && (
                          <p className="text-gray-400 text-sm mb-3">
                            {template.description}
                          </p>
                        )}
                        <div className="flex items-center space-x-4 text-sm text-gray-500">
                          <span>{template.steps.length} steps</span>
                          <span>
                            {template.steps.filter(p => p.type === 'interactive').length} interactive
                          </span>
                          <span>
                            {template.steps.filter(p => p.type === 'autonomous').length} automated
                          </span>
                        </div>
                      </div>
                      <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>

                    {/* Step Preview */}
                    <div className="mt-4 flex items-center space-x-2">
                      {template.steps.map((step, index) => (
                        <div key={index} className="flex items-center">
                          <div
                            className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                              step.type === 'interactive'
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-700 text-gray-300'
                            }`}
                            title={step.name}
                          >
                            {step.type === 'interactive' ? (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              </svg>
                            )}
                          </div>
                          {index < template.steps.length - 1 && (
                            <div className="w-4 h-0.5 bg-gray-600" />
                          )}
                        </div>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Name Workflow */}
        {step === 'name' && selectedTemplate && (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <button
                type="button"
                onClick={() => setStep('template')}
                className="flex items-center space-x-2 text-sm text-gray-400 hover:text-white mb-4"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span>Back to templates</span>
              </button>

              <div className="p-4 rounded-lg bg-gray-800/50 border border-gray-700 mb-6">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-full bg-primary-600 flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-sm text-gray-400">Template</div>
                    <div className="text-white font-medium">{selectedTemplate.name}</div>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="workflowName" className="block text-sm font-medium text-gray-300 mb-2">
                Workflow Name
              </label>
              <input
                id="workflowName"
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                placeholder="e.g., My New Product"
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                autoFocus
              />
              <p className="mt-2 text-sm text-gray-500">
                Give your workflow a descriptive name so you can easily identify it later.
              </p>
            </div>

            {error && (
              <div className="p-4 rounded-lg bg-red-900/20 border border-red-800 text-red-400">
                {error}
              </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!workflowName.trim() || submitting}
                className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors disabled:opacity-50"
              >
                {submitting ? 'Creating...' : 'Create Workflow'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
