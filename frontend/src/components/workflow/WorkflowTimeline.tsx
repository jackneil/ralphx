import { useState, useEffect } from 'react'
import type { WorkflowStep, WorkflowResource, ResourceVersion } from '../../api'
import { listResourceVersions, restoreResourceVersion } from '../../api'

interface WorkflowTimelineProps {
  steps: WorkflowStep[]
  currentStep: number
  selectedStep?: number
  resources?: WorkflowResource[]
  projectSlug?: string
  workflowId?: string
  onStepSelect?: (stepNumber: number) => void
  onRunStep?: (stepNumber: number) => void
  onItemsClick?: (stepId: number) => void
  onResourceUpdate?: (resourceId: number, content: string, expectedUpdatedAt: string) => Promise<void>
  isRunning?: boolean
}

// Rough token estimation (4 chars per token on average)
function estimateTokens(content: string | undefined): number {
  if (!content) return 0
  return Math.ceil(content.length / 4)
}

function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens}`
  return `${(tokens / 1000).toFixed(1)}k`
}

// Step Card Component
function StepCard({ step, isSelected, onSelect, onRun, onItemsClick, isRunning }: {
  step: WorkflowStep
  isSelected: boolean
  onSelect?: () => void
  onRun?: () => void
  onItemsClick?: () => void
  isRunning?: boolean
}) {
  const isGenerator = step.config?.loopType === 'generator'
  const isConsumer = step.config?.loopType === 'consumer'
  const inputItems = step.input_items
  const hasInputItems = inputItems && inputItems.total > 0

  return (
    <div
      className={`flex-1 min-w-[200px] p-4 rounded-lg border transition-all
        ${onSelect ? 'cursor-pointer hover:border-[var(--color-border-hover)]' : ''}
        ${isSelected ? 'border-cyan-500 bg-cyan-500/10' : 'border-[var(--color-border)] bg-[var(--color-elevated)]'}`}
      onClick={onSelect}
    >
      {/* Header: step number + name */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-[var(--color-text-muted)]">
            {step.step_number}.
          </span>
          <span className="font-medium text-[var(--color-text-primary)]">
            {step.name}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {step.has_active_run && (
            <span className="badge badge-running text-[10px]">RUNNING</span>
          )}
          {onRun && !step.has_active_run && (
            <button
              onClick={(e) => { e.stopPropagation(); onRun(); }}
              disabled={isRunning}
              className="px-2 py-1 text-xs font-medium bg-cyan-600 hover:bg-cyan-500 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={`Run ${step.name}`}
            >
              ▶ Run
            </button>
          )}
        </div>
      </div>

      {/* Work metrics - varies by step type */}
      <div className="mb-3 min-h-[48px]">
        {isGenerator && (
          <div
            className={`text-2xl font-bold text-[var(--color-text-primary)] ${onItemsClick && (step.items_generated ?? 0) > 0 ? 'cursor-pointer hover:text-cyan-400 transition-colors' : ''}`}
            onClick={(e) => {
              if (onItemsClick && (step.items_generated ?? 0) > 0) {
                e.stopPropagation()
                onItemsClick()
              }
            }}
            title={onItemsClick && (step.items_generated ?? 0) > 0 ? 'Click to view items' : undefined}
          >
            {step.items_generated ?? 0}
            <span className="text-sm font-normal text-[var(--color-text-muted)] ml-2">generated</span>
          </div>
        )}
        {isConsumer && hasInputItems && (
          <>
            <div className="text-lg font-bold text-[var(--color-text-primary)]">
              {inputItems.completed} / {inputItems.total}
              <span className="text-sm font-normal text-[var(--color-text-muted)] ml-2">completed</span>
            </div>
            <div className="mt-2 h-2 bg-[var(--color-border)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--color-emerald)] transition-all"
                style={{ width: `${(inputItems.completed / inputItems.total) * 100}%` }}
              />
            </div>
          </>
        )}
        {!isGenerator && !(isConsumer && hasInputItems) && (
          <div className="text-lg text-[var(--color-text-muted)]">
            {step.iterations_completed ?? 0} cycles
          </div>
        )}
      </div>

      {/* Footer: cycles + type */}
      <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
        <span>{step.iterations_completed ?? 0} cycles</span>
        <span>{step.step_type === 'interactive' ? 'Chat' : 'Auto'}</span>
      </div>
    </div>
  )
}

export default function WorkflowTimeline({ steps, currentStep, selectedStep, resources = [], projectSlug, workflowId, onStepSelect, onRunStep, onItemsClick, onResourceUpdate, isRunning }: WorkflowTimelineProps) {
  // Use selectedStep if provided, otherwise fall back to currentStep
  const effectiveSelectedStep = selectedStep ?? currentStep
  // State for viewing resources
  const [viewingCategory, setViewingCategory] = useState<string | null>(null)

  // State for editing resources
  const [editingResource, setEditingResource] = useState<WorkflowResource | null>(null)
  const [editContent, setEditContent] = useState('')
  const [originalUpdatedAt, setOriginalUpdatedAt] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // State for version history
  const [viewingVersions, setViewingVersions] = useState<WorkflowResource | null>(null)
  const [versions, setVersions] = useState<ResourceVersion[]>([])
  const [versionsTotal, setVersionsTotal] = useState(0)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [previewVersion, setPreviewVersion] = useState<ResourceVersion | null>(null)
  const [restoringVersion, setRestoringVersion] = useState(false)

  // Auto-hide toast after 3 seconds
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  // Handle edit button click
  const handleEditClick = (resource: WorkflowResource) => {
    setEditingResource(resource)
    setEditContent(resource.content || '')
    setOriginalUpdatedAt(resource.updated_at)
    setSaveError(null)
  }

  // Handle save (show confirmation first)
  const handleSaveClick = () => {
    setShowSaveConfirm(true)
  }

  // Handle confirmed save
  const handleConfirmSave = async () => {
    if (!editingResource || !onResourceUpdate) return

    setSaving(true)
    setSaveError(null)
    setShowSaveConfirm(false)

    try {
      await onResourceUpdate(editingResource.id, editContent, originalUpdatedAt)
      setToast({ message: 'Version saved', type: 'success' })
      setEditingResource(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save'
      if (message.includes('modified in another session') || message.includes('409')) {
        setSaveError('Resource was modified in another session. Please reload to see the latest version.')
      } else {
        setSaveError(message)
      }
    } finally {
      setSaving(false)
    }
  }

  // Handle viewing version history
  const handleViewHistory = async (resource: WorkflowResource) => {
    if (!projectSlug || !workflowId) return

    setViewingVersions(resource)
    setVersionsLoading(true)
    setPreviewVersion(null)

    try {
      const data = await listResourceVersions(projectSlug, workflowId, resource.id)
      setVersions(data.versions)
      setVersionsTotal(data.total)
    } catch (err) {
      console.error('Failed to load versions:', err)
      setVersions([])
      setVersionsTotal(0)
    } finally {
      setVersionsLoading(false)
    }
  }

  // Handle restore version
  const handleRestoreVersion = async (version: ResourceVersion) => {
    if (!projectSlug || !workflowId || !viewingVersions) return

    setRestoringVersion(true)

    try {
      await restoreResourceVersion(projectSlug, workflowId, viewingVersions.id, version.id)
      setToast({ message: 'Version restored', type: 'success' })
      setViewingVersions(null)
      setPreviewVersion(null)
      // Refresh versions list would happen through parent component's reload
    } catch (err) {
      console.error('Failed to restore version:', err)
      setToast({ message: 'Failed to restore version', type: 'error' })
    } finally {
      setRestoringVersion(false)
    }
  }

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  }

  // Calculate resource stats
  const totalTokens = resources.reduce((sum, r) => sum + estimateTokens(r.content), 0)
  const enabledResources = resources.filter(r => r.enabled)

  // Group resources by type
  const designDocs = enabledResources.filter(r => r.resource_type === 'design_doc')
  const guidelines = enabledResources.filter(r => r.resource_type === 'guardrail')
  const inputs = enabledResources.filter(r => r.resource_type === 'input_file' || r.resource_type === 'input')
  const prompts = enabledResources.filter(r => r.resource_type === 'prompt')

  // Get resources for the currently viewed category
  const viewingResources = viewingCategory === 'design_doc' ? designDocs
    : viewingCategory === 'guardrail' ? guidelines
    : viewingCategory === 'input' ? inputs
    : viewingCategory === 'prompt' ? prompts
    : []

  const categoryLabels: Record<string, string> = {
    design_doc: 'Design Documents',
    guardrail: 'Guidelines',
    input: 'Input Files',
    prompt: 'Prompt Templates',
  }

  return (
    <div className="card-panel p-6">
      {/* Header - Resource Summary by Type */}
      <div className="flex items-center gap-6 mb-6 flex-wrap">
        {designDocs.length > 0 && (
          <button
            onClick={() => setViewingCategory(viewingCategory === 'design_doc' ? null : 'design_doc')}
            className={`flex items-center gap-2 px-2 py-1 rounded transition-colors ${
              viewingCategory === 'design_doc' ? 'bg-purple-500/20 ring-1 ring-purple-500/50' : 'hover:bg-purple-500/10'
            }`}
          >
            <div className="w-6 h-6 rounded bg-purple-500/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="text-left">
              <span className="text-xs text-purple-400 font-medium">Design Doc</span>
              <span className="text-xs text-[var(--color-text-muted)] ml-1.5">
                {designDocs.length > 1 ? `${designDocs.length} • ` : ''}{formatTokens(designDocs.reduce((s, r) => s + estimateTokens(r.content), 0))} tok
              </span>
            </div>
          </button>
        )}

        {guidelines.length > 0 && (
          <button
            onClick={() => setViewingCategory(viewingCategory === 'guardrail' ? null : 'guardrail')}
            className={`flex items-center gap-2 px-2 py-1 rounded transition-colors ${
              viewingCategory === 'guardrail' ? 'bg-amber-500/20 ring-1 ring-amber-500/50' : 'hover:bg-amber-500/10'
            }`}
          >
            <div className="w-6 h-6 rounded bg-amber-500/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="text-left">
              <span className="text-xs text-amber-400 font-medium">Guidelines</span>
              <span className="text-xs text-[var(--color-text-muted)] ml-1.5">
                {guidelines.length} • {formatTokens(guidelines.reduce((s, r) => s + estimateTokens(r.content), 0))} tok
              </span>
            </div>
          </button>
        )}

        {inputs.length > 0 && (
          <button
            onClick={() => setViewingCategory(viewingCategory === 'input' ? null : 'input')}
            className={`flex items-center gap-2 px-2 py-1 rounded transition-colors ${
              viewingCategory === 'input' ? 'bg-blue-500/20 ring-1 ring-blue-500/50' : 'hover:bg-blue-500/10'
            }`}
          >
            <div className="w-6 h-6 rounded bg-blue-500/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="text-left">
              <span className="text-xs text-blue-400 font-medium">Inputs</span>
              <span className="text-xs text-[var(--color-text-muted)] ml-1.5">
                {inputs.length} • {formatTokens(inputs.reduce((s, r) => s + estimateTokens(r.content), 0))} tok
              </span>
            </div>
          </button>
        )}

        {prompts.length > 0 && (
          <button
            onClick={() => setViewingCategory(viewingCategory === 'prompt' ? null : 'prompt')}
            className={`flex items-center gap-2 px-2 py-1 rounded transition-colors ${
              viewingCategory === 'prompt' ? 'bg-emerald-500/20 ring-1 ring-emerald-500/50' : 'hover:bg-emerald-500/10'
            }`}
          >
            <div className="w-6 h-6 rounded bg-emerald-500/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="text-left">
              <span className="text-xs text-emerald-400 font-medium">Prompts</span>
              <span className="text-xs text-[var(--color-text-muted)] ml-1.5">
                {prompts.length} • {formatTokens(prompts.reduce((s, r) => s + estimateTokens(r.content), 0))} tok
              </span>
            </div>
          </button>
        )}

        {enabledResources.length === 0 && (
          <span className="text-xs text-[var(--color-text-muted)]">No resources configured</span>
        )}

        {/* Total */}
        {enabledResources.length > 0 && (
          <div className="ml-auto text-xs text-[var(--color-text-muted)]">
            Total: {formatTokens(totalTokens)} tokens
          </div>
        )}
      </div>

      {/* Resource Viewer Panel */}
      {viewingCategory && viewingResources.length > 0 && (
        <div className="mb-6 border border-[var(--color-border)] rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-[var(--color-elevated)] border-b border-[var(--color-border)]">
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              {categoryLabels[viewingCategory]} ({viewingResources.length})
            </h3>
            <button
              onClick={() => setViewingCategory(null)}
              className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="max-h-[400px] overflow-y-auto">
            {viewingResources.map((resource, idx) => (
              <div
                key={resource.id}
                className={`p-4 ${idx > 0 ? 'border-t border-[var(--color-border)]' : ''}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-[var(--color-text-primary)]">
                    {resource.name}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {formatTokens(estimateTokens(resource.content))} tokens
                    </span>
                    {onResourceUpdate && (
                      <button
                        onClick={() => handleEditClick(resource)}
                        className="px-2 py-1 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 rounded transition-colors"
                        title="Edit resource"
                      >
                        Edit
                      </button>
                    )}
                    {projectSlug && workflowId && (
                      <button
                        onClick={() => handleViewHistory(resource)}
                        className="px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] rounded transition-colors"
                        title="View version history"
                      >
                        History
                      </button>
                    )}
                  </div>
                </div>
                <pre className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap font-mono bg-[var(--color-surface)] p-3 rounded max-h-[200px] overflow-y-auto">
                  {resource.content || '(No content)'}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Step Cards */}
      <div className="flex gap-4 flex-wrap">
        {steps.map((step) => (
          <StepCard
            key={step.id}
            step={step}
            isSelected={step.step_number === effectiveSelectedStep}
            onSelect={onStepSelect ? () => onStepSelect(step.step_number) : undefined}
            onRun={onRunStep ? () => onRunStep(step.step_number) : undefined}
            onItemsClick={onItemsClick ? () => onItemsClick(step.id) : undefined}
            isRunning={isRunning}
          />
        ))}
      </div>

      {/* Edit Resource Modal */}
      {editingResource && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">
                Edit: {editingResource.name}
              </h3>
              <button
                onClick={() => setEditingResource(null)}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-4 flex-1 overflow-auto">
              {saveError && (
                <div className="mb-4 p-3 rounded bg-red-900/20 border border-red-800 text-red-400 text-sm">
                  {saveError}
                </div>
              )}

              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-[300px] p-3 bg-[var(--color-elevated)] border border-[var(--color-border)] rounded text-sm text-[var(--color-text-primary)] font-mono resize-none focus:outline-none focus:border-cyan-500"
                placeholder="Enter content..."
              />
            </div>

            <div className="flex items-center justify-end gap-3 px-4 py-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => setEditingResource(null)}
                className="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveClick}
                disabled={saving || editContent === (editingResource.content || '')}
                className="px-4 py-2 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save Confirmation Modal */}
      {showSaveConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-6 max-w-md">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">
                Save Changes?
              </h3>
            </div>

            <p className="text-sm text-[var(--color-text-secondary)] mb-6">
              This will update the resource for <strong>ALL steps</strong> in this workflow.
              A version snapshot will be saved automatically.
            </p>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowSaveConfirm(false)}
                className="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmSave}
                disabled={saving}
                className="px-4 py-2 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {viewingVersions && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">
                Version History: {viewingVersions.name}
              </h3>
              <button
                onClick={() => { setViewingVersions(null); setPreviewVersion(null); }}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4">
              {versionsLoading ? (
                <div className="text-center py-8 text-[var(--color-text-muted)]">
                  Loading versions...
                </div>
              ) : versions.length === 0 ? (
                <div className="text-center py-8 text-[var(--color-text-muted)]">
                  No version history yet. Versions are created when you edit a resource.
                </div>
              ) : (
                <div className="space-y-3">
                  {versions.map((version) => (
                    <div
                      key={version.id}
                      className={`p-3 rounded border transition-colors ${
                        previewVersion?.id === version.id
                          ? 'border-cyan-500 bg-cyan-500/10'
                          : 'border-[var(--color-border)] hover:border-[var(--color-border-hover)]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-[var(--color-text-primary)]">
                            Version {version.version_number}
                          </span>
                          {version.name && version.name !== viewingVersions.name && (
                            <span className="text-xs text-[var(--color-text-muted)]">
                              (was: {version.name})
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-[var(--color-text-muted)]">
                          {formatDate(version.created_at)}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setPreviewVersion(previewVersion?.id === version.id ? null : version)}
                          className="px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] rounded transition-colors"
                        >
                          {previewVersion?.id === version.id ? 'Hide Preview' : 'Preview'}
                        </button>
                        <button
                          onClick={() => handleRestoreVersion(version)}
                          disabled={restoringVersion}
                          className="px-2 py-1 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 rounded transition-colors disabled:opacity-50"
                        >
                          {restoringVersion ? 'Restoring...' : 'Restore'}
                        </button>
                      </div>

                      {previewVersion?.id === version.id && (
                        <pre className="mt-3 text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap font-mono bg-[var(--color-elevated)] p-3 rounded max-h-[200px] overflow-y-auto">
                          {version.content || '(No content)'}
                        </pre>
                      )}
                    </div>
                  ))}

                  {versionsTotal > versions.length && (
                    <div className="text-center text-xs text-[var(--color-text-muted)] py-2">
                      Showing {versions.length} of {versionsTotal} versions
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg ${
          toast.type === 'success'
            ? 'bg-green-900/90 border border-green-700 text-green-400'
            : 'bg-red-900/90 border border-red-700 text-red-400'
        }`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
